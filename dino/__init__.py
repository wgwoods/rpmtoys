# dino - Dynamic Image Network Objects. Yeah, that's it...
#
# Copyright (c) 2019, Red Hat, Inc.
#
# GPLv3 boilerplate should go here.
#
# Author: Will Woods <wwoods@redhat.com>

'''
So, DINO is my codename (pet name?) for a reworked repository/package format.

It's a weird little experimental sandbox where I'm playing with various
ideas about how to make building images safe, reliable, efficient, and fast.

The design is strongly influenced by ELF, RPM, git packfiles, and squashfs.
Further inspiration came from ostree, solaris-ips, conary, and _lots_ of beer.

Important features include file-level deduplication, random file access,
http-friendly packfile layout, small binary indexes, and easy extensibility
for both future features (like file/object deltas) and backwards compatibility
(like storing unmodified RPM headers so we can spit out almost-pristine RPMs).

The code itself is UNFINISHED, UNRELIABLE, UNDOCUMENTED, and UUUUGLY.
It's a heap of gross hacks that I've thrown together to prototype / smoke-test
the file format and evaluate whether the design concepts are even viable.

KNOWN BUGS/LIMITATIONS:
    * 64-bit sizes/offsets are not yet supported, so don't try to make
      anything bigger than 4GB
    * IndexSection is much larger than needed for small data sets
'''

from .const import *
from .section import *
from .dstruct import Dhdrp, Shdrp, StringTable
from .compression import get_compressor, get_decompressor

# This only exports the public-facing stuff enums and classes.
__all__ = [
    # Constants/enums
    'Arch', 'CompressionID', 'DigestID', 'HeaderEncoding', 'ObjectType',
    'SectionType', 'SectionFlags',
    # Section objects
    'NullSection', 'BlobSection', 'BlobSectionBytes', 'IndexSection',
    'RPMSection', 'FilesysSection', 'FileDataSection',
    # The big boy
    'DINO',
]

class DINOError(Exception):
    pass

class DINO(object):
    MAGIC = MAGIC_V0
    VERSION = 0
    def __init__(self,
                 arch=Arch(0),
                 encoding=HeaderEncoding(0),
                 objtype=ObjectType(0),
                 compression_id=CompressionID(0)):
        self._encoding = None
        self.Dhdrp = Dhdrp
        self.Shdrp = Shdrp
        self.arch = Arch(arch)
        self.encoding = HeaderEncoding(encoding)
        self.objtype = ObjectType(objtype)
        self.compression_id = CompressionID(compression_id)
        self.compression_opts = 0    # TODO: proper compression_opts
        self.sectab = list()
        self.namtab = StringTable()  # TODO: special NameTable object?

    @classmethod
    def from_path(cls, path):
        return cls.from_file(open(path, 'rb'))

    @classmethod
    def from_file(cls, fobj):
        d, dhdr, sectab, namtab = cls.read_hdrs(fobj)
        d.namtab = namtab
        # Make section objects and populate sectab
        for shdr in sectab:
            ThisSection = sectionclass(shdr.stype)
            sec = ThisSection.from_hdr(shdr)
            d.add_section(sec)
        # Now that the sections are all in sectab they can load properly
        pos = fobj.tell()
        for shdr, (name, sec) in zip(sectab, d.sections()):
            sec.from_file(fobj, size=shdr.size, count=shdr.count)
            pos = fobj.seek(pos+shdr.size)
        # We're good to go!
        return d

    @classmethod
    def read_dhdr(cls, fobj):
        # Read bytes, check endianness, re-parse if needed
        dhdr_bytes = fobj.read(Dhdrp.structsize)
        dhdr = Dhdrp.LE.parse_bytes(dhdr_bytes)
        if dhdr.encoding & HeaderEncoding.BE:
            dhdr = Dhdrp.BE.parse_bytes(dhdr_bytes)
        # Check magic and version
        if dhdr.magic != cls.MAGIC:
            raise DINOError(f"Bad magic {dhdr.magic}")
        if dhdr.version > cls.VERSION:
            raise DINOError(f"Unknown version {dhdr.version}")
        # We're good, return a new object with dhdr fields set
        d = cls(arch=dhdr.arch,
                encoding=dhdr.encoding,
                objtype=dhdr.objtype,
                compression_id=dhdr.compression_id)
        return d, dhdr

    @classmethod
    def read_hdrs(cls, fobj):
        d, dhdr = cls.read_dhdr(fobj)
        sectab = list(d.Shdrp.iter_read_from(fobj, dhdr.sectab_size))
        namtab = StringTable(fobj.read(dhdr.namtab_size))
        return d, dhdr, sectab, namtab

    @property
    def encoding(self):
        return self._encoding

    @encoding.setter
    def encoding(self, enc):
        enc = HeaderEncoding(enc)
        if enc & HeaderEncoding.BE:
            self.Dhdrp, self.Shdrp = Dhdrp.BE, Shdrp.BE
        else:
            self.Dhdrp, self.Shdrp = Dhdrp.LE, Shdrp.LE
        self._encoding = enc

    def sections(self):
        '''Generate (name, section) for each section in the section table.'''
        for sec in self.sectab:
            name = self.namtab.get(sec.name_idx)
            yield (name, sec)

    def findsections(self, name=None, suffix=None, type=None):
        '''
        Generate each section in this object's section table.
        Setting `name`, `suffix`, or `type` will generate only sections that
        match the given constraints.
        '''
        # If we got a 'type', turn that into a typeid
        typeid = None
        if type:
            if issubclass(type, BaseSection) or isinstance(type, BaseSection):
                typeid = type.typeid
            else:
                typeid = SectionType(type)
        for secname, sec in self.sections():
            if ((not typeid or sec.typeid == typeid) and
                (not name or name == secname) and
                (not suffix or secname.endswith(suffix))):
                yield (name, sec)

    def findsection(self, name=None, suffix=None, type=None):
        '''Return the first section matching the constraints.'''
        for secname, sec in self.findsections(name=name, suffix=suffix, type=type):
            return sec

    def add_section(self, section, name=None):
        section._dino = self
        idx = len(self.sectab)
        self.sectab.append(section)
        if name:
            self.name_section(section, name)
        return idx

    def name_section(self, section, name):
        name_idx = self.namtab.add(name)
        section.name_idx = self.namtab.add(name)

    def section_index(self, section):
        if section in self.sectab:
            return self.sectab.index(section)

    # TODO: this needs a progress callback or something...
    def write_to(self, fobj):
        wrote = fobj.write(self.pack_hdrs())
        for sec in self.sectab:
            # FIXME: pass through the compressor if that flag is set
            # compr = self.get_compressor()
            wrote += sec.write_to(fobj)
        return wrote

    def get_compressor(self, level=None):
        # TODO: compression_opts!
        return get_compressor(self.compression_id, level=level)

    def get_decompressor(self):
        return get_decompressor(self.compression_id)

    def pack_dhdr(self):
        return Dhdrp._struct.pack(self.MAGIC,
                                  self.VERSION,
                                  self.arch,
                                  self.encoding,
                                  self.objtype,
                                  self.compression_id,
                                  self.compression_opts,
                                  0, # reserved, always 0
                                  len(self.sectab),
                                  len(self.sectab) * Shdrp.structsize,
                                  self.namtab.size())

    def pack_hdrs(self):
        return (self.pack_dhdr() +
                b''.join(sec.pack_hdr() for sec in self.sectab) +
                self.namtab.pack())

    def hdrsize(self):
        return Dhdrp._struct.size + self.sectab.size() + self.namtab.size()

    # TODO: read headers from a .dino file
    # TODO: interface to read section data (w/decompression)
