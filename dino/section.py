# dino.section - classes representing DINO file sections

from io import BytesIO
from struct import Struct
from collections import Counter
from tempfile import SpooledTemporaryFile

from .util import copy_stream
from .const import SectionFlags, SectionType, NAME_IDX_NONE
from .struct import Shdrp

class BaseSection(object):
    '''Abstract base class for holding section data.'''
    typeid = NotImplemented
    datatype = NotImplemented

    def __init__(self, initval=None, info=0, flags=SectionFlags.NONE):
        self._data = self.datatype(initval) if initval is not None else self.datatype()
        self._flags = flags
        self._info = info
        self._sectab = None
        self.name_idx = NAME_IDX_NONE

    @property
    def flags(self):
        return self._flags

    @property
    def info(self):
        return self._info

    @property
    def size(self):
        return 0

    @property
    def count(self):
        return 0

    @property
    def idx(self):
        if self._sectab:
            return self._sectab.index(self)

    @property
    def fobj(self):
        return None

    # I dunno about this, since we might need to instantiate the object before
    # we can correctly read from the file...
    @classmethod
    def from_file(cls, fobj, size=None):
        return cls()

    def pack_hdr(self, sectab):
        return Shdrp._struct.pack(self.name_idx, self.typeid, self.flags,
                                  self.info,     self.size,   self.count)

    def write_to(self, fobj):
        self.fobj.seek(0)
        return copy_stream(self.fobj, fobj, size=self.size)

    def tobytes(self):
        b = BytesIO()
        self.write_to(b)
        return b.getvalue()


class NullSection(BaseSection):
    '''A null section, containing no data.'''
    typeid = SectionType.Null
    datatype = type(None)

class BlobSectionBytes(BaseSection):
    '''A section containing a blob of data, resident in memory'''
    typeid = SectionType.Blob
    datatype = BytesIO

    @property
    def fobj(self):
        return self._data

    @property
    def size(self):
        return len(self._data)

    @classmethod
    def from_file(cls, fobj, size=None):
        return cls(fobj.read(size))

class BlobSection(BaseSection):
    '''A section containing a blob of data, stored in a temporary file'''
    typeid = SectionType.Blob
    datatype = lambda s: SpooledTemporaryFile(max_size=16*1024, mode='w+b')

    @property
    def fobj(self):
        return self._data

    @property
    def size(self):
        try:
            # If it's not using an actual file, we can get the buffer size
            return len(self._data._file.getbuffer())
        except AttributeError:
            # Otherwise use seek() to find the end of the file
            oldpos = self._data.tell()
            self._data.seek(0,2)
            size = self._data.tell()
            self._data.seek(oldpos)
            return size

    @classmethod
    def from_file(cls, fobj, size=None):
        # TODO: copy file contents? mmap?
        raise NotImplementedError

# TODO: make fanout and sizes optional
class IndexSection(BaseSection):
    '''
    A section containing an index / lookup table with offsets into another
    section. (Think git packfile indexes.)
    '''
    typeid = SectionType.Index
    datatype = dict
    offset_sfmt = 'II'
    fanout_sfmt = '256I'
    info_sfmt = 'xxBB'

    def __init__(self, *args, othersec=None, keysize=32, endian='<', **kwargs):
        # TODO: flag for whether or not there's a full fanout table
        #       (so we can skip it for small indexes)
        # TODO: flag for whether we have offsets and sizes or just offsets
        # TODO: flag for varint encoding of offsets/sizes
        if not isinstance(othersec, BaseSection):
            raise ValueError("expected BaseSection, got {type(othersec)}")
        BaseSection.__init__(self, *args, **kwargs)
        self.keysize = keysize
        self.othersec = othersec
        self.endian = endian
        self._key_s = Struct(f'{self.endian}{self.keysize}s')
        self._offset_s = Struct(f'{self.endian}{self.offset_sfmt}')
        self._fanout_s = Struct(f'{self.endian}{self.fanout_sfmt}')
        self._info_s = Struct(f'{self.endian}{self.info_sfmt}')

    @property
    def count(self):
        return len(self._data)

    @property
    def size(self):
        return (self._fanout_s.size +
                self.count*(self._key_s.size + self._offset_s.size))

    @property
    def info(self):
        return ((0xff & self.keysize) |
               ((0xff & self.othersec.idx) << 8))

    def setinfo(self, info):
        self.keysize = info & 0xff
        otheridx = (info >> 8) & 0xff
        # TODO: this seems inelegant..
        self.othersec = self._sectab[otheridx]

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data

    def add(self, key, offset, size):
        self._data[self._key_s.pack(key)] = (offset, size)

    def remove(self, key):
        del self._data[key]

    def make_fanout(self):
        counts = Counter(k[0] for k in self.keys())
        fanout = [0] * 257
        for i in range(256):
            fanout[i+1] = fanout[i] + counts[i]
        return self._fanout_s.pack(*fanout[1:])

    def write_to(self, fobj):
        wrote = 0
        wrote += fobj.write(self.make_fanout())
        assert wrote == self._fanout_s.size
        for k in sorted(self.keys()):
            wrote += fobj.write(self._key_s.pack(k))
        assert wrote == self._fanout_s.size + self.count * (self._key_s.size)
        for o in sorted(self.values()):
            wrote += fobj.write(self._offset_s.pack(*o))
        assert wrote == self.size
        return wrote

    def read_from(self, fobj, size=None):
        # It's a little silly that we unpack this data structure into native
        # python data structures rather than using it directly, but the
        # native structures *seem* to perform better, and this is really
        # just a rapid-devel prototype anyway.
        # A real implementation of this would be native code in a library
        # that we use via the FFI or something.
        fanout = self._fanout_s.unpack(fobj.read(self._fanout_s.size))
        keycount = fanout[-1]
        keys = self._key_s.iter_unpack(fobj.read(self._key_s.size * keycount))
        offs = self._offset_s.iter_unpack(fobj.read(self._offset_s.size * keycount))
        self._data = self.datatype(zip(keys, offs))
        return self

class RPMSection(BlobSection):
    '''A section containing one or more RPM headers.'''
    typeid = SectionType.RPMHdr

class FilesysSection(BlobSection):
    '''A section containing a filesystem image.'''
    typeid = SectionType.Filesys

class FileDataSection(BlobSection):
    '''A section containing packed file data.'''
    typeid = SectionType.FileData
