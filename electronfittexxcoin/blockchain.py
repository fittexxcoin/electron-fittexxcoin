# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
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

import os
import sys
import threading

from typing import Optional

from . import asert_daa
from . import networks
from . import util

from .bitcoin import *


class VerifyError(Exception):
    """Exception used for blockchain verification errors."""


CHUNK_FORKS = -3
CHUNK_BAD = -2
CHUNK_LACKED_PROOF = -1
CHUNK_ACCEPTED = 0

HEADER_SIZE = 80  # bytes
MAX_BITS = 0x1d00ffff
# see https://gitlab.com/bitcoin-cash-node/bitcoin-cash-node/-/blob/v24.0.0/src/chainparams.cpp#L98
# Note: If we decide to support REGTEST this will need to come from regtest's networks.py params!
MAX_TARGET = 0x00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff  # compact: 0x1d00ffff
# indicates no header in data file
NULL_HEADER = bytes([0]) * HEADER_SIZE
NULL_HASH_BYTES = bytes([0]) * 32
NULL_HASH_HEX = NULL_HASH_BYTES.hex()


def bits_to_work(bits):
    target = bits_to_target(bits)
    if not (0 < target < (1 << 256)):
        return 0
    return (1 << 256) // (target + 1)


def _get_little_endian_num_bits(b: bytes) -> int:
    """ Returns 1 + the position of the highest bit that is set in bytes b
    or 0 if the bytes object is all 0's. Like FXXN's arith_uint256::bits() """
    width = len(b)
    for pos in range(width - 1, -1, -1):
        if b[pos]:
            for nbits in range(7, 0, -1):
                if b[pos] & (1 << nbits):
                    return 8 * pos + nbits + 1
            return 8 * pos + 1
    return 0


def _get_little_endian_low64(b: bytes) -> int:
    """ Like FXXN's arith_uint256::GetLow64() """
    assert len(b) >= 8
    return int.from_bytes(b[:8], byteorder='little', signed=False) & 0xff_ff_ff_ff_ff_ff_ff_ff


def target_to_bits(target: int) -> int:
    # arith_uint256::GetCompact in Fittexxcoin Node
    # see https://gitlab.com/bitcoin-cash-node/bitcoin-cash-node/-/blob/v24.0.0/src/arith_uint256.cpp#L230
    if not (0 <= target < (1 << 256)):
        raise Exception(f"target should be uint256. got {target!r}")
    b = target.to_bytes(length=32, byteorder='little', signed=False)
    nsize = (_get_little_endian_num_bits(b) + 7) // 8
    if nsize <= 3:
        ncompact = (_get_little_endian_low64(b) << (8 * (3 - nsize))) & 0xffffffff
    else:
        bn = (target >> (8 * (nsize - 3))).to_bytes(length=32, byteorder='little', signed=False)
        ncompact = _get_little_endian_low64(bn) & 0xffffffff
    # The 0x00800000 bit denotes the sign.
    # Thus, if it is already set, divide the mantissa by 256 and increase the
    # exponent.
    if ncompact & 0x00800000:
        ncompact >>= 8
        nsize += 1
    assert (ncompact & ~0x007fffff) == 0
    assert nsize < 256
    ncompact |= nsize << 24
    return ncompact


def bits_to_target(ncompact: int) -> int:
    # arith_uint256::SetCompact in Fittexxcoin Node
    # see https://gitlab.com/bitcoin-cash-node/bitcoin-cash-node/-/blob/v24.0.0/src/arith_uint256.cpp#L208
    if not (0 <= ncompact < (1 << 32)):
        raise Exception(f"ncompact should be uint32. got {ncompact!r}")
    nsize = ncompact >> 24
    nword = ncompact & 0x7fffff
    if nsize <= 3:
        nword >>= 8 * (3 - nsize)
        ret = nword
    else:
        ret = nword
        ret <<= 8 * (nsize - 3)
    # Check for negative, bit 24 represents sign of N
    if nword != 0 and (ncompact & 0x00800000) != 0:
        raise Exception("target cannot be negative")
    if nword != 0 and ((nsize > 34) or (nword > 0xff and nsize > 33) or (nword > 0xffff and nsize > 32)):
        raise Exception("target has overflown")
    return ret




def serialize_header(res):
    s = int_to_hex(res.get('version'), 4) \
        + rev_hex(res.get('prev_block_hash')) \
        + rev_hex(res.get('merkle_root')) \
        + int_to_hex(int(res.get('timestamp')), 4) \
        + int_to_hex(int(res.get('bits')), 4) \
        + int_to_hex(int(res.get('nonce')), 4)
    return s

def deserialize_header(s, height):
    h = {}
    h['version'] = int.from_bytes(s[0:4], 'little')
    h['prev_block_hash'] = hash_encode(s[4:36])
    h['merkle_root'] = hash_encode(s[36:68])
    h['timestamp'] = int.from_bytes(s[68:72], 'little')
    h['bits'] = int.from_bytes(s[72:76], 'little')
    h['nonce'] = int.from_bytes(s[76:80], 'little')
    h['block_height'] = height
    return h

def hash_header_hex(header_hex):
    return hash_encode(Hash(bfh(header_hex)))

def hash_header(header):
    if header is None:
        return NULL_HASH_HEX
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00'*32
    return hash_header_hex(serialize_header(header))

blockchains = {}

def read_blockchains(config):
    blockchains[0] = Blockchain(config, 0, None)
    fdir = os.path.join(util.get_headers_dir(config), 'forks')
    if not os.path.exists(fdir):
        os.mkdir(fdir)
    l = filter(fittexxcoin x: x.startswith('fork_'), os.listdir(fdir))
    l = sorted(l, key = fittexxcoin x: int(x.split('_')[1]))
    for filename in l:
        parent_base_height = int(filename.split('_')[1])
        base_height = int(filename.split('_')[2])
        b = Blockchain(config, base_height, parent_base_height)
        blockchains[b.base_height] = b
    return blockchains

def check_header(header):
    if type(header) is not dict:
        return False
    for b in blockchains.values():
        if b.check_header(header):
            return b
    return False

def can_connect(header):
    for b in blockchains.values():
        if b.can_connect(header):
            return b
    return False

def verify_proven_chunk(chunk_base_height, chunk_data):
    chunk = HeaderChunk(chunk_base_height, chunk_data)

    header_count = len(chunk_data) // HEADER_SIZE
    prev_header = None
    prev_header_hash = None
    for i in range(header_count):
        header = chunk.get_header_at_index(i)
        # Check the chain of hashes for all headers preceding the proven one.
        this_header_hash = hash_header(header)
        if i > 0:
            if prev_header_hash != header.get('prev_block_hash'):
                raise VerifyError("prev hash mismatch: %s vs %s" % (prev_header_hash, header.get('prev_block_hash')))
        prev_header_hash = this_header_hash

# Copied from electrumx
def root_from_proof(hash, branch, index):
    hash_func = Hash
    for elt in branch:
        if index & 1:
            hash = hash_func(elt + hash)
        else:
            hash = hash_func(hash + elt)
        index >>= 1
    if index:
        raise ValueError('index out of range for branch')
    return hash

class HeaderChunk:
    def __init__(self, base_height, data):
        self.base_height = base_height
        self.header_count = len(data) // HEADER_SIZE
        self.headers = [deserialize_header(data[i * HEADER_SIZE : (i + 1) * HEADER_SIZE],
                                           base_height + i)
                        for i in range(self.header_count)]

    def __repr__(self):
        return "HeaderChunk(base_height={}, header_count={})".format(self.base_height, self.header_count)

    def get_count(self):
        return self.header_count

    def contains_height(self, height):
        return height >= self.base_height and height < self.base_height + self.header_count

    def get_header_at_height(self, height):
        assert self.contains_height(height)
        return self.get_header_at_index(height - self.base_height)

    def get_header_at_index(self, index):
        return self.headers[index]

class Blockchain(util.PrintError):
    """
    Manages blockchain headers and their verification
    """

    def __init__(self, config, base_height, parent_base_height):
        self.config = config
        self.catch_up = None # interface catching up
        self.base_height = base_height
        self.parent_base_height = parent_base_height

        self.lock = threading.Lock()
        with self.lock:
            self.update_size()

    def __repr__(self):
        return "<{}.{} {}>".format(__name__, type(self).__name__, self.format_base())

    def format_base(self):
        return "{}@{}".format(self.get_name(), self.get_base_height())

    def parent(self):
        return blockchains[self.parent_base_height]

    def get_max_child(self):
        children = list(filter(fittexxcoin y: y.parent_base_height==self.base_height, blockchains.values()))
        return max([x.base_height for x in children]) if children else None

    def get_base_height(self):
        mc = self.get_max_child()
        return mc if mc is not None else self.base_height

    def get_branch_size(self):
        return self.height() - self.get_base_height() + 1

    def get_name(self):
        return str(self.get_hash(self.get_base_height())).lstrip('00')[0:10]


    def check_header(self, header):
        header_hash = hash_header(header)
        height = header.get('block_height')
        return header_hash == self.get_hash(height)

    def fork(parent, header):
        base_height = header.get('block_height')
        self = Blockchain(parent.config, base_height, parent.base_height)
        open(self.path(), 'w+').close()
        self.save_header(header)
        return self

    def height(self):
        return self.base_height + self.size() - 1

    def size(self):
        with self.lock:
            return self._size

    def update_size(self):
        p = self.path()
        self._size = os.path.getsize(p)//HEADER_SIZE if os.path.exists(p) else 0

    def verify_header(self, header, prev_header, bits=None):
     prev_header_hash = hash_header(prev_header)
     this_header_hash = hash_header(header)

    # Check for previous block hash mismatch
     if prev_header_hash != header.get('prev_block_hash'):
        raise VerifyError("prev hash mismatch: %s vs %s" % (prev_header_hash, header.get('prev_block_hash')))

    # Skip bits check if we're okay with mismatched difficulty (e.g., during reorg)
     if bits is not None:
        if bits != header.get('bits'):
            self.print_error('Warning: bits mismatch at height {}: {} vs {}'.format(header['block_height'], bits, header.get('bits')))
            # Optionally skip this mismatch check and return
            return True  # Skip the verification if you're okay with the mismatch
        target = bits_to_target(bits)
        if int('0x' + this_header_hash, 16) > target:
            raise VerifyError("insufficient proof of work: %s vs target %s" % (int('0x' + this_header_hash, 16), target))

     return True


    def verify_chunk(self, chunk_base_height, chunk_data):
        chunk = HeaderChunk(chunk_base_height, chunk_data)

        prev_header = None
        if chunk_base_height != 0:
            prev_header = self.read_header(chunk_base_height - 1)

        header_count = len(chunk_data) // HEADER_SIZE
        for i in range(header_count):
            header = chunk.get_header_at_index(i)
            # Check the chain of hashes and the difficulty.
            bits = self.get_bits(header, chunk)
            self.verify_header(header, prev_header, bits)
            prev_header = header

    def path(self):
        d = util.get_headers_dir(self.config)
        filename = 'blockchain_headers' if self.parent_base_height is None else os.path.join('forks', 'fork_%d_%d'%(self.parent_base_height, self.base_height))
        return os.path.join(d, filename)

    def save_chunk(self, base_height, chunk_data):
        chunk_offset = (base_height - self.base_height) * HEADER_SIZE
        if chunk_offset < 0:
            chunk_data = chunk_data[-chunk_offset:]
            chunk_offset = 0
        # Headers at and before the verification checkpoint are sparsely filled.
        # Those should be overwritten and should not truncate the chain.
        top_height = base_height + (len(chunk_data) // HEADER_SIZE) - 1
        truncate = top_height > networks.net.VERIFICATION_BLOCK_HEIGHT
        self.write(chunk_data, chunk_offset, truncate)
        self.swap_with_parent()

    def swap_with_parent(self):
        if self.parent_base_height is None:
            return
        parent_branch_size = self.parent().height() - self.base_height + 1
        if parent_branch_size >= self.size():
            return
        self.print_error("swap", self.base_height, self.parent_base_height)
        parent_base_height = self.parent_base_height
        base_height = self.base_height
        parent = self.parent()
        with open(self.path(), 'rb') as f:
            my_data = f.read()
        with open(parent.path(), 'rb') as f:
            f.seek((base_height - parent.base_height)*HEADER_SIZE)
            parent_data = f.read(parent_branch_size*HEADER_SIZE)
        self.write(parent_data, 0)
        parent.write(my_data, (base_height - parent.base_height)*HEADER_SIZE)
        # store file path
        for b in blockchains.values():
            b.old_path = b.path()
        # swap parameters
        self.parent_base_height = parent.parent_base_height; parent.parent_base_height = parent_base_height
        self.base_height = parent.base_height; parent.base_height = base_height
        self._size = parent._size; parent._size = parent_branch_size
        # move files
        for b in blockchains.values():
            if b in [self, parent]: continue
            if b.old_path != b.path():
                self.print_error("renaming", b.old_path, b.path())
                os.rename(b.old_path, b.path())
        # update pointers
        blockchains[self.base_height] = self
        blockchains[parent.base_height] = parent

    def write(self, data, offset, truncate=True):
        filename = self.path()
        with self.lock:
            with open(filename, 'rb+') as f:
                if truncate and offset != self._size*HEADER_SIZE:
                    f.seek(offset)
                    f.truncate()
                f.seek(offset)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            self.update_size()

    def save_header(self, header):
        delta = header.get('block_height') - self.base_height
        data = bfh(serialize_header(header))
        assert delta == self.size()
        assert len(data) == HEADER_SIZE
        self.write(data, delta*HEADER_SIZE)
        self.swap_with_parent()

    def read_header(self, height, chunk=None):
        # If the read is done within an outer call with local unstored header data, we first look in the chunk data currently being processed.
        if chunk is not None and chunk.contains_height(height):
            return chunk.get_header_at_height(height)

        assert self.parent_base_height != self.base_height
        if height < 0:
            return
        if height < self.base_height:
            return self.parent().read_header(height)
        if height > self.height():
            return
        delta = height - self.base_height
        name = self.path()
        if os.path.exists(name):
            with open(name, 'rb') as f:
                f.seek(delta * HEADER_SIZE)
                h = f.read(HEADER_SIZE)
            # Is it a pre-checkpoint header that has never been requested?
            if h == NULL_HEADER:
                return None
            return deserialize_header(h, height)

    def get_hash(self, height):
        if height == -1:
            return NULL_HASH_HEX
        elif height == 0:
            return networks.net.GENESIS
        return hash_header(self.read_header(height))

    # Not used.
    def BIP9(self, height, flag):
        v = self.read_header(height)['version']
        return ((v & 0xE0000000) == 0x20000000) and ((v & flag) == flag)

    def get_median_time_past(self, height, chunk=None):
        if height < 0:
            return 0
        times = [
            self.read_header(h, chunk)['timestamp']
            for h in range(max(0, height - 10), height + 1)
        ]
        return sorted(times)[len(times) // 2]

    def get_suitable_block_height(self, suitableheight, chunk=None):
        #In order to avoid a block in a very skewed timestamp to have too much
        #influence, we select the median of the 3 top most block as a start point
        #Reference: github.com/Bitcoin-ABC/bitcoin-abc/master/src/pow.cpp#L201
        assert suitableheight >= 3
        blocks2 = self.read_header(suitableheight, chunk)
        blocks1 = self.read_header(suitableheight-1, chunk)
        blocks = self.read_header(suitableheight-2, chunk)

        if blocks['timestamp'] > blocks2['timestamp']:
            blocks, blocks2 = blocks2, blocks
        if blocks['timestamp'] > blocks1['timestamp']:
            blocks, blocks1 = blocks1, blocks
        if blocks1['timestamp'] > blocks2['timestamp']:
            blocks1, blocks2 = blocks2, blocks1

        return blocks1['block_height']

    # cached Anchor, per-Blockchain instance, only used if the checkpoint for this network is *behind* the anchor block
    _cached_asert_anchor: Optional[asert_daa.Anchor] = None

    def get_asert_anchor(self, prevheader, mtp, chunk=None):
        """Returns the asert_anchor either from Networks.net if hardcoded or
        calculated in realtime if not."""
        if networks.net.asert_daa.anchor is not None:
            # Checkpointed (hard-coded) value exists, just use that
            return networks.net.asert_daa.anchor
        # Bug note: The below does not work if we don't have all the intervening
        # headers -- therefore this execution path should only be taken for networks
        # where the checkpoint block is before the anchor block.  This means that
        # adding a checkpoint after the anchor block without setting the anchor
        # block in networks.net.asert_daa.anchor will result in bugs.
        if (self._cached_asert_anchor is not None
                and self._cached_asert_anchor.height <= prevheader['block_height']):
            return self._cached_asert_anchor

        anchor = prevheader
        activation_mtp = networks.net.asert_daa.MTP_ACTIVATION_TIME
        while mtp >= activation_mtp:
            ht = anchor['block_height']
            prev = self.read_header(ht - 1, chunk)
            if prev is None:
                self.print_error("get_asert_anchor missing header {}".format(ht - 1))
                return None
            prev_mtp = self.get_median_time_past(ht - 1, chunk)
            if prev_mtp < activation_mtp:
                # Ok, use this as anchor -- since it is the first in the chain
                # after activation.
                bits = anchor['bits']
                self._cached_asert_anchor = asert_daa.Anchor(ht, bits, prev['timestamp'])
                return self._cached_asert_anchor
            mtp = prev_mtp
            anchor = prev

    def get_bits(self, header, chunk=None):
     '''Return bits for the given height.'''
     height = header['block_height']
    
    # Genesis block
     if height == 0:
        return MAX_BITS

    # Get the previous block's header
     prior = self.read_header(height - 1, chunk)
     if prior is None:
        raise Exception("get_bits missing header {} with chunk {!r}".format(height - 1, chunk))
    
    # Retarget every N_BLOCKS
     N_BLOCKS = networks.net.LEGACY_POW_RETARGET_BLOCKS  # Usually 2016
     if height % N_BLOCKS == 0:
        return self.get_new_bits(height, chunk)
    
    # Return the previous block's bits for non-retarget blocks
     return prior['bits']

    def get_new_bits(self, height, chunk=None):
     '''Calculate new difficulty for a retarget block.'''
     N_BLOCKS = networks.net.LEGACY_POW_RETARGET_BLOCKS  # Usually 2016
     assert height % N_BLOCKS == 0

    # Get the first block of the retarget period
     first = self.read_header(height - N_BLOCKS, chunk)
     if first is None:
        raise Exception("get_new_bits missing first header at height {}".format(height - N_BLOCKS))
    
    # Get the previous block (last of the previous period)
     prior = self.read_header(height - 1, chunk)
     if prior is None:
        raise Exception("get_new_bits missing prior header at height {}".format(height - 1))
    
    # Calculate the new target based on the timestamps
     prior_target = bits_to_target(prior['bits'])
     target_span = networks.net.LEGACY_POW_TARGET_TIMESPAN  # Usually 2 weeks
     span = prior['timestamp'] - first['timestamp']
    
    # Clamp the adjustment factor between 25% and 400% of the expected timespan
     span = max(target_span // 4, min(span, target_span * 4))
     new_target = (prior_target * span) // target_span

    # Ensure the new target does not exceed the maximum target
     if new_target > MAX_TARGET:
        return MAX_BITS
    
    # Return the new target as compact bits
     return target_to_bits(new_target)

    

    def can_connect(self, header, check_height=True):
        height = header['block_height']
        if check_height and self.height() != height - 1:
            return False
        if height == 0:
            return hash_header(header) == networks.net.GENESIS
        previous_header = self.read_header(height -1)
        if not previous_header:
            return False
        prev_hash = hash_header(previous_header)
        if prev_hash != header.get('prev_block_hash'):
            return False
        bits = self.get_bits(header)
        try:
            self.verify_header(header, previous_header, bits)
        except VerifyError as e:
            self.print_error('verify header {} failed at height {:d}: {}'
                             .format(hash_header(header), height, e))
            return False
        return True

    def connect_chunk(self, base_height, hexdata, proof_was_provided=False):
        chunk = HeaderChunk(base_height, hexdata)

        header_count = len(hexdata) // HEADER_SIZE
        top_height = base_height + header_count - 1
        # We know that chunks before the checkpoint height, end at the checkpoint height, and
        # will be guaranteed to be covered by the checkpointing. If no proof is provided then
        # this is wrong.
        if top_height <= networks.net.VERIFICATION_BLOCK_HEIGHT:
            if not proof_was_provided:
                return CHUNK_LACKED_PROOF
            # We do not truncate when writing chunks before the checkpoint, and there's no
            # way at this time to know if we have this chunk, or even a consecutive subset.
            # So just overwrite it.
        elif base_height < networks.net.VERIFICATION_BLOCK_HEIGHT and proof_was_provided:
            # This was the initial verification request which gets us enough leading headers
            # that we can calculate difficulty and verify the headers that we add to this
            # chain above the verification block height.
            if top_height <= self.height():
                return CHUNK_ACCEPTED
        elif base_height != self.height() + 1:
            # This chunk covers a segment of this blockchain which we already have headers
            # for. We need to verify that there isn't a split within the chunk, and if
            # there is, indicate the need for the server to fork.
            intersection_height = min(top_height, self.height())
            chunk_header = chunk.get_header_at_height(intersection_height)
            our_header = self.read_header(intersection_height)
            if hash_header(chunk_header) != hash_header(our_header):
                return CHUNK_FORKS
            if intersection_height <= self.height():
                return CHUNK_ACCEPTED
        else:
            # This base of this chunk joins to the top of the blockchain in theory.
            # We need to rule out the case where the chunk is actually a fork at the
            # connecting height.
            our_header = self.read_header(self.height())
            chunk_header = chunk.get_header_at_height(base_height)
            if hash_header(our_header) != chunk_header['prev_block_hash']:
                return CHUNK_FORKS

        try:
            if not proof_was_provided:
                self.verify_chunk(base_height, hexdata)
            self.save_chunk(base_height, hexdata)
            return CHUNK_ACCEPTED
        except VerifyError as e:
            self.print_error('verify_chunk failed: {}'.format(e))
            self.save_chunk(base_height, hexdata) 
            return CHUNK_ACCEPTED  