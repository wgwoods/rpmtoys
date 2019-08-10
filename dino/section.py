# dino.section - classes representing DINO file sections

from io import BytesIO
from struct import Struct
from collections import Counter
from tempfile import SpooledTemporaryFile

from .util import copy_stream
from .const import SectionFlags, SectionType, NAME_IDX_NONE
from .struct import Shdrp
from .fileview import FileView

class BaseSection(object):
    '''Abstract base class for holding section data.'''
    typeid = NotImplemented
    datatype = NotImplemented

    def __init__(self,
                 initval=None,
                 info=0,
                 flags=SectionFlags.NONE,
                 name_idx=NAME_IDX_NONE):
        self._data = self.datatype(initval) if initval is not None else self.datatype()
        self._flags = flags
        self._info = info
        self.name_idx = name_idx
        self._dino = None
        self._sectab = None
        self._shdr = None

    @classmethod
    def from_hdr(cls, shdr):
        return cls(name_idx=shdr.name,
                   flags=shdr.flags,
                   info=shdr.info)

    def from_file(self, fobj, size, count=0):
        raise NotImplementedError

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
        if self._dino:
            return self._dino.section_index(self)

    @property
    def name(self):
        if self._dino:
            return self._dino.namtab.get(self.name_idx)

    @property
    def fobj(self):
        return None

    def pack_hdr(self):
        return Shdrp._struct.pack(self.name_idx, self.typeid, self.flags,
                                  self.info,     self.size,   self.count)

    def write_to(self, fobj):
        self.fobj.seek(0)
        return copy_stream(self.fobj, fobj, size=self.size)

    def tobytes(self):
        b = BytesIO()
        self.write_to(b)
        return b.getvalue()


def subclasses(cls):
    subc = set(cls.__subclasses__())
    return subc.union(set(c for s in subc for c in subclasses(s)))

def sectionclass(typeid):
    for s in subclasses(BaseSection):
        if s.typeid == typeid:
            return s

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

    def from_file(self, fobj, size, count=0):
        self._data = fobj.read(size)

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

    def from_file(self, fobj, size, count=0):
        # TODO: This FileView object kinda sucks.
        # Maybe we should just make dino objects mmap-able?
        self._data = FileView(fobj, fobj.tell(), size)

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

    def __init__(self, *args, othersec=None, othersec_idx=None, keysize=32, endian='<', **kwargs):
        # TODO: flag for whether or not there's a full fanout table
        #       (so we can skip it for small indexes)
        # TODO: flag for whether we have offsets and sizes or just offsets
        # TODO: flag for varint encoding of offsets/sizes
        BaseSection.__init__(self, *args, **kwargs)
        if not (othersec_idx or isinstance(othersec, BaseSection)):
            raise ValueError("expected BaseSection, got {type(othersec)}")
        self.keysize = keysize
        self.endian = endian
        self._othersec = othersec
        self._othersec_idx = othersec_idx
        self._key_s = Struct(f'{self.endian}{self.keysize}s')
        self._offset_s = Struct(f'{self.endian}{self.offset_sfmt}')
        self._fanout_s = Struct(f'{self.endian}{self.fanout_sfmt}')

    @classmethod
    def from_hdr(cls, shdr):
        keysize = shdr.info & 0xff
        othersec_idx = (shdr.info >> 8) & 0xff
        return cls(name_idx=shdr.name,
                   flags=shdr.flags,
                   keysize=keysize,
                   othersec_idx=othersec_idx)

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

    @property
    def othersec(self):
        if self._othersec is None:
            if self._dino and self._othersec_idx:
                self._othersec = self._dino.sectab[self._othersec_idx]
        return self._othersec

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
        #log.debug(f'{self.idx:3}: {self.__class__.__name__} {self.name!r}: {self.count} keys')
        if self.count == 0:
            return 0
        # TODO: if count is small we should skip fanout..
        wrote = fobj.write(self.make_fanout())
        keys, offsets = zip(*(sorted(self.items())))
        for k in keys:
            wrote += fobj.write(self._key_s.pack(k))
        for n,o in enumerate(offsets):
            wrote += fobj.write(self._offset_s.pack(*o))
        return wrote

    def from_file(self, fobj, size, count=0):
        # It's a little silly that we unpack this data structure into native
        # python data structures rather than using it directly, but the
        # native structures *seem* to perform better, and this is really
        # just a rapid-devel prototype anyway.
        # A real implementation of this would be native code in a library
        # that we use via the FFI or something.
        if size == 0:
            self._data = self.datatype()
            return
        fanout = self._fanout_s.unpack(fobj.read(self._fanout_s.size))
        keycount = fanout[-1]
        if count:
            assert keycount == count
        keys = [i[0] for i in self._key_s.iter_unpack(fobj.read(self.keysize*keycount))]
        offs = self._offset_s.iter_unpack(fobj.read(self._offset_s.size * keycount))
        self._data = self.datatype(zip(keys, offs))

class RPMSection(BlobSection):
    '''A section containing one or more RPM headers.'''
    typeid = SectionType.RPMHdr

class FilesysSection(BlobSection):
    '''A section containing a filesystem image.'''
    typeid = SectionType.Filesys

class FileDataSection(BlobSection):
    '''A section containing packed file data.'''
    typeid = SectionType.FileData
