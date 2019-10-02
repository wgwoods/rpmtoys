# dino.section - classes representing DINO file sections

from io import BytesIO
from struct import Struct
from collections import Counter
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from enum import IntFlag

from .util import copy_stream
from .const import SectionFlags, SectionType, NAME_IDX_NONE
from .varint import varint_encode, varint_iter_decode
from .dstruct import Shdrp
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

    def _parse_info(self):
        pass

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

    def write_to(self, fobj):
        oldpos = self.fobj.tell()
        self.fobj.seek(0)
        r = copy_stream(self.fobj, fobj, size=self.size)
        self.fobj.seek(oldpos)
        return r

class IndexFlags(IntFlag):
    NONE     = 0
    NoFanout = 1 << 0
    Off64    = 1 << 1
    UncSize  = 1 << 2

@dataclass
class IndexInfo:
    othersec: int = 0
    keysize: int = 0
    fanout: bool = True
    off64: bool = False
    unc_size: bool = True

    @property
    def flags(self):
        return (IndexFlags.NONE |
                (not self.fanout and IndexFlags.NoFanout) |
                (self.off64 and IndexFlags.Off64) |
                (self.unc_size and IndexFlags.UncSize))

    def to_int(self):
        if self.othersec < 0 or self.othersec > 0xff:
            raise ValueError(f"invalid othersec {self.othersec}")
        if self.keysize < 0 or self.keysize > 0xff:
            raise ValueError(f"invalid keysize {self.keysize}")
        return (self.keysize | (self.othersec << 8) | (int(self.flags) << 16))

    @classmethod
    def from_int(cls, info):
        flags = IndexFlags((info >> 16) & 0xff)
        return cls(keysize=info & 0xff,
                   othersec=(info >> 8) & 0xff,
                   fanout=IndexFlags.NoFanout not in flags,
                   off64=IndexFlags.Off64 in flags,
                   unc_size=IndexFlags.UncSize in flags)

# FIXME use logging for this!!
DEBUG=1
if DEBUG:
    def dprint(*args, **kwargs):
        print(*args, **kwargs)
else:
    def dprint(*args, **kwargs):
        pass



# TODO: make fanout and sizes optional
class IndexSection(BaseSection):
    '''
    A section containing an index / lookup table with offsets into another
    section. (Think git packfile indexes.)
    '''
    typeid = SectionType.Index
    datatype = dict

    def __init__(self, *args, othersec=None, othersec_idx=None, keysize=32,
                 fanout=True, off64=False, unc_size=True, varint=False,
                 endian='<', **kwargs):
        # TODO: flag for whether or not there's a full fanout table
        #       (so we can skip it for small indexes)
        # TODO: flag for varint encoding of offsets/sizes
        BaseSection.__init__(self, *args, **kwargs)
        if not (othersec_idx or isinstance(othersec, BaseSection)):
            raise ValueError("expected BaseSection, got {type(othersec)}")

        # these control the output encoding and can be set/changed whenever
        self.endian = endian
        self.fanout = fanout
        self.varint = varint
        # off64 is an output encoding setting that gets set automatically
        # if a 64-bit offset/size is added
        self._off64 = off64
        # keysize and unc_size can't be changed once an index is created
        self._keysize = keysize
        self._unc_size = unc_size
        # references to the section we're an index over
        self._othersec = othersec
        self._othersec_idx = othersec_idx

        # set up
        self._key_s = Struct(f'{self._keysize}s')
        valfmt = ('L' if off64 else 'I') * (3 if unc_size else 2)
        self._val_s = Struct(f'{self.endian}{valfmt}')
        self._fanout_s = Struct(f'{self.endian}256I')

        if unc_size:
            self.add = self.add3
        else:
            self.add = self.add2

    @property
    def keysize(self):
        return self._keysize

    @staticmethod
    def parse_info(info):
        return IndexInfo.from_int(info)

    @classmethod
    def from_hdr(cls, shdr):
        info = cls.parse_info(shdr.info)
        return cls(name_idx=shdr.name,
                   flags=shdr.flags,
                   othersec_idx=info.othersec,
                   keysize=info.keysize,
                   fanout=info.fanout,
                   off64=info.off64,
                   unc_size=info.unc_size,
                   varint=bool(shdr.flags & SectionFlags.VARINT))

    @property
    def count(self):
        return len(self._data)

    @property
    def size(self):
        if self.varint:
            return (len(self.make_fanout()) +
                    (self.count*self.keysize) +
                    sum(len(varint_encode(i)) for v in self.values() for i in v))
        else:
            return (self._fanout_s.size +
                    self.count*(self.keysize + self._val_s.size))

    @property
    def info(self):
        return IndexInfo(keysize=self.keysize,
                         othersec=self.othersec.idx if self.othersec else 0xff,
                         fanout=self.fanout,
                         unc_size=self._unc_size,
                         off64=self._off64).to_int()

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

    def add2(self, key, offset, size):
        self._data[self._key_s.pack(key)] = (offset, size)

    def add3(self, key, offset, size, uncsize):
        self._data[self._key_s.pack(key)] = (offset, size, uncsize)

    def remove(self, key):
        del self._data[key]

    def make_fanout(self):
        counts = Counter(k[0] for k in self.keys())
        if self.varint:
            # varint-encoded fanout just gives the counts for each byte
            return self._varint_pack(*[counts[b] for b in range(256)])
        else:
            fanout = [0] * 257
            for i in range(256):
                fanout[i+1] = fanout[i] + counts[i]
            return self._fanout_s.pack(*fanout[1:])

    def _varint_pack(self, *values):
        return b''.join(varint_encode(i) for i in values)

    @property
    def keysize(self):
        return self._key_s.size

    def write_to(self, fobj):
        if self.count == 0:
            return 0
        dprint(f"writing index: fanout={self.fanout} varint={self.varint} "
               f"unc_size={self._unc_size} keysize={self.keysize} "
               f"count={self.count}")
        wrote = 0
        if self.fanout:
            wrote += fobj.write(self.make_fanout())
        keys, vals = zip(*(sorted(self.items())))
        dprint(f"  fanout: {wrote:7} bytes")

        prevpos = wrote
        for k in keys:
            wrote += fobj.write(self._key_s.pack(k))
        dprint(f"    keys: {wrote-prevpos:7} bytes")

        if self.varint:
            valpack = self._varint_pack
        else:
            valpack = self._val_s.pack

        prevpos = wrote
        for v in vals:
            wrote += fobj.write(valpack(*v))
        dprint(f"    vals: {wrote-prevpos:7} bytes")
        dprint(f"   total: {wrote:7} bytes")

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

        dprint(f"reading index: fanout={self.fanout} varint={self.varint} "
               f"unc_size={self._unc_size} keysize={self.keysize} "
               f"count={self.count}")

        data = fobj.read(size)
        keypos = 0
        if self.fanout:
            if self.varint:
                # NOTE: varint-encoded fanout is a sequence of counts, not a
                # running count..
                fv = 0
                for v, n in varint_iter_decode(data, 256):
                    fv += v
                    keypos += n
                    fanout.append(fv)
            else:
                keypos = self._fanout_s.size
                fanout = self._fanout_s.unpack(data[0:keypos])
            if count:
                assert count == fanout[-1]
            dprint(f"  fanout: {keypos:7} bytes, count={fanout[-1]}")
        keylen = self.keysize * count
        valpos = keypos + keylen
        keydata = data[keypos:valpos]
        valdata = data[valpos:]
        dprint(f"    keys: {valpos-keypos:7} bytes")
        dprint(f"    vals: {len(valdata):7} bytes")
        keys = [i[0] for i in self._key_s.iter_unpack(keydata)]
        if self.varint:
            vals = [i[0] for i in varint_iter_decode(valdata)]
            n, m = divmod(len(vals), count)
            assert (m == 0), "Incorrect/corrupt index"
            vals = [tuple(vals[i:i+n]) for i in range(0,len(vals),n)]
        else:
            if (len(valdata) % self._val_s.size):
                print(f"wtf: size {self._val_s.size} * count {count} != {len(valdata)}")
            vals = self._val_s.iter_unpack(valdata)
        self._data = self.datatype(zip(keys, vals))

class RPMSection(BlobSection):
    '''A section containing one or more RPM headers.'''
    typeid = SectionType.RPMHdr

class FilesysSection(BlobSection):
    '''A section containing a filesystem image.'''
    typeid = SectionType.Filesys

class FileDataSection(BlobSection):
    '''A section containing packed file data.'''
    typeid = SectionType.FileData
