#!/usr/bin/python3
# measure-metadata.py - raw RPM header parsing and data measurements
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

import os
import struct
from collections import Counter

# --- This section parses `tagtbl.C` (generated in the RPM sources) to get
# --- data about which data types we _expect_ for each tag.
#
# import re
# import rpm
# from collections import namedtuple
#
# tagtbl_re = re.compile('^ *{ "\w+", "(\w+)", (RPMTAG_[A-Z0-9_]+), RPM_([A-Z0-9_]+)_TYPE, RPM_(\w+)_RETURN_TYPE, (\d+)')
# TagInfo = namedtuple("TagInfo", "name num vtype rtype ext")
#
# def iter_tagtbl(fn):
#     with open(fn, 'rt') as fobj:
#         for line in fobj:
#             m = tagtbl_re.match(line)
#             if m:
#                 n,t,v,r,e = m.groups()
#                 num = getattr(rpm,t,0)
#                 yield TagInfo(n,num,v,r,bool(int(e)))
# def read_tagtbl(fn):
#     return list(iter_tagtbl(fn))
#
# tagtbl = read_tagtbl("tagtbl.C")
#
# BIN_TAGS = frozenset(t.num for t in tagtbl if t.vtype == 'BIN')
# SCALAR_TAGS = frozenset(t.num for t in tagtbl if t.rtype == 'SCALAR')


# --- Below here we have a bunch of tag metadata (meta-metadata?)


# These are what got dumped by the code above, run against rpm-4.14.1 or so
BIN_TAGS = frozenset({259, 261, 262, 267, 268, 1043, 1012, 1013, 1146})
SCALAR_TAGS = frozenset({
    261, 262, 259, 257, 1044, 267, 268, 269, 270, 271, 1024, 1152, 1026, 1155,
    1025, 5009, 5011, 5012, 5013, 1046, 1043, 5016, 5017, 5015, 5019, 5014,
    5021, 5020, 5023, 5024, 5025, 1151, 5022, 5018, 5026, 1064, 5034, 1195,
    1196, 1001, 1129, 1079, 1094, 5062, 1106, 1122, 1123, 5091, 1125, 1126,
    1127, 1128, 1000, 1124, 1003, 1132, 1005, 1006, 1007, 1008, 1002, 1010,
    1009, 1012, 1004, 1014, 1015, 1016, 1011, 1146, 1013, 1020, 1021, 1022,
    1023, 5092, 5093
})

# My own artisinal hand-crafted groupings for tags
TAG_GROUPS = {
    "CHANGELOG": frozenset({1080,1081,1082}),
    "FILEDIGESTS": frozenset({1035}),
    "FILENAMES": frozenset({1116,1117,1118}),
    "FILESTAT": frozenset({1028,1029,1030,1031,1032,1033,1034,1036,
                           1039,1040,1095,1096,5010}),
    "RPMFILEMD": frozenset({1045,1097,1098,1099,1140,1037}),
    "FILECLASS": frozenset({1141,1142}),
    "FILEDEPENDS": frozenset({1143,1144,1145}),
    # These two aren't exhaustive yet
    "DEPENDENCY": frozenset({1047,1048,1049,1050,1053,1054,1055,1090,}),
    "SCRIPTLETS": frozenset({1065,1066,1067,1068,1069,1085,1086,1087,1088,
                             1091,1092,1112,1113,1114,1115,1151,1152,1153,
                             1154,1023,1024,1025,1026}),
    "BUILDMD": frozenset({1132,1122,1044,1007,1006,1022,1021}),
    "DISTROMD": frozenset({1010,1011,1015}),
    "PACKAGEINFO": frozenset({1004,1005,1000,1014,1016,1020,5034}),
}
# Confirm that each tag only belongs to one group
assert(len(set(i for s in TAG_GROUPS.values() for i in s)) ==
       len(list(i for s in TAG_GROUPS.values() for i in s)))


# --- Okay, here's some machinery to parse an RPM by hand.
# --- For more info about the header data format, see:
# ---   http://ftp.rpm.org/max-rpm/s1-rpm-file-format-rpm-file-format.html
# ---   http://refspecs.linuxfoundation.org/LSB_1.3.0/gLSB/gLSB/swinstall.html

# Read the obsolete "Lead" structure
def read_lead(fobj):
    lead_s = struct.Struct("! 4s B B h h 66s h h 16s")
    return lead_s.unpack(fobj.read(lead_s.size))


# Read an RPM "Header Section Header" and return (tags, store):
#   tags: list of (tag, offset, tagtype, count) tuples
#   store: `bytes`, the "data store" for this section's values.
def read_section_header(fobj, pad=False):
    hdr_s = struct.Struct("! 4L")
    idx_s = struct.Struct("! 4L")
    magic, reserved, icount, dsize = hdr_s.unpack(fobj.read(hdr_s.size))
    tags = tuple(idx_s.iter_unpack(fobj.read(icount*idx_s.size)))
    if pad and dsize % 8:
        dsize += 8 - (dsize % 8)
    store = fobj.read(dsize)
    return tags, store


# "unpack" C-style (NUL-terminated) strings from the data store.
def iter_unpack_c_string(store, offset, count=1):
    start = offset
    end = len(store)
    n = offset
    while count and n < end:
        if store[n] == 0:
            yield store[start:n]
            start = n+1
            count -= 1
        n += 1

# Run through the section's "tags", parse the corresponding values, and
# return a gnarly tuple (tag,typ,off,size,realsize,val) for each one.
#  tag: `int` tag number
#  typ: `int` tag type (0-9, see "Index Type Values" in the LSB RPM docs)
#  off: `int` offset into the store where the value resides
#  size: `int` length of the value data, in bytes
#  realsize: `int` count of bytes of the value that do _not_ overlap other
#            values. (The first value will have size == realsize).
#  val: the actual parsed data. the type depends on the tag, but should be
#       one of `int`, `[int]`, `str`, `[str]`, `bytes`.
#       NOTE: we actually get `bytes` for `str`, and we _could_ decode() them
#             all using the value of tag 100 (HEADERI18NTABLE), buuuut the
#             official rpm-python module doesn't bother so why should we?
fmt_type_char = 'xCBHIL'
def iter_parse_tags(tags, store):
    used = Counter()
    i18ncnt = 1
    for tag, typ, off, cnt in tags:
        if tag == 100:
            # this will be the real 'cnt' value for all values of type 9.
            # See the note about RPM_I18NSTRING_TYPE in the LSB docs.
            i18ncnt = cnt
        # NULL type
        if typ == 0:
            val = None
            size = 0
        # integer types
        elif typ <= 5:
            fmt = '!'+str(cnt)+fmt_type_char[typ]
            val = struct.unpack_from(fmt, store, off)
            if cnt == 1 and tag in SCALAR_TAGS:
                val = val[0]
            size = struct.calcsize(fmt)
        # string
        elif typ == 6:
            val = next(iter_unpack_c_string(store, off))
            size = len(val)+1
        # binary blob
        elif typ == 7:
            val = store[off:off+cnt]
            size = cnt
        # string array
        elif typ == 8:
            val = tuple(iter_unpack_c_string(store, off, cnt))
            size = sum(len(v)+1 for v in val)
        # i18n string array
        elif typ == 9:
            val = tuple(iter_unpack_c_string(store, off, i18ncnt))
            size = sum(len(v)+1 for v in val)
        else:
            val = None
            size = 0

        # count only bytes that haven't been already counted
        realsize = sum(1 for i in range(off, off+size) if i not in used)
        # update which bytes we've counted
        used.update(range(off, off+size))

        yield (tag, typ, off, size, realsize, val)


# Hold either the Signature or Header section data
class rpmsection(object):
    def __init__(self, fobj, pad=False):
        tagents, store = read_section_header(fobj, pad)
        self.size = 16 + 16*len(tagents) + len(store)
        self.store = store
        self.tagtype = dict()
        self.tagrange = dict()
        self.tagsize = dict()
        self.tagval = dict()
        for tag, typ, off, size, rsize, val in iter_parse_tags(tagents, store):
            self.tagtype[tag] = typ
            self.tagrange[tag] = (off, size)
            self.tagsize[tag] = rsize
            self.tagval[tag] = val

    def rawval(self, tag):
        off, size = self.tagrange[tag]
        return self.store[off:off+size]


# Our low-level equivalent to rpm.hdr - hold all the RPM's header data.
class rpmhdr(object):
    def __init__(self, filename):
        self.name = filename
        with open(filename, 'rb') as fobj:
            self.lead = read_lead(fobj)
            self.sig = rpmsection(fobj, pad=True)
            self.hdr = rpmsection(fobj, pad=False)
            self.headersize = fobj.tell()

        size = os.stat(filename).st_size
        assert (self.headersize == 0x60+self.sig.size+self.hdr.size)
        self.payloadsize = size - self.headersize

        # For convenience's sake, construct the package's ENVRA as a str
        tv = self.hdr.tagval
        # these four are required, so it's OK to throw an exception if missing
        n, v, r, a = [tv[t].decode() for t in (1000, 1001, 1002, 1022)]
        nvra = "{}-{}-{}.{}".format(n, v, r, a)
        # EPOCH is an int, but it's also optional (and 0 != None)
        e = self.hdr.tagval.get(1003)
        self.envra = nvra if e is None else str(e)+':'+nvra

    # for convenience and _selftest(), get rpm-python's `hdr` for this RPM
    def _get_rpm_hdr(self):
        import rpm
        ts = rpm.ts("/", rpm.RPMVSF_NOHDRCHK |
                         rpm._RPMVSF_NODIGESTS |
                         rpm._RPMVSF_NOSIGNATURES)
        with open(self.name, 'rb') as fobj:
            hdr = ts.hdrFromFdno(fobj.fileno())
        return hdr

    # Get the value of a given tag and munge it up to look like RPM's version.
    # Mostly useful for _selftest().
    def _get_rpm_val(self, tag):
        val = self.hdr.tagval[tag]

        # we use tuples, RPM uses lists, that's fine
        if type(val) == tuple:
            val = list(val)

        # rpm enforces SCALAR_TAGS, even for things with type == 6
        if tag not in SCALAR_TAGS and type(val) != list:
            val = [val]

        # ..except this. bluhhh RPM why are you like this.
        if tag == 5092 and type(val) == list and len(val) == 1:
            val = val[0]

        # oh also this, which the rpm module rejiggers internally
        if tag == 1141:  # FILECLASS: val is a list of indexes into CLASSDICT
            cd = self.hdr.tagval[1142]  # CLASSDICT: file(1) output, or ''
            lt = self.hdr.tagval[1036]  # FILELINKTOS: link targets, or ''
            # returned value is the CLASSDICT value (if non-empty);
            # else 'symbolic link to `%s'" if it's a symlink, otherwise ''
            val = [cd[i] or (lt[n] and b"symbolic link to `"+lt[n]+b"'")
                   for n, i in enumerate(val)]

        return val

    # Compare our tagval data to what RPM thinks.
    # I ran this against every package in F27 GOLD + updates and it passed,
    # so I'm pretty sure this parser works OK!
    def _selftest(self):
        checked = set()

        import rpm
        # get RPM header
        hdr = self._get_rpm_hdr()

        # error helper function
        def terr(t, msg, *args):
            errmsg = msg.format(*args)
            return "{} ({}): {}".format(t, rpm.tagnames.get(t), errmsg)

        # check each tag/val in the RPM header against our values
        for t in hdr.keys():
            # skip private tags (1046=RPMVERSION)
            if t < 1000 or t == 1046:
                checked.add(t)
                continue

            typ = self.hdr.tagtype.get(t)
            assert t in self.hdr.tagtype, terr(t, "not in hdr")
            assert typ in range(0, 10), terr(t, "unknown type: {}", typ)

            off, size = self.hdr.tagrange[t]
            myval = self._get_rpm_val(t)
            rpmval = hdr[t]

            # check value
            if typ == 9:
                assert type(myval) == list, terr(t, "I18NTABLE isn't a list")
                assert rpmval in myval, terr(t, "value {} not in table: {}", rpmval, myval)
            else:
                assert type(myval) == type(rpmval), terr(t,
                           "type mismatch: myval={}, rpmval={}",
                           type(myval).__name__, type(rpmval).__name__)
                assert (myval == rpmval), terr(t, "{} != {}", myval, rpmval)

            # check size
            if typ == 0:
                expsize = 0
            elif typ <= 5:
                expsize = struct.calcsize(fmt_type_char[typ]) * (len(myval) if type(myval) == list else 1)
            elif typ == 6 or typ == 8 or typ == 9:
                expsize = sum(len(s)+1 for s in myval) if type(myval) == list else len(myval) + 1
            elif typ == 7:
                expsize = len(myval)
            else:
                expsize = None
            assert size == expsize, terr(t, "size mismatch: {} != {}", size, expsize)

            # done! add it to the list
            checked.add(t)

        return checked


# fun fact: this is waaayyy faster than reading repodata
def iter_repo_rpms(paths):
    for path in paths:
        for top, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".rpm"):
                    yield os.path.join(top, f)


def dump_sizedata(repo_paths, outfile="sizedata.json.gz"):
    import json
    import gzip
    rpmlist = list(iter_repo_rpms(repo_paths))
    sizedata = dict()
    for n, rpmfn in enumerate(rpmlist):
        if n % 100 == 0:
            print("reading {:6}/{:6} ({:4.1f}%)".format(n,len(rpmlist),n/len(rpmlist)*100.0), end='\r', flush=True) # NOQA
        r = rpmhdr(rpmfn)
        sizedata[r.envra] = [
                [r.sig.size, r.hdr.size, r.payloadsize],
                [(tag, off, size, r.hdr.tagsize[tag])
                    for tag, (off, size) in r.hdr.tagrange.items()]
        ]
    print("\ndumping to {}...".format(outfile))
    json.dump(sizedata, gzip.open(outfile, 'wt'))
    print("done!")
    return sizedata


def analyze_sizedata(sizedata):
    import rpm
    tagsizes = Counter()
    tagcounts = Counter()
    for (s,h,p),ts in sizedata.values():
        tsd = Counter({rpm.tagnames.get(t,str(t)):rs for t,o,s,rs in ts})
        tagsizes.update(tsd)
        tagcounts.update(tsd.keys())
    return tagsizes, tagcounts

load_sizedata = True

# yeah obviously this ain't gonna work on your system.
# THIS IS A ROUGH HACK, MY FRIENDS.
# You should run this with `ipython3 -i measure-metadata.py`.
if __name__ == '__main__':
    import json
    import gzip
    f27_dir = '/srv/released/F-27/GOLD/Everything/x86_64/os'
    upd_dir = '/srv/updates/27/x86_64'
    sizefile = 'f27-sizedata.json.gz'
    if load_sizedata:
        try:
            sizedata = json.load(gzip.open(sizefile))
        except FileNotFoundError:
            sizedata = dump_sizedata([f27_dir, upd_dir], sizefile)
        tagsizes, tagcounts = analyze_sizedata(sizedata)
