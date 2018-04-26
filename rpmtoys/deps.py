# Dependency metadata.

from collections import namedtuple
from enum import IntFlag, auto

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

depinfo = {d.name:d for d in deptypes}
char2name = {d.char:d.name for d in deptypes if d.char != '?'}

# This comes from rpmsenseFlags_e in rpm/lib/rpmds.h
class Flags(IntFlag):
    ANY = 0
    unused_1 = auto()
    LESS = auto()
    GREATER = auto()
    EQUAL = auto()
    unused_4 = auto()
    POSTTRANS = auto()
    PREREQ = auto()
    PRETRANS = auto()
    INTERP = auto()
    SCRIPT_PRE = auto()
    SCRIPT_POST = auto()
    SCRIPT_PREUN = auto()
    SCRIPT_POSTUN = auto()
    SCRIPT_VERIFY = auto()
    FIND_REQUIRES = auto()
    FIND_PROVIDES = auto()
    TRIGGERIN = auto()
    TRIGGERUN = auto()
    TRIGGERPOSTUN = auto()
    MISSINGOK = auto()
    unused_20 = auto()
    unused_21 = auto()
    unused_22 = auto()
    unused_23 = auto()
    RPMLIB = auto()
    TRIGGERPREIN = auto()
    KEYRING = auto()
    unused_27 = auto()
    CONFIG = auto()

    SENSEMASK = unused_1 | LESS | GREATER | EQUAL
    TRIGGER = TRIGGERPREIN | TRIGGERIN | TRIGGERUN | TRIGGERPOSTUN
