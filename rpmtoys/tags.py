# rpmtoys/tags.py - RPM tag metadata (meta-metadata!)
# Copyright (C) 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Will Woods <wwoods@redhat.com>

from enum import IntEnum
from .tagtbl import tagtbl
from .sigtagtbl import sigtagtbl

class VType(IntEnum):
    '''RPM Value Type - see rpm/lib/rpmtag.h:rpmTagType_e'''
    NULL = 0
    CHAR = 1
    INT8 = 2
    INT16 = 3
    INT32 = 4
    INT64 = 5
    STRING = 6
    BIN = 7
    STRING_ARRAY = 8
    I18NSTRING = 9
    MAX = 9
    MASK = 0x0000ffff

class RType(IntEnum):
    '''RPM Return Type - see rpm/lib/rpmtag.h:rpmTagReturnType_e'''
    ANY = 0
    SCALAR = 0x00010000
    ARRAY = 0x00020000
    MAPPING = 0x00040000
    MASK = 0xffff0000

class TagEnum(IntEnum):
    '''
    RPM tag info - see rpm/lib/tagname.c:headerTagTableEntry_s
    All members are subclasses of 'int', with the following extra attributes:

    name: the symbol name for this tag
    shortname: human-readable short name for this tag
    vtype: expected type of this tag's value(s)
    rtype: expected "return type" of this tag: SCALAR, ARRAY, or MAPPING
    extension: bool; is this tag a non-standard "extension"?
    '''
    def __new__(cls, info):
        name, num, vtype, rtype, ext = info
        tag = int.__new__(cls, num)
        tag._value_ = num
        tag.shortname = name  # non-upper() string
        tag.vtype = VType[vtype]
        tag.rtype = RType[rtype]
        tag.extension = bool(ext)
        return tag

    @classmethod
    def getname(self, num):
        try:
            return self(num).name
        except ValueError:
            return str(num)

    @classmethod
    def byprefix(self, pfx):
        if type(pfx) == str:
            return {t for t in Tag if t.name.startswith(pfx.upper())}
        else:
            return {t for p in pfx for t in self.byprefix(p)}

# Fill in the "Tag" enum from tagtbl data.
# NOTE: The enum member names are all uppercase versions of the "shortname"
# (he human-readable version of the name - see rpm:lib/tagname.c
# NOTE: we sort tagtbl so that the longest name comes first for each numeric
# value, because the longest name is always the canonical name.
# (rpm/lib/tagname.c:tagCmpValue() is where that gets done in RPM.)
Tag = TagEnum('Tag', ((t[0].upper(), t) for t in
                      sorted(tagtbl, key=lambda t:len(t[0]), reverse=True)))

# Similarly, construct SigTag from sigtagtbl data.
SigTag = TagEnum('SigTag', ((t[0].upper(), t) for t in
                   sorted(sigtagtbl, key=lambda t:len(t[0]), reverse=True)))

# --- Below here we have a bunch of tag metadata (meta-metadata?)

# Tags that have binary values
BIN_TAGS = {t for t in Tag if t.vtype == VType.BIN}
SIG_BIN_TAGS = {t for t in SigTag if t.vtype == VType.BIN}
# Tags that have non-array values
SCALAR_TAGS = {t for t in Tag if t.rtype == RType.SCALAR}
SIG_SCALAR_TAGS = {t for t in SigTag if t.rtype == RType.SCALAR}
# Tags that have array values with one item per file
PER_FILE_TAGS = {
    Tag.FILESIZES,
    Tag.FILEMODES,
    Tag.FILERDEVS,
    Tag.FILEMTIMES,
    Tag.FILEDIGESTS,
    Tag.FILELINKTOS,
    Tag.FILEFLAGS,
    Tag.FILEUSERNAME,
    Tag.FILEGROUPNAME,
    Tag.FILEVERIFYFLAGS,
    Tag.FILEDEVICES,
    Tag.FILEINODES,
    Tag.FILELANGS,
    Tag.DIRINDEXES,
    Tag.BASENAMES,
    Tag.FILECOLORS,
    Tag.FILECLASS,
    Tag.FILEDEPENDSX,
    Tag.FILEDEPENDSN,
    Tag.FILECAPS,
    Tag.FILESIGNATURES, # XXX unverified
    # Tag.PREFIXES?
}

# Group dependencies by type. Note that the names are a _prefix_ for a bunch of
# tags that get zipped together inside RPM to create each dependency "item".
# (See the DepInfo table in deps, which actually lists the exact tags used.)
DEPENDENCY_GROUPS = {
    "BASIC": ["Provide", "Require", "Conflict", "Obsolete"],
    "SOFT": ["Enhance", "Recommend", "Suggest", "Supplement"],
    "ORDER": ["Order"],
    "TRIGGER": ["Trigger", "Filetrigger", "Transfiletrigger"],
    "OLD": ["Oldenhance", "Oldsuggest", "Patches"],
}
# Same deal as above, but for scriptlets.
SCRIPTLET_GROUPS = {
    "BASIC": ["Prein", "Postin", "Preun", "Postun", "Pretrans", "Posttrans"],
    "VERIFY": ["Verify"],
}

# map each name "stem" to corresponding set of tag numbers
DEPENDENCY_NAMES = {n:Tag.byprefix(n)
                    for gn in DEPENDENCY_GROUPS.values() for n in gn}
SCRIPTLET_NAMES = {n:Tag.byprefix(n)
                   for sn in SCRIPTLET_GROUPS.values() for n in sn}

# Here's a couple of groupings for SigTags.
SIGNATURE_SIGTAGS = {SigTag.PGP, SigTag.GPG, SigTag.DSA, SigTag.RSA}
DIGEST_SIGTAGS = {SigTag.MD5, SigTag.SHA1, SigTag.SHA256}

# Lovingly handcrafted tag groupings.
# This covers every tag known to rpm-4.16.0. Whee!
tag_group = {name:{Tag(t) for t in grp} for (name, grp) in {
    "FILEDIGESTS": {1035, 5011},
    "FILENAMES":   {1116, 1117, 1118, 5000},
    "FILESTAT":    {1028, 1029, 1030, 1033, 1034, 1036, 1039, 1040,
                    1095, 1096, 5008, 5010, 5045},
    "FILECLASS":   {1141, 1142},
    "FILEDEPENDS": {1143, 1144, 1145, 5001, 5002},
    "SELINUX":     {1147, 1148, 1149, 1150, 5030, 5031, 5032, 5033},
    "RPMMD":       {61, 63, 64, 100, 1064, 1094, 5017, 5018, 5062},
    "RPMFILEMD":   {1045, 1097, 1098, 1099, 1140, 1037},
    "BUILDMD":     {1132, 1122, 1044, 1007, 1006, 1022, 1021, 1106, 1146},
    "DISTROMD":    {1010, 1011, 1015, 1123, 1155},
    "MODULEMD":    {5096},
    "PACKAGEINFO": {1000, 1001, 1002, 1003, 1004, 1005, 1014, 1016, 1020,
                    5012, 5019, 5034},
    "PAYLOADMD":   {1009, 1046, 1124, 1125, 1126, 5009, 5092, 5093, 5097},
    "IMAGES":      {1012, 1013, 1043},
    "NEVRAS":      {1196, 5013, 5014, 5015, 5016},
    "SRPM":        {1018, 1019, 1051, 1052, 1059, 1060, 1061, 1062, 1089},
    "RPMDB":       {1008, 1127, 1128, 1129, 1195, 5040},
    "DEPRECATED":  {1027, 1119, 1120, 1121, 5007},
    # FIXME: Tag and SigTag are separate namespaces...
    "SIGNATURES":  {62, 257, 259, 261, 262, 266, 267, 268, 269, 270, 271, 273,
                    5090, 5091},
    "CHANGELOG":   Tag.byprefix("Changelog"),
    "DEPENDENCY":  Tag.byprefix(DEPENDENCY_NAMES),
    "SCRIPTLET":   Tag.byprefix(SCRIPTLET_NAMES),
}.items()}

# And the catch-all for any Tag that's not already in another tag_group
tag_group["UNGROUPED"] = set(Tag).difference(*tag_group.values())

# Map {int/Tag:groupname}
groupname = {t:name for (name, grp) in tag_group.items() for t in grp}

# Confirm that each tag only belongs to one group
assert(len(set(i for s in tag_group.values() for i in s)) ==
       len(list(i for s in tag_group.values() for i in s)))
