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

from collections import namedtuple
from .tagtbl import tagtbl

TagInfo = namedtuple("TagInfo", "name num vtype rtype ext")

info = [TagInfo(*t) for t in tagtbl]

byname = dict()
bynum = dict()
for t in info:
    byname[t.name.upper()] = t
    # longest name wins - see rpm/lib/tagname.c:tagCmpValue
    if t.num not in bynum or len(bynum[t.num].name) < len(t.name):
        bynum[t.num] = t

# for easy lookups: tagname[1000], tagnum.EPOCH, groupname.scriptlet
class TagNameDict(dict):
    def __getitem__(self, key):
        if type(key) is str:
            key = key.upper()
        return dict.__getitem__(self, key)

    def __getattr__(self, name):
        return self[name]


tagname = {t.num:t.name for t in bynum.values()}
tagnum = TagNameDict({t.name.upper():t.num for t in info})

def getname(tagnum):
    try:
        return tagname[tagnum]
    except KeyError:
        return str(tagnum)


def byprefix(pfx):
    if type(pfx) == str:
        return {t.num for t in info if t.name.startswith(pfx)}
    else:
        return {t.num for t in info if any(t.name.startswith(p) for p in pfx)}

# --- Below here we have a bunch of tag metadata (meta-metadata?)

# Tags that have binary values
BIN_TAGS = {t.num for t in info if t.vtype == 'BIN'}
# Tags that have non-array values
SCALAR_TAGS = {t.num for t in info if t.rtype == 'SCALAR'}
# Tags that have array values with one item per file
PER_FILE_TAGS = {1028, 1030, 1033, 1034, 1035, 1036, 1037, 1039, 1040, 1045,
                 1095, 1096, 1097, 1116, 1117}

# Group dependencies by type. Note that the names are a _prefix_ for a bunch of
# tags that get zipped together inside RPM to create each dependency "item".
DEPENDENCY_GROUPS = {
    "BASIC": ["Provide", "Require", "Conflict", "Obsolete"],
    "SOFT": ["Enhance", "Recommend", "Suggest", "Supplement"],
    "OLD": ["Oldenhance", "Oldsuggest"],
    "SPECIAL": ["Order", "Patches"],
}
# Same deal as above, but for scriptlets.
SCRIPTLET_GROUPS = {
    "BASIC": ["Prein", "Postin", "Preun", "Postun", "Pretrans", "Posttrans"],
    "TRIGGER": ["Trigger"],
    "FILETRIGGER": ["Filetrigger", "Transfiletrigger"],
    "VERIFY": ["Verify"],
}

# map each name "stem" to corresponding set of tag numbers
DEPENDENCY_NAMES = {n: byprefix(n)
                    for gn in DEPENDENCY_GROUPS.values() for n in gn}
SCRIPTLET_NAMES = {n: byprefix(n)
                   for sn in SCRIPTLET_GROUPS.values() for n in sn}

# Lovingly handcrafted tag groupings.
# This covers every tag known to rpm-4.14.1. Whee!
tag_group = TagNameDict({
    "FILEDIGESTS": {1035, 5011},
    "FILENAMES":   {1116, 1117, 1118, 5000},
    "FILESTAT":    {1028, 1029, 1030, 1031, 1032, 1033, 1034, 1036, 1039, 1040,
                    1095, 1096, 5008, 5010, 5045},
    "FILECLASS":   {1141, 1142},
    "FILEDEPENDS": {1143, 1144, 1145, 5001, 5002},
    "SELINUX":     {1147, 1148, 1149, 1150, 5030, 5031, 5032, 5033},
    "RPMMD":       {61, 63, 64, 100, 1064, 1094, 5017, 5018, 5062},
    "RPMFILEMD":   {1045, 1097, 1098, 1099, 1140, 1037},
    "BUILDMD":     {1132, 1122, 1044, 1007, 1006, 1022, 1021, 1106, 1146},
    "DISTROMD":    {1010, 1011, 1015, 1123, 1155},
    "PACKAGEINFO": {1000, 1001, 1002, 1003, 1004, 1005, 1014, 1016, 1020,
                    5012, 5019, 5034},
    "PAYLOADMD":   {1009, 1046, 1124, 1125, 1126, 5009, 5092, 5093},
    "IMAGES":      {1012, 1013, 1043},
    "NEVRAS":      {1196, 5013, 5014, 5015, 5016},
    "SRPM":        {1018, 1019, 1051, 1052, 1059, 1060, 1061, 1062, 1089},
    "RPMDB":       {1008, 1127, 1128, 1129, 1195, 5040},
    "DEPRECATED":  {1027, 1119, 1120, 1121, 5007},
    "SIGNATURES":  {62, 257, 259, 261, 262, 266, 267, 268, 269, 270, 271, 273,
                    5090, 5091},
    "CHANGELOG":   byprefix("Changelog"),
    "DEPENDENCY":  byprefix(DEPENDENCY_NAMES),
    "SCRIPTLET":   byprefix(SCRIPTLET_NAMES),
})

groupname = {t:name for (name, grp) in tag_group.items() for t in grp}

KNOWN_TAGS = {n for g in tag_group.values() for n in g}

# Confirm that each tag only belongs to one group
assert(len(set(i for s in tag_group.values() for i in s)) ==
       len(list(i for s in tag_group.values() for i in s)))
