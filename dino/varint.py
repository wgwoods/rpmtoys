# dino.varint - variable-length integer encoding/decoding

__all__ = [
    'VARINT_MAXLEN',
    'VARINT_MAXVAL',
    'VARINT_MAXVAL_WIDTH',
    'varint_encode',
    'varint_decode',
    'varint_iter_decode',
]

from ctypes import c_ulonglong as uintmax
from ctypes import sizeof


VARINT_NBITS = 8 * sizeof(uintmax)
VARINT_MAXLEN = (VARINT_NBITS // 7) + 1
VARINT_MAXVAL = uintmax(~0).value
VARINT_MAXVAL_WIDTH = [
                  0x80-1, # 127
                0x4080-1, # 16511
              0x204080-1, # 2113663
            0x10204080-1, # 270549119
          0x0810204080-1, # 34630287487
        0x040810204080-1, # 4432676798591
      0x02040810204080-1, # 567382630219903
    0x0102040810204080-1, # 72624976668147839
    0x8102040810204080-1, # 9295997013522923647
]
VARINT_MS7B_MASK = 127 << (VARINT_NBITS - 7)

def varint_encode(val):
    '''Encode integer val to a varint byte sequence.'''
    # Force val to be a uintmax value
    val = uintmax(val).value
    # TODO: this is a very C-style way to do this. Could probably be more
    # pythonic and/or more efficient..
    varint = bytearray(VARINT_MAXLEN)
    pos = len(varint) - 1
    varint[pos] = val & 127
    val = val >> 7
    while val:
        val -= 1
        pos -= 1
        varint[pos] = 128 | (val & 127)
        val = val >> 7
    return bytes(varint[pos:])

def varint_decode(varint):
    '''Decode the varint byte sequence and return (val, nbytes)'''
    b = varint[0]
    val = b & 127
    n = 1
    while (b & 128):
        if (val & VARINT_MS7B_MASK):
            raise ValueError("varint overflow")
        val += 1
        b = varint[n]
        n += 1
        val = (val << 7) + (b & 127)
    return val, n

def varint_iter_decode(data, maxcount=None):
    end = len(data)
    itemsleft = maxcount if maxcount else end
    data = memoryview(data)
    pos = 0
    while itemsleft and pos < end:
        val, size = varint_decode(data[pos:])
        yield val, size
        pos += size
        itemsleft -= 1

def varint_str(varint):
    varint_bytes = [f"{'+' if b & 128 else '.'}{b&127:02x}" for b in varint]
    return '{' + ''.join(varint_bytes) + '}'


if __name__ == '__main__':
    assert (varint_encode(0) == b'\0'), "varint_encode(0) != b'\0'"
    assert (varint_decode(b'\0') == (0,1))
    assert (varint_encode(127) == b'\x7f')
    varint = varint_encode(128)
    varexp = b'\x80\x00'
    assert (varint == varexp), f"{varint_str(varint)} != {varint_str(varexp)}"
    for width, val in enumerate(VARINT_MAXVAL_WIDTH,1):
        vmax = varint_encode(val)
        vnext = varint_encode(val + 1)
        assert (len(vmax) == width)
        assert (len(vnext) == width + 1)
        d_vmax, w_vmax = varint_decode(vmax)
        d_vnext, w_vnext = varint_decode(vnext)
        assert (d_vmax == val), f'{d_vmax} != {val}'
        assert (d_vnext == val + 1), f'{d_vnext} != {val+1}'
        assert (w_vmax == width)
        assert (w_vnext == width + 1)

    vmax = varint_encode(VARINT_MAXVAL)
    assert(len(vmax) == VARINT_MAXLEN)
    assert(varint_decode(vmax)[0] == VARINT_MAXVAL)
