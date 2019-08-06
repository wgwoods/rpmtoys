# dino.const - HERE'S A BUNCHA CONSTANTS / ENUMS, YEAH

from enum import IntEnum, IntFlag, auto

# Magic bytes
MAGIC_V0 = 0xedabeef0

# Special name_idx value that means "no name"
NAME_IDX_NONE = 0xffff

class CompressionID(IntEnum):
    NONE = 0
    ZLIB = 1
    LZMA = 2
    LZO  = 3
    XZ   = 4
    LZ4  = 5
    ZSTD = 6

class DigestID(IntEnum):
    UNKNOWN   = 0
    MD5       = 1
    SHA1      = 2
    RIPEMD160 = 3
    # ???     = 4 # Unused in rpmpgp.h:pgpHashAlgo enum
    # MD2     = 5 # Broken in 2004, unsupported
    TIGER192  = 6
    # HAVAL   = 7 # Broken in 2004, unsupported
    SHA256    = 8
    SHA384    = 9
    SHA512    = 10
    SHA224    = 11

# e_machine numbers from elf.h; not exhaustive, but if you want to port this
# to the PDP-11 then you're welcome to add it here
class Arch(IntEnum):
    NONE    = 0
    SPARC   = 2
    X86     = 3
    MIPS    = 8
    PPC     = 20
    PPC64   = 21
    S390    = 22
    ARM     = 40
    ALPHA   = 41
    SH      = 42
    SPARCV9 = 43
    IA64    = 50
    MIPSX   = 51
    X86_64  = 62
    NDS32   = 167
    AARCH64 = 183
    RISCV   = 243

class HeaderEncoding(IntFlag):
    DEFAULT     = 0b00000000 # Big-endian; 32-bit offsets
    LE          = 0b00000001 # TODO: little-endian
    OFF64       = 0b00000010 # TODO: 64-bit section sizes

class ObjectType(IntEnum):
    Unknown     = 0
    Archive     = auto()
    DynImage    = auto()
    Component   = auto()
    Application = auto()
    Dump        = auto()

assert int(ObjectType.Archive) == 1, "enum.auto() is busted"

class SectionType(IntEnum):
    Null         = 0      # Empty/non-existent section

    # Generic data sections
    Blob         = auto() # An opaque blob of binary data
    Index        = auto() # An index table for another section
    StringTable  = auto() # TODO: Strings prefixed with varint length
    CStringTable = auto() # NUL-terminated string table, like ELF
    Note         = auto() # ELF-style generic notes

    Provs        = auto() # TODO: Dependency metadata: Provides
    Deps         = auto() # TODO: Dependency metadata: Requires, etc

    # Object contents/payload
    Filesys      = auto() # TODO: A filesystem image or archive

    # TODO: finish defining our file container/archive format(s)
    FileData     = auto() # TODO: File contents (binary blobs)
    #FileStat     = auto() # TODO: Filesystem-level file metadata (mode etc)
    #FileTree     = auto() # TODO: File names / directory contents / etc.
    #FileMeta     = auto() # TODO: File metadata

    # TODO: Build data
    #BuildData    = auto() # TODO: Build objects

    # TODO: Package-level data
    #PkgInfo      = auto() # TODO: Human-readable package info
    #PkgData      = auto() # TODO: Machine-parseable package data


    # 0x60-0x6f are reserved for OS-specific extensions

    # 0x70-0x7f are reserved for backwards/cross-compat with external tools
    RPMHdr       = 0x7f # RPM headers (either sig or hdr)

    # 0x80-0xff are reserved for user extensions. Have fun!

    # Aliases for the low/high end of the reserved ranges
    LoOS         = 0x60
    HiOS         = 0x6f
    LoExt        = 0x70
    HiExt        = 0x7f
    LoUser       = 0x80
    HiUser       = 0xff

class SectionFlags(IntFlag):
    NONE       = 0b00000000
    COMPRESSED = 0b00000001
