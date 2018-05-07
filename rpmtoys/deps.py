# rpmtoys.deps - Dependency metadata.

from collections import namedtuple
from enum import IntFlag

# These are from depinfo_s and depTypes[] in rpm/lib/rpmds.c
DepInfo = namedtuple("DepInfo", "name char nametag vertag flagtag idxtag")

deptypes = [
    DepInfo('Provides',         'P', 1047, 1113, 1112, None),
    DepInfo('Requires',         'R', 1049, 1050, 1048, None),
    DepInfo('Conflicts',        'C', 1054, 1055, 1053, None),
    DepInfo('Obsoletes',        'O', 1090, 1115, 1114, None),
    DepInfo('Supplements',      'S', 5052, 5053, 5054, None),
    DepInfo('Enhances',         'e', 5055, 5056, 5057, None),
    DepInfo('Recommends',       'r', 5046, 5047, 5048, None),
    DepInfo('Suggests',         's', 5049, 5050, 5051, None),
    DepInfo('Order',            'o', 5035, 5036, 5037, None),
    DepInfo('Trigger',          't', 1066, 1067, 1068, 1069),
    DepInfo('Filetrigger',      'f', 5069, 5071, 5072, 5070),
    DepInfo('Transfiletrigger', 'F', 5079, 5081, 5082, 5080),
    DepInfo('Oldsuggests',      '?', 1156, 1157, 1158, None),
    DepInfo('Oldenhances',      '?', 1159, 1160, 1161, None),
]

depinfo = {ident:d for d in deptypes for ident in (d.name, d.char)}
char2name = {d.char:d.name for d in deptypes if d.char != '?'}

# This comes from rpmsenseFlags in rpm/lib/rpmds.h
class DepFlags(IntFlag):
    # pylama:ignore=E221
    ANY           = 0
    UNUSED_SERIAL = (1 << 0)
    LESS          = (1 << 1)
    GREATER       = (1 << 2)
    EQUAL         = (1 << 3)
    # bit 4 unused
    POSTTRANS     = (1 << 5)
    PREREQ        = (1 << 6)
    PRETRANS      = (1 << 7)
    INTERP        = (1 << 8)
    SCRIPT_PRE    = (1 << 9)
    SCRIPT_POST   = (1 << 10)
    SCRIPT_PREUN  = (1 << 11)
    SCRIPT_POSTUN = (1 << 12)
    SCRIPT_VERIFY = (1 << 13)
    FIND_REQUIRES = (1 << 14)
    FIND_PROVIDES = (1 << 15)
    TRIGGERIN     = (1 << 16)
    TRIGGERUN     = (1 << 17)
    TRIGGERPOSTUN = (1 << 18)
    MISSINGOK     = (1 << 19)
    # bit 20-23 unused
    RPMLIB        = (1 << 24)
    TRIGGERPREIN  = (1 << 25)
    KEYRING       = (1 << 26)
    # bit 27 unused
    CONFIG        = (1 << 28)
    # bit 29-31 unused

    SENSEMASK = UNUSED_SERIAL | LESS | GREATER | EQUAL
    TRIGGER = TRIGGERPREIN | TRIGGERIN | TRIGGERUN | TRIGGERPOSTUN
