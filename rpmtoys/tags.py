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
    byname[t.name] = t
    # longest name wins - see rpm/lib/tagname.c:tagCmpValue
    if t.num not in bynum or len(bynum[t.num].name) < len(t.name):
        bynum[t.num] = t

def getname(tagnum):
    if tagnum not in bynum:
        return str(tagnum)
    else:
        return bynum[tagnum].name

# --- Below here we have a bunch of tag metadata (meta-metadata?)

BIN_TAGS = frozenset(t.num for t in info if t.vtype == 'BIN')
SCALAR_TAGS = frozenset(t.num for t in info if t.rtype == 'SCALAR')

# My own artisinal hand-crafted groupings for tags
TAG_GROUPS = {
    "CHANGELOG": frozenset({1080, 1081, 1082}),
    "FILEDIGESTS": frozenset({1035}),
    "FILENAMES": frozenset({1116, 1117, 1118}),
    "FILESTAT": frozenset({1028, 1029, 1030, 1031, 1032, 1033, 1034, 1036,
                           1039, 1040, 1095, 1096, 5010}),
    "RPMFILEMD": frozenset({1045, 1097, 1098, 1099, 1140, 1037}),
    "FILECLASS": frozenset({1141, 1142}),
    "FILEDEPENDS": frozenset({1143, 1144, 1145}),
    "BUILDMD": frozenset({1132, 1122, 1044, 1007, 1006, 1022, 1021}),
    "DISTROMD": frozenset({1010, 1011, 1015}),
    "PACKAGEINFO": frozenset({1004, 1005, 1000, 1014, 1016, 1020, 5034}),
    # These two are incomplete at the moment
    "DEPENDENCY": frozenset({1047, 1048, 1049, 1050, 1053, 1054, 1055, 1090}),
    "SCRIPTLETS": frozenset({1065, 1066, 1067, 1068, 1069, 1085, 1086, 1087,
                             1088, 1091, 1092, 1112, 1113, 1114, 1115, 1151,
                             1152, 1153, 1154, 1023, 1024, 1025, 1026}),
}
# Confirm that each tag only belongs to one group
assert(len(set(i for s in TAG_GROUPS.values() for i in s)) ==
       len(list(i for s in TAG_GROUPS.values() for i in s)))
