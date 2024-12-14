# Electron Cash - lightweight Lambda client
# Copyright (C) 2011 thomasv@gitorious
# Copyright (C) 2017 Neil Booth
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

import json
import pkgutil

from .asert_daa import ASERTDaa, Anchor

def _read_json_dict(filename):
    try:
        data = pkgutil.get_data(__name__, filename)
        r = json.loads(data.decode('utf-8'))
    except:
        r = {}
    return r

class AbstractNet:
    TESTNET = False
    LEGACY_POW_TARGET_TIMESPAN = 14 * 24 * 60 * 60   # 2 weeks
    LEGACY_POW_TARGET_INTERVAL = 10 * 60  # 10 minutes
    LEGACY_POW_RETARGET_BLOCKS = LEGACY_POW_TARGET_TIMESPAN // LEGACY_POW_TARGET_INTERVAL  # 2016 blocks
    BASE_UNITS = {'RXD': 8, 'mRXD': 5, 'photons': 0}
    DEFAULT_UNIT = "RXD"


class MainNet(AbstractNet):
    TESTNET = False
    WIF_PREFIX = 0x80
    ADDRTYPE_P2PKH = 0
    ADDRTYPE_P2SH = 5
    CASHADDR_PREFIX = "bitcoincash"
    RPA_PREFIX = "paycode"
    HEADERS_URL = "http://bitcoincash.com/files/blockchain_headers"  # Unused
    GENESIS = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    GENESIS1 = 1
    DEFAULT_PORTS = {'t': '50001', 's': '50002'}
    DEFAULT_SERVERS = _read_json_dict('servers.json')  # DO NOT MODIFY IN CLIENT CODE
    TITLE = 'Electron lambda'
    NO_RETARGETING = None

    # Lambda fork block specification

    # Nov 13. 2017 HF to CW144 DAA height (height of last block mined on old DAA)
    CW144_HEIGHT = 504031

    # Note: this is not the Merkle root of the verification block itself , but a Merkle root of
    # all blockchain headers up until and including this block. To get this value you need to
    # connect to an ElectrumX server you trust and issue it a protocol command. This can be
    # done in the console as follows:
    #Lam
    #    network.synchronous_get(("blockchain.block.header", [height, height]))
    #
    # Consult the ElectrumX documentation for more details.
    VERIFICATION_BLOCK_MERKLE_ROOT = "1a9a5a04194efc88310e0ad517f4fe536080f2a9c8bb8e2745654495e8b8e346"
    VERIFICATION_BLOCK_HEIGHT =2017
    asert_daa = ASERTDaa(is_testnet=False)
    # Note: We *must* specify the anchor if the checkpoint is after the anchor, due to the way
    # blockchain.py skips headers after the checkpoint.  So all instances that have a checkpoint
    # after the anchor must specify the anchor as well.
    asert_daa.anchor = Anchor(height=2016, bits=486604799, prev_time=1657404650)

    # Version numbers for BIP32 extended keys
    # standard: xprv, xpub
    XPRV_HEADERS = {
        'standard': 0x0488ade4,
    }

    XPUB_HEADERS = {
        'standard': 0x0488b21e,
    }


class TestNet(AbstractNet):
    TESTNET = True
    WIF_PREFIX = 0xef
    ADDRTYPE_P2PKH = 111
    ADDRTYPE_P2SH = 196
    CASHADDR_PREFIX = "bchtest"
    RPA_PREFIX = "paycodetest"
    HEADERS_URL = "http://bitcoincash.com/files/testnet_headers"  # Unused
    GENESIS = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    DEFAULT_PORTS = {'t':'51001', 's':'51002'}
    DEFAULT_SERVERS = _read_json_dict('servers_testnet.json')  # DO NOT MODIFY IN CLIENT CODE
    TITLE = 'Electron Radiant Testnet'
    BASE_UNITS = {'tRXD': 8, 'mtRXD': 5, 'tbits': 2}
    DEFAULT_UNIT = "tRXD"

    # Nov 13. 2017 HF to CW144 DAA height (height of last block mined on old DAA)
    CW144_HEIGHT = 1188697

    # Lambda fork block specification
    

    VERIFICATION_BLOCK_MERKLE_ROOT = ""
    VERIFICATION_BLOCK_HEIGHT = None
    asert_daa = ASERTDaa(is_testnet=True)
    asert_daa.anchor = Anchor(height=33000, bits=453224288, prev_time=1657404650)

    # Version numbers for BIP32 extended keys
    # standard: tprv, tpub
    XPRV_HEADERS = {
        'standard': 0x04358394,
    }

    XPUB_HEADERS = {
        'standard': 0x043587cf,
    }


class TestNet4(TestNet):
    GENESIS = "000000001dd410c49a788668ce26751718cc797474d3152a5fc073dd44fd9f7b"
    TITLE = 'Electron Cash Testnet4'

    HEADERS_URL = "http://bitcoincash.com/files/testnet4_headers"  # Unused

    DEFAULT_SERVERS = _read_json_dict('servers_testnet4.json')  # DO NOT MODIFY IN CLIENT CODE
    DEFAULT_PORTS = {'t': '62001', 's': '62002'}

    

    # Nov 13. 2017 HF to CW144 DAA height (height of last block mined on old DAA)
    CW144_HEIGHT = 3000

    VERIFICATION_BLOCK_MERKLE_ROOT = "e4cd956daecf2a1d2894954bb479f09e6d2d488e470ed59e1af6a329170597d6"
    VERIFICATION_BLOCK_HEIGHT = 68611
    asert_daa = ASERTDaa(is_testnet=True)  # Redeclare to get instance for this subclass
    asert_daa.anchor = Anchor(height=16844, bits=453224288, prev_time=1657404650)


class ScaleNet(TestNet):
    GENESIS = "00000000e6453dc2dfe1ffa19023f86002eb11dbb8e87d0291a4599f0430be52"
    TITLE = 'Electron Cash Scalenet'
    BASE_UNITS = {'sRXD': 8, 'msRXD': 5, 'sbits': 2}
    DEFAULT_UNIT = "tRXD"


    HEADERS_URL = "http://bitcoincash.com/files/scalenet_headers"  # Unused

    DEFAULT_SERVERS = _read_json_dict('servers_scalenet.json')  # DO NOT MODIFY IN CLIENT CODE
    DEFAULT_PORTS = {'t': '63001', 's': '63002'}

    

    # Nov 13. 2017 HF to CW144 DAA height (height of last block mined on old DAA)
    CW144_HEIGHT = 3000

    VERIFICATION_BLOCK_MERKLE_ROOT = ""
    VERIFICATION_BLOCK_HEIGHT = None
    asert_daa = ASERTDaa(is_testnet=False)  # Despite being a "testnet", ScaleNet uses 2d half-life
    asert_daa.anchor = None  # Intentionally not specified because it's after checkpoint; blockchain.py will calculate


# All new code should access this to get the current network config.
net = MainNet


def _set_units():
    from . import util
    util.base_units = net.BASE_UNITS.copy()
    util.DEFAULT_BASE_UNIT = net.DEFAULT_UNIT
    util.recalc_base_units()


def set_mainnet():
    global net
    net = MainNet
    _set_units()


def set_testnet():
    global net
    net = TestNet
    _set_units()


def set_testnet4():
    global net
    net = TestNet4
    _set_units()


def set_scalenet():
    global net
    net = ScaleNet
    _set_units()


# Compatibility
def _instancer(cls):
    return cls()


@_instancer
class NetworkConstants:
    ''' Compatibility class for old code such as extant plugins.

    Client code can just do things like:
    NetworkConstants.ADDRTYPE_P2PKH, NetworkConstants.DEFAULT_PORTS, etc.

    We have transitioned away from this class. All new code should use the
    'net' global variable above instead. '''
    def __getattribute__(self, name):
        return getattr(net, name)

    def __setattr__(self, name, value):
        raise RuntimeError('NetworkConstants does not support setting attributes! ({}={})'.format(name,value))
        #setattr(net, name, value)