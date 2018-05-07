# rpmtoys.file - RPM file metadata
#
# Allow extra whitespace around '=' to make enum tables line up:
# pylama:ignore=E221

from enum import IntFlag

class Attrs(IntFlag):
    NONE      = 0
    CONFIG    = (1 << 0)
    DOC       = (1 << 1)
    ICON      = (1 << 2)
    MISSINGOK = (1 << 3)
    NOREPLACE = (1 << 4)
    SPECFILE  = (1 << 5)
    GHOST     = (1 << 6)
    LICENSE   = (1 << 7)
    README    = (1 << 8)
    # bits 9-10 unused
    PUBKEY    = (1 << 11)
    ARTIFACT  = (1 << 12)

class VerifyAttrs(IntFlag):
    NONE       = 0
    FILEDIGEST = (1 << 0)
    FILESIZE   = (1 << 1)
    LINKTO     = (1 << 2)
    USER       = (1 << 3)
    GROUP      = (1 << 4)
    MTIME      = (1 << 5)
    MODE       = (1 << 6)
    RDEV       = (1 << 7)
    CAPS       = (1 << 8)
    # bits 9-14 unused, "reserved for VerifyAttrs"
    CONTEXTS   = (1 << 15)
    # bits 16-22 "used in rpmVerifyFlags" (?)
    # bits 23-27 "used in rpmQueryFlags"
    READLINKFAIL = (1 << 28)
    READFAIL   = (1 << 29)
    LSTATFAIL  = (1 << 30)
    LGETFILECONFAIL = (1 << 31)

    FAILURES = LSTATFAIL | READFAIL | READLINKFAIL | LGETFILECONFAIL
    ALL = 0xffffffff
    VERIFYMASK = (FILEDIGEST | FILESIZE | LINKTO | USER | GROUP | MTIME | MODE |
                  RDEV | CAPS | CONTEXTS)

    FLAGMASK = (FILEDIGEST | FILESIZE | LINKTO | USER | GROUP | MTIME | MODE |
                RDEV | CAPS | CONTEXTS | FAILURES)
