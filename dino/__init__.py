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
from .struct import Dhdrp, Shdrp, StringTable, SectionTable

# FIXME: re-export the good bits
__all__ = [
    'Arch',
    'DINO',
]

###### AND FINALLY: THE ACTUAL DINO OBJECT THAT YOU WANT TO USE ######

class DINO(object):
    MAGIC = MAGIC_V0
    VERSION = 0
    def __init__(self,
                 arch=Arch(0),
                 encoding=HeaderEncoding(0),
                 objtype=ObjectType(0),
                 compression_id=CompressionID(0)):
        self.arch = arch
        self.encoding = encoding
        self.objtype = objtype
        self.compression_id = compression_id
        self.compression_opts = 0    # TODO: proper compression_opts
        self.sectab = SectionTable() # TODO: just use a list?
        self.namtab = StringTable()  # TODO: special NameTable object?

    def sections(self):
        for sec in self.sectab:
            name = ''
            if sec.name_idx != NAME_IDX_NONE:
                name = self.namtab.get(sec.name_idx)
            yield (name, sec)

    def add_section(self, section, name=None):
        if name:
            section.name_idx = self.namtab.add(name)
        else:
            section.name_idx = NAME_IDX_NONE
        return self.sectab.add(section)

    # TODO: this needs a progress callback or something...
    def write_to(self, fobj):
        wrote = 0
        wrote += fobj.write(self.pack_dhdr())
        wrote += fobj.write(self.sectab.pack())
        wrote += fobj.write(self.namtab.pack())
        for n,(name,sec) in enumerate(self.sections()):
            # FIXME: pass through the compressor?
            wrote += sec.write_to(fobj)
        return wrote

    def get_compressor(self, level=None):
        # TODO: this should probably be in a dino.compression module..
        # FIXME: should be using self.compression_opts...
        if self.compression_id == CompressionID.ZSTD:
            import zstandard as zstd
            if level and level < 0:
                level = zstd.MAX_COMPRESSION_LEVEL
            cctx = zstd.ZstdCompressor(write_content_size=True, level=level)
            return cctx
        elif self.compression_id == CompressionID.XZ:
            import lzma
            if level and level < 0:
                level = 9
            # TODO: this doesn't support zstd's copy_stream function.
            # Might need a wrapper object to make the different compressors
            # all play nice, while still making sure they can flush and
            # start a new compression frame when needed..
            cctx = lzma.LZMACompressor(preset=level)
            return cctx
        else:
            raise ValueError(f"{self.compression_id} not implemented!")

    def pack_dhdr(self):
        return Dhdrp._struct.pack(self.MAGIC,
                                  self.VERSION,
                                  self.arch,
                                  self.encoding,
                                  self.objtype,
                                  self.compression_id,
                                  self.compression_opts,
                                  0, # reserved, always 0
                                  self.sectab.count(),
                                  self.sectab.size(),
                                  self.namtab.size())
    def pack(self):
        return self.pack_dhdr() + self.sectab.pack() + self.namtab.pack()

    def hdrsize(self):
        return Dhdrp._struct.size + self.sectab.size() + self.namtab.size()

    # TODO: read headers from a .dino file
    # TODO: interface to read section data (w/decompression)
