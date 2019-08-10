# dino.struct - data structures used in DINO objects

from bisect import bisect_left

from .structparse import StructParser, HOST_ENDIAN
from .const import MAGIC_V0, Arch, HeaderEncoding, ObjectType, CompressionID
from .const import SectionType, SectionFlags

__all__ = [
    'Dhdrp',
    'Shdrp',
    'StringTable',
]

# Make StructParser objects for the things we know about
Dhdrp = StructParser('Dhdr', endian='little')
Dhdrp.add_field("magic",           "4s", choices=(MAGIC_V0,), default=MAGIC_V0)
Dhdrp.add_field("version",          "B", choices=(0,),        default=0)
Dhdrp.add_field("arch",             "B", type=Arch,           default=0)
Dhdrp.add_field("encoding",         "B", type=HeaderEncoding, default=0)
Dhdrp.add_field("objtype",          "B", type=ObjectType,     default=0)
Dhdrp.add_field("compression_id",   "B", type=CompressionID,  default=0)
Dhdrp.add_field("compression_opts", "B", default=0)
Dhdrp.add_field("reserved",         "B", default=0)
Dhdrp.add_field("section_count",    "B")
Dhdrp.add_field("sectab_size",      "H")
Dhdrp.add_field("namtab_size",      "H")

Shdrp = StructParser('Shdr', endian='little')
# TODO: we could rearrange this and have name be a 32-bit "id" field, and
# reserve 0xffff0000-0xffffffff so if id & 0xffff0000 then the "name" is
# Nametable.get(s.id & 0x0000ffff)
Shdrp.add_field("name",     "H", default=0)
Shdrp.add_field("stype",    "B", type=SectionType,  default=0)
Shdrp.add_field("flags",    "B", type=SectionFlags, default=0)
Shdrp.add_field("info",     "I", default=0)
Shdrp.add_field("size",     "I", default=0)
Shdrp.add_field("count",    "I", default=0)


assert Shdrp.structsize == 16, f"Shdrp.structsize = {Shdrp.structsize}"
assert Dhdrp.structsize == 16, f"Dhdrp.structsize = {Dhdrp.structsize}"

# TODO: if StructParser was smarter about its argument types we could probably
# also describe the indexes here. But this might already be too clever anyway.

# TODO: I know this is probably _wildly_ inefficient, and probably the
# in-memory representation could just be a list of str so we don't have to
# repeatedly decode() on get(). But the point here is to experiment with the
# file format - a Real Implementation (tm) would be calling out to C/Rust code
# through the FFI or a CPython module.
class StringTable(object):
    # Really more of a heap/bag/set than a Table, but that's what ELF calls
    # it, so let's not confuse things...
    def __init__(self, data=None):
        self._data = data or bytearray()
        self._ends = list(self.iter_ends())

    def size(self):
        return len(self._data)

    def add(self, s):
        b = s.encode('utf8')+b'\0'
        i = self._data.find(b)
        if i == -1:
            i = len(self._data)
            self._data.extend(b)
            self._ends.append(len(self._data)-1)
        return i

    def get(self, i):
        if i < self.size():
            # find the range of bytes from i to the nearest string ending
            b = self._data[i:self._ends[bisect_left(self._ends,i)]]
            return b.decode('utf8')

    def pack(self):
        return bytes(self._data)

    def iter_ends(self):
        start = 0
        while True:
            end = self._data.find(b'\0', start)
            if end == -1:
                break
            yield end
            start = end + 1
