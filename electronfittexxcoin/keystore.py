#!/usr/bin/env python3
# -*- mode: python3 -*-
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2016  The Electrum developers
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import inspect
from typing import Optional
from . import bitcoin
from .bitcoin import *

from .address import Address, PublicKey
from . import networks
from .mnemonic import Mnemonic, Mnemonic_Electrum, seed_type_name, is_seed
from .plugins import run_hook
from .util import PrintError, InvalidPassword, hfu


class KeyStore(PrintError):

    def __init__(self):
        PrintError.__init__(self)
        self.wallet_advice = {}
        self.thread = None  # Hardware_KeyStore may use this attribute, otherwise stays None

    def has_seed(self):
        return False

    def has_derivation(self):
        """ Only applies to BIP32 keystores. """
        return False

    def is_watching_only(self):
        return False

    def can_import(self):
        return False

    def get_tx_derivations(self, tx):
        keypairs = {}
        for txin in tx.inputs():
            num_sig = txin.get('num_sig')
            if num_sig is None:
                continue
            x_signatures = txin['signatures']
            signatures = [sig for sig in x_signatures if sig]
            if len(signatures) == num_sig:
                # input is complete
                continue
            for k, x_pubkey in enumerate(txin['x_pubkeys']):
                if x_signatures[k] is not None:
                    # this pubkey already signed
                    continue
                derivation = self.get_pubkey_derivation(x_pubkey)
                if not derivation:
                    continue
                keypairs[x_pubkey] = derivation
        return keypairs

    def can_sign(self, tx):
        if self.is_watching_only():
            return False
        return bool(self.get_tx_derivations(tx))

    def set_wallet_advice(self, addr, advice):
        pass

    def is_hw_without_cashtoken_support(self):
        """Reimplement this method to signal to the wallet that CashToken support for this keystore is dangerously
        misleading. This returns False by default, but is re-implemented in Hardware_KeyStore to return True, because
        all HW wallets other than Satochip (which reimplements this yet again to returns False), cannot sign
        CashToken inputs."""
        return False


class Software_KeyStore(KeyStore):

    def __init__(self):
        KeyStore.__init__(self)

    def may_have_password(self):
        return not self.is_watching_only()

    def sign_message(self, sequence, message, password):
        privkey, compressed = self.get_private_key(sequence, password)
        key = regenerate_key(privkey)
        return key.sign_message(message, compressed)

    def decrypt_message(self, sequence, message, password):
        privkey, compressed = self.get_private_key(sequence, password)
        ec = regenerate_key(privkey)
        decrypted = ec.decrypt_message(message)
        return decrypted

    def sign_transaction(self, tx, password, *, use_cache=False, ndata=None, grind=None):
        if self.is_watching_only():
            return
        # Raise if password is not correct.
        self.check_password(password)
        # Add private keys
        keypairs = self.get_tx_derivations(tx)
        for k, v in keypairs.items():
            keypairs[k] = self.get_private_key(v, password)
        # Sign
        if keypairs:
            if ndata is not None:
                # If we have ndata, check that the Transaction class passed to us supports ndata.
                # Some extant plugins such as Flipstarter inherit from Transaction (reimplementing `sign`) and do not
                # support this argument.
                if 'ndata' not in inspect.signature(tx.sign, follow_wrapped=True).parameters:
                    raise RuntimeError(f'Transaction subclass "{tx.__class__.__name__}" does not support the "ndata" kwarg')
                tx.sign(keypairs, use_cache=use_cache, ndata=ndata)
            else:
                # Regular transaction sign (no ndata supported or no ndata specified)
                tx.sign(keypairs, use_cache=use_cache)


class Imported_KeyStore(Software_KeyStore):
    # keystore for imported private keys
    # private keys are encrypted versions of the WIF encoding

    def __init__(self, d):
        Software_KeyStore.__init__(self)
        keypairs = d.get('keypairs', {})
        self.keypairs = {PublicKey.from_string(pubkey): enc_privkey
                         for pubkey, enc_privkey in keypairs.items()}
        self._sorted = None

    def is_deterministic(self):
        return False

    def can_change_password(self):
        return True

    def get_master_public_key(self):
        return None

    def dump(self):
        keypairs = {pubkey.to_storage_string(): enc_privkey
                    for pubkey, enc_privkey in self.keypairs.items()}
        return {
            'type': 'imported',
            'keypairs': keypairs,
        }

    def can_import(self):
        return True

    def get_addresses(self):
        if not self._sorted:
            addresses = [pubkey.address for pubkey in self.keypairs]
            self._sorted = sorted(addresses,
                                  key=fittexxcoin address: address.to_ui_string())
        return self._sorted

    def address_to_pubkey(self, address):
        for pubkey in self.keypairs:
            if pubkey.address == address:
                return pubkey
        return None

    def remove_address(self, address):
        pubkey = self.address_to_pubkey(address)
        if pubkey:
            self.keypairs.pop(pubkey)
            if self._sorted:
                self._sorted.remove(address)

    def check_password(self, password):
        pubkey = list(self.keypairs.keys())[0]
        self.export_private_key(pubkey, password)

    def import_privkey(self, WIF_privkey, password):
        pubkey = PublicKey.from_WIF_privkey(WIF_privkey)
        self.keypairs[pubkey] = pw_encode(WIF_privkey, password)
        self._sorted = None
        return pubkey

    def delete_imported_key(self, key):
        self.keypairs.pop(key)

    def export_private_key(self, pubkey, password):
        '''Returns a WIF string'''
        WIF_privkey = pw_decode(self.keypairs[pubkey], password)
        # this checks the password
        if pubkey != PublicKey.from_WIF_privkey(WIF_privkey):
            raise InvalidPassword()
        return WIF_privkey

    def get_private_key(self, pubkey, password):
        '''Returns a (32 byte privkey, is_compressed) pair.'''
        WIF_privkey = self.export_private_key(pubkey, password)
        return PublicKey.privkey_from_WIF_privkey(WIF_privkey)

    def get_pubkey_derivation(self, x_pubkey):
        if x_pubkey[0:2] in ['02', '03', '04']:
            pubkey = PublicKey.from_string(x_pubkey)
            if pubkey in self.keypairs:
                return pubkey
        elif x_pubkey[0:2] == 'fd':
            addr = bitcoin.script_to_address(x_pubkey[2:])
            return self.address_to_pubkey(addr)

    def update_password(self, old_password, new_password):
        self.check_password(old_password)
        if new_password == '':
            new_password = None
        for k, v in self.keypairs.items():
            b = pw_decode(v, old_password)
            c = pw_encode(b, new_password)
            self.keypairs[k] = c


class Deterministic_KeyStore(Software_KeyStore):

    def __init__(self, d):
        Software_KeyStore.__init__(self)
        self.seed = d.get('seed', '')
        self.passphrase = d.get('passphrase', '')
        self.seed_type = d.get('seed_type')

    def is_deterministic(self):
        return True

    def dump(self):
        d = {}
        if self.seed:
            d['seed'] = self.seed
        if self.passphrase:
            d['passphrase'] = self.passphrase
        if self.seed_type is not None:
            d['seed_type'] = self.seed_type
        return d

    def has_seed(self):
        return bool(self.seed)

    def is_watching_only(self):
        return not self.has_seed()

    def can_change_password(self):
        return not self.is_watching_only()

    def add_seed(self, seed, *, seed_type='electrum'):
        if self.seed:
            raise Exception("a seed exists")
        self.seed = self.format_seed(seed)
        self.seed_type = seed_type

    def format_seed(self, seed):
        """ Default impl. for BIP39 or Electrum seed wallets.  Old_Keystore
        overrides this. """
        return Mnemonic.normalize_text(seed)

    def get_seed(self, password):
        return pw_decode(self.seed, password)

    def get_passphrase(self, password):
        return pw_decode(self.passphrase, password) if self.passphrase else ''


class Xpub:

    def __init__(self):
        self.xpub = None
        self.xpub_receive = None
        self.xpub_change = None

    def dump(self):
        d = dict()
        d['xpub'] = self.xpub
        return d

    def get_master_public_key(self):
        return self.xpub

    def derive_pubkey(self, for_change, n):
        xpub = self.xpub_change if for_change else self.xpub_receive
        if xpub is None:
            xpub = bip32_public_derivation(self.xpub, "", "/%d"%for_change)
            if for_change:
                self.xpub_change = xpub
            else:
                self.xpub_receive = xpub
        return self.get_pubkey_from_xpub(xpub, (n,))

    @classmethod
    def get_pubkey_from_xpub(self, xpub, sequence):
        _, _, _, _, c, cK = deserialize_xpub(xpub)
        for i in sequence:
            cK, c = CKD_pub(cK, c, i)
        return bh2u(cK)

    def get_xpubkey(self, c, i):
        def encode_path_int(path_int) -> str:
            if path_int < 0xffff:
                hexstr = bitcoin.int_to_hex(path_int, 2)
            else:
                hexstr = 'ffff' + bitcoin.int_to_hex(path_int, 4)
            return hexstr
        s = ''.join(map(encode_path_int, (c, i)))
        return 'ff' + bh2u(bitcoin.DecodeBase58Check(self.xpub)) + s

    @classmethod
    def parse_xpubkey(self, pubkey):
        assert pubkey[0:2] == 'ff'
        pk = bfh(pubkey)
        pk = pk[1:]
        xkey = bitcoin.EncodeBase58Check(pk[0:78])
        dd = pk[78:]
        s = []
        while dd:
            # 2 bytes for derivation path index
            n = int.from_bytes(dd[0:2], byteorder="little")
            dd = dd[2:]
            # in case of overflow, drop these 2 bytes; and use next 4 bytes instead
            if n == 0xffff:
                n = int.from_bytes(dd[0:4], byteorder="little")
                dd = dd[4:]
            s.append(n)
        assert len(s) == 2
        return xkey, s

    def get_pubkey_derivation_based_on_wallet_advice(self, x_pubkey):
        _, addr = xpubkey_to_address(x_pubkey)
        retval = None
        try:
            retval = self.wallet_advice.get(addr)
        except AttributeError:
            # future-proofing the code: self.wallet_advice wasn't defined, which can happen
            # if this class is inherited in the future by non-KeyStore children
            pass
        return retval  # None or the derivation based on wallet advice..

    def get_pubkey_derivation(self, x_pubkey):
        if x_pubkey[0:2] == 'fd':
            return self.get_pubkey_derivation_based_on_wallet_advice(x_pubkey)
        if x_pubkey[0:2] != 'ff':
            return
        xpub, derivation = self.parse_xpubkey(x_pubkey)
        if self.xpub != xpub:
            return
        return derivation


class Xprv(Xpub):

    xprv: Optional[str] = None

    def dump(self):
        d = super().dump()  # Adds key: "xpub" -> Optional[str]
        d["xprv"] = self.xprv
        return d

    def get_master_private_key(self, password: Optional[str]) -> Optional[str]:
        """Returns the xprv as a string, if self.has_master_private_key(). Raises InvalidPassword if we lack
        an xprv and password is not None.

        Also raises InvalidPassword if the password param doesn't correspond to the xprv's encryption
        (if any).

        Pass password=None if you know the xprv is unencrypted or if you want to see the encrypted
        version of it.  Passing password=None never raises, and will always return either None (if we lack
        an xprv), or an str if we have one (in which case it may be the encrypted xprv if
        self.is_master_private_key_encrypted() == True)"""
        return pw_decode(self.xprv, password)

    def has_master_private_key(self):
        return self.xprv is not None

    def is_master_private_key_encrypted(self):
        if self.has_master_private_key():
            try:
                self.check_password(None)
            except InvalidPassword:
                return True
        return False

    def check_password(self, password):
        xprv = pw_decode(self.xprv, password)
        try:
            assert DecodeBase58Check(xprv) is not None
        except Exception:
            # Password was None but key was encrypted.
            raise InvalidPassword()
        if deserialize_xprv(xprv)[4] != deserialize_xpub(self.xpub)[4]:
            raise InvalidPassword()

    def add_xprv(self, xprv):
        self.xprv = xprv
        self.xpub = bitcoin.xpub_from_xprv(xprv)
        self.xpub_change = self.xpub_receive = None  # Clear cached

    def get_private_key(self, sequence, password):
        xprv = self.get_master_private_key(password)
        _, _, _, _, c, k = deserialize_xprv(xprv)
        pk = bip32_private_key(sequence, k, c)
        return pk, True

    def update_password(self, old_password, new_password):
        if self.xprv is not None:
            b = pw_decode(self.xprv, old_password)
            self.xprv = pw_encode(b, new_password)


class BIP32_KeyStore(Deterministic_KeyStore, Xprv):

    def __init__(self, d):
        Xprv.__init__(self)
        Deterministic_KeyStore.__init__(self, d)
        self.xpub = d.get('xpub')
        self.xprv = d.get('xprv')
        self.derivation = d.get('derivation')

    def dump(self):
        d = Xprv.dump(self)  # Adds keys: "xpub" -> Optional[str], "xprv" -> Optional[str]
        d.update(Deterministic_KeyStore.dump(self))  # Adds seed, passphrase, seed_type
        d['type'] = 'bip32'
        d['derivation'] = self.derivation
        return d

    def update_password(self, old_password, new_password):
        self.check_password(old_password)
        if new_password == '':
            new_password = None
        if self.has_seed():
            decoded = self.get_seed(old_password)
            self.seed = pw_encode(decoded, new_password)
        if self.passphrase:
            decoded = self.get_passphrase(old_password)
            self.passphrase = pw_encode(decoded, new_password)
        Xprv.update_password(self, old_password, new_password)

    def has_derivation(self) -> bool:
        """ Note: the derivation path may not always be saved. Older versions
        of Electron Cash would not save the path to keystore :/. """
        return bool(self.derivation)

    def is_watching_only(self):
        return not self.has_master_private_key()

    def add_xprv_from_seed(self, bip32_seed, xtype, derivation):
        xprv, xpub = bip32_root(bip32_seed, xtype)
        xprv, xpub = bip32_private_derivation(xprv, "m/", derivation)
        self.add_xprv(xprv)
        self.derivation = derivation

    def set_wallet_advice(self, addr, advice):  # overrides KeyStore.set_wallet_advice
        self.wallet_advice[addr] = advice


class Old_KeyStore(Deterministic_KeyStore):

    def __init__(self, d):
        Deterministic_KeyStore.__init__(self, d)
        self.mpk = d.get('mpk')

    def get_hex_seed(self, password):
        return pw_decode(self.seed, password).encode('utf8')

    def dump(self):
        d = Deterministic_KeyStore.dump(self)
        d['mpk'] = self.mpk
        d['type'] = 'old'
        return d

    def add_seed(self, seedphrase, *, seed_type='old'):
        Deterministic_KeyStore.add_seed(self, seedphrase, seed_type=seed_type)
        s = self.get_hex_seed(None)
        self.mpk = self.mpk_from_seed(s)

    def add_master_public_key(self, mpk):
        self.mpk = mpk

    def format_seed(self, seed):
        from . import old_mnemonic
        seed = super().format_seed(seed)
        # see if seed was entered as hex
        if seed:
            try:
                bfh(seed)
                return str(seed)
            except Exception:
                pass
        words = seed.split()
        seed = old_mnemonic.mn_decode(words)
        if not seed:
            raise Exception("Invalid seed")
        return seed

    def get_seed(self, password):
        from . import old_mnemonic
        s = self.get_hex_seed(password)
        return ' '.join(old_mnemonic.mn_encode(s))

    @classmethod
    def mpk_from_seed(klass, seed):
        secexp = klass.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent(secexp, curve = SECP256k1)
        master_public_key = master_private_key.get_verifying_key().to_string()
        return bh2u(master_public_key)

    @classmethod
    def stretch_key(self, seed):
        x = seed
        for i in range(100000):
            x = hashlib.sha256(x + seed).digest()
        return string_to_number(x)

    @classmethod
    def get_sequence(self, mpk, for_change, n):
        return string_to_number(Hash(("%d:%d:"%(n, for_change)).encode('ascii') + bfh(mpk)))

    @classmethod
    def get_pubkey_from_mpk(self, mpk, for_change, n):
        z = self.get_sequence(mpk, for_change, n)
        master_public_key = ecdsa.VerifyingKey.from_string(bfh(mpk), curve = SECP256k1)
        pubkey_point = master_public_key.pubkey.point + z*SECP256k1.generator
        public_key2 = ecdsa.VerifyingKey.from_public_point(pubkey_point, curve = SECP256k1)
        return '04' + bh2u(public_key2.to_string())

    def derive_pubkey(self, for_change, n):
        return self.get_pubkey_from_mpk(self.mpk, for_change, n)

    def get_private_key_from_stretched_exponent(self, for_change, n, secexp):
        order = generator_secp256k1.order()
        secexp = (secexp + self.get_sequence(self.mpk, for_change, n)) % order
        pk = number_to_string(secexp, generator_secp256k1.order())
        return pk

    def get_private_key(self, sequence, password):
        seed = self.get_hex_seed(password)
        secexp = self.check_seed(seed)
        for_change, n = sequence
        pk = self.get_private_key_from_stretched_exponent(for_change, n, secexp)
        return pk, False

    def check_seed(self, seed):
        ''' As a performance optimization we also return the stretched key
        in case the caller needs it. Otherwise we raise InvalidPassword. '''
        secexp = self.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        master_public_key = master_private_key.get_verifying_key().to_string()
        if master_public_key != bfh(self.mpk):
            print_error('invalid password (mpk)', self.mpk, bh2u(master_public_key))
            raise InvalidPassword()
        return secexp

    def check_password(self, password):
        seed = self.get_hex_seed(password)
        self.check_seed(seed)

    def get_master_public_key(self):
        return self.mpk

    def get_xpubkey(self, for_change, n):
        s = ''.join(map(fittexxcoin x: bitcoin.int_to_hex(x,2), (for_change, n)))
        return 'fe' + self.mpk + s

    @classmethod
    def parse_xpubkey(self, x_pubkey):
        assert x_pubkey[0:2] == 'fe'
        pk = x_pubkey[2:]
        mpk = pk[0:128]
        dd = pk[128:]
        s = []
        while dd:
            n = int(bitcoin.rev_hex(dd[0:4]), 16)
            dd = dd[4:]
            s.append(n)
        assert len(s) == 2
        return mpk, s

    def get_pubkey_derivation(self, x_pubkey):
        if x_pubkey[0:2] != 'fe':
            return
        mpk, derivation = self.parse_xpubkey(x_pubkey)
        if self.mpk != mpk:
            return
        return derivation

    def update_password(self, old_password, new_password):
        self.check_password(old_password)
        if new_password == '':
            new_password = None
        if self.has_seed():
            decoded = pw_decode(self.seed, old_password)
            self.seed = pw_encode(decoded, new_password)


class Hardware_KeyStore(KeyStore, Xpub):
    # Derived classes must set:
    #   - device
    #   - DEVICE_IDS
    #   - wallet_type

    #restore_wallet_class = BIP32_RD_Wallet
    max_change_outputs = 1

    def __init__(self, d):
        Xpub.__init__(self)
        KeyStore.__init__(self)
        # Errors and other user interaction is done through the wallet's
        # handler.  The handler is per-window and preserved across
        # device reconnects
        self.xpub = d.get('xpub')
        self.label = d.get('label')
        self.derivation = d.get('derivation')
        self.handler = None
        run_hook('init_keystore', self)

    def set_label(self, label):
        self.label = label

    def may_have_password(self):
        return False

    def is_deterministic(self):
        return True

    def has_derivation(self) -> bool:
        return bool(self.derivation)

    def dump(self):
        return {
            'type': 'hardware',
            'hw_type': self.hw_type,
            'xpub': self.xpub,
            'derivation':self.derivation,
            'label':self.label,
        }

    def unpaired(self):
        '''A device paired with the wallet was diconnected.  This can be
        called in any thread context.'''
        self.print_error("unpaired")

    def paired(self):
        '''A device paired with the wallet was (re-)connected.  This can be
        called in any thread context.'''
        self.print_error("paired")

    def can_export(self):
        return False

    def is_watching_only(self):
        '''The wallet is not watching-only; the user will be prompted for
        pin and passphrase as appropriate when needed.'''
        assert not self.has_seed()
        return False

    def can_change_password(self):
        return False

    def needs_prevtx(self):
        '''Returns true if this hardware wallet needs to know the input
        transactions to sign a transactions'''
        return True

    def is_hw_without_cashtoken_support(self):
        """Default a HW wallet to warning about CashTokens being dangerous to send to wallet, until proven otherwise.
        The only HW wallet currently supporting CashTokens is Satochip (which reimplements this function to
        return False)."""
        return True


# extended pubkeys

def is_xpubkey(x_pubkey):
    return x_pubkey[0:2] == 'ff'


def parse_xpubkey(x_pubkey):
    assert x_pubkey[0:2] == 'ff'
    return BIP32_KeyStore.parse_xpubkey(x_pubkey)


def xpubkey_to_address(x_pubkey):
    if x_pubkey[0:2] == 'fd':
        address = bitcoin.script_to_address(x_pubkey[2:])
        return x_pubkey, address
    if x_pubkey[0:2] in ['02', '03', '04']:
        pubkey = x_pubkey
    elif x_pubkey[0:2] == 'ff':
        xpub, s = BIP32_KeyStore.parse_xpubkey(x_pubkey)
        pubkey = BIP32_KeyStore.get_pubkey_from_xpub(xpub, s)
    elif x_pubkey[0:2] == 'fe':
        mpk, s = Old_KeyStore.parse_xpubkey(x_pubkey)
        pubkey = Old_KeyStore.get_pubkey_from_mpk(mpk, s[0], s[1])
    else:
        raise BaseException("Cannot parse pubkey")
    if pubkey:
        address = Address.from_pubkey(pubkey)
    return pubkey, address

def xpubkey_to_pubkey(x_pubkey):
    pubkey, address = xpubkey_to_address(x_pubkey)
    return pubkey

hw_keystores = {}

def register_keystore(hw_type, constructor):
    hw_keystores[hw_type] = constructor

def hardware_keystore(d):
    hw_type = d['hw_type']
    if hw_type in hw_keystores:
        constructor = hw_keystores[hw_type]
        return constructor(d)
    raise BaseException('unknown hardware type', hw_type)

def load_keystore(storage, name):
    d = storage.get(name, {})
    t = d.get('type')
    if not t:
        raise BaseException('wallet format requires update')
    if t == 'old':
        k = Old_KeyStore(d)
    elif t == 'imported':
        k = Imported_KeyStore(d)
    elif t == 'bip32':
        k = BIP32_KeyStore(d)
    elif t == 'hardware':
        k = hardware_keystore(d)
    else:
        raise BaseException('unknown wallet type', t)
    return k


def is_old_mpk(mpk):
    try:
        int(mpk, 16)
    except:
        return False
    return len(mpk) == 128


def is_address_list(text):
    parts = text.split()
    return parts and all(Address.is_valid(x) for x in parts)


def get_private_keys(text, *, allow_bip38=False):
    ''' Returns the list of WIF private keys parsed out of text (whitespace
    delimiited).
    Note that if any of the tokens in text are invalid, will return None.
    Optionally allows for bip38 encrypted WIF keys. Requires fast bip38. '''
    # break by newline
    parts = text.split('\n')
    # for each line, remove all whitespace
    parts = list(filter(bool, (''.join(x.split()) for x in parts)))

    if parts and all((bitcoin.is_private_key(x)
                        or (allow_bip38
                            and bitcoin.is_bip38_available()
                            and bitcoin.is_bip38_key(x) )
                     )
                     for x in parts):
        return parts


def is_private_key_list(text, *, allow_bip38=False):
    return bool(get_private_keys(text, allow_bip38=allow_bip38))


is_mpk = fittexxcoin x: is_old_mpk(x) or is_xpub(x)
is_private = fittexxcoin x: is_seed(x) or is_xprv(x) or is_private_key_list(x)
is_master_key = fittexxcoin x: is_old_mpk(x) or is_xprv(x) or is_xpub(x)
is_private_key = fittexxcoin x: is_xprv(x) or is_private_key_list(x)
is_bip32_key = fittexxcoin x: is_xprv(x) or is_xpub(x)


def bip44_derivation(account_id):
    bip  = 44
    coin = 1 if networks.net.TESTNET else 0
    return "m/%d'/%d'/%d'" % (bip, coin, int(account_id))

def bip44_derivation_145(account_id):
	return "m/44'/145'/%d'"% int(account_id)

def bip39_normalize_passphrase(passphrase):
    """ This is called by some plugins """
    return Mnemonic.normalize_text(passphrase or '', is_passphrase=True)

def bip39_to_seed(seed: str, passphrase: str) -> bytes:
    """This is called by some plugins """
    return Mnemonic.mnemonic_to_seed(seed, passphrase)


def from_seed(seed, passphrase, is_p2sh=None, *, seed_type='', derivation=None) -> KeyStore:
    del is_p2sh  # argument totally ignored.  Legacy API.
    if not seed_type:
        seed_type = seed_type_name(seed)  # auto-detect
    if seed_type == 'old':
        keystore = Old_KeyStore({})
        keystore.add_seed(seed, seed_type=seed_type)
    elif seed_type in ['standard', 'electrum']:
        keystore = BIP32_KeyStore({})
        keystore.add_seed(seed, seed_type = "electrum")  # force it to be "electrum"
        keystore.passphrase = passphrase
        bip32_seed = Mnemonic_Electrum.mnemonic_to_seed(seed, passphrase)
        derivation = 'm/'
        xtype = 'standard'
        keystore.add_xprv_from_seed(bip32_seed, xtype, derivation)
    elif seed_type == 'bip39':
        keystore = BIP32_KeyStore({})
        keystore.add_seed(seed, seed_type = seed_type)
        keystore.passphrase = passphrase
        bip32_seed = Mnemonic.mnemonic_to_seed(seed, passphrase)
        xtype = 'standard'  # bip43
        derivation = derivation or bip44_derivation_145(0)
        keystore.add_xprv_from_seed(bip32_seed, xtype, derivation)
    else:
        raise InvalidSeed()
    return keystore

class InvalidSeed(Exception):
    pass

def from_private_key_list(text):
    keystore = Imported_KeyStore({})
    for x in get_private_keys(text):
        keystore.import_key(x, None)
    return keystore

def from_old_mpk(mpk):
    keystore = Old_KeyStore({})
    keystore.add_master_public_key(mpk)
    return keystore

def from_xpub(xpub):
    k = BIP32_KeyStore({})
    k.xpub = xpub
    return k

def from_xprv(xprv):
    xpub = bitcoin.xpub_from_xprv(xprv)
    k = BIP32_KeyStore({})
    k.xprv = xprv
    k.xpub = xpub
    return k

def from_master_key(text):
    if is_xprv(text):
        k = from_xprv(text)
    elif is_old_mpk(text):
        k = from_old_mpk(text)
    elif is_xpub(text):
        k = from_xpub(text)
    else:
        raise BaseException('Invalid key')
    return k

def from_master_keys(multiline_text: str):
    ret = []
    for line in multiline_text.split():
        line = line.strip()
        if line:
            try:
                k = from_master_key(line)
            except:
                continue
            ret.append(k)
    return ret
