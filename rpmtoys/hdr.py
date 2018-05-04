#!/usr/bin/python3
# rpmtoys/hdr.py - raw RPM header parsing
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

from .tags import SCALAR_TAGS, BIN_TAGS

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
#             using the value of tag 5062 (ENCODING), buuuut the official
#             rpm-python module doesn't bother, so we'll sort that out later
fmt_type_char = 'xCBHIL'
def iter_parse_tags(tags, store): # noqa: C901
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

        yield (tag, typ, off, cnt, size, realsize, val)


class rpmsection(object):
    '''
    Hold RPM Signature/Header Section data (rpmhdr.hdr, rpmhdr.sig)
    This object is mostly good for raw access to the contained data.
    '''
    def __init__(self, fobj, pad=False):
        tagents, store = read_section_header(fobj, pad)
        self.size = 16 + 16*len(tagents) + len(store)
        self.store = store
        self.tagtype = dict()
        self.tagrange = dict()
        self.tagsize = dict()
        self.tagval = dict()
        self.tagcnt = dict()
        self.encoding = 'utf-8'
        for tag, typ, off, cnt, size, rsize, val in iter_parse_tags(tagents, store):
            self.tagtype[tag] = typ
            self.tagrange[tag] = (off, size)
            self.tagcnt[tag] = cnt
            self.tagsize[tag] = rsize
            self.tagval[tag] = val
            if tag == 5062:  # ENCODING
                self.encoding = val.decode('utf-8')

    def rawval(self, tag):
        '''Return the raw value for the given tag, as bytes.'''
        off, size = self.tagrange[tag]
        return self.store[off:off+size]

    def getval(self, tag, default=None):
        '''
        Return the value for the given tag, decoded to its expected type:

        * String values are decoded using the value of self.encoding, which is
          set to the value of the ENCODING tag if encountered (utf-8 otherwise).
        * Tags with binary values return a bytes() object.
        * Tags listed as SCALAR in tagtbl are returned as a single value of the
          appropriate type. Everything else is returned as a tuple of values.

        returns default if tag is not found in this section.
        '''
        if tag not in self.tagval:
            return default
        val = self.tagval[tag]
        typ = self.tagtype[tag]
        enc = self.encoding
        if typ < 6:  # int arrays
            return val
        elif tag in BIN_TAGS:  # binary blobs
            return bytes(val)
        elif type(val) == bytes:  # plain string
            return val.decode(enc, errors='backslashreplace')
        elif type(val) == tuple and type(val[0]) == bytes:  # string array
            return tuple(v.decode(enc, errors='backslashreplace') for v in val)
            return val[0] if tag in SCALAR_TAGS else val
        else:
            msg = "unhandled value (typ:{} tag:{}): {}".format(typ, tag, val)
            raise ValueError(msg)

    def jsonval(self, tag, default=None):
        '''
        Return a json-compatible value for the given tag.
        (Same as getval(), but binary blobs are b64encoded into ascii strings.)
        '''
        from base64 import b64encode
        val = self.getval(tag)
        if type(val) == bytes:
            val = b64encode(val).decode('ascii', errors='ignore')
        return val

# Our equivalent to rpm.hdr - hold all the RPM's header data.
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
        e,n,v,r,a = [self.hdr.getval(t) for t in (1003,1000,1001,1002,1022)]
        nvra = "{}-{}-{}.{}".format(n, v, r, a)
        # EPOCH is an int, but it's also optional (and 0 != None)
        self.envra = nvra if e is None else str(e)+':'+nvra

    def iterfiles(self):
        '''Yield each of the (complete) filenames in this RPM.'''
        dirindexes = self.hdr.tagval.get(1116, [])
        basenames = self.hdr.tagval.get(1117, [])
        dirnames = self.hdr.tagval.get(1118, [])
        for diridx, basename in zip(dirindexes, basenames):
            yield (dirnames[diridx]+basename).decode('utf-8')

    def files(self):
        return list(self.iterfiles())

    def nfiles(self):
        return len(self.hdr.tagval.get(1116, []))

    # for convenience and _selftest(), get rpm-python's `hdr` for this RPM
    def _get_rpm_hdr(self):
        with open(self.name, 'rb') as fobj:
            hdr = self._ts.hdrFromFdno(fobj.fileno())
        return hdr

    # Share a single rpm.ts between all instances of this class
    @property
    def _ts(self):
        if self.__class__.__ts is None:
            import rpm
            flags = (rpm.RPMVSF_NOHDRCHK |
                     rpm._RPMVSF_NODIGESTS |
                     rpm._RPMVSF_NOSIGNATURES)
            self.__class__.__ts = rpm.ts("/", flags)
        return self.__class__.__ts
    __ts = None

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

        # ..except for ENCODING. bluhhh RPM why are you like this.
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

    # Return the expected in-header size of this value, given its RPM vtype
    @staticmethod
    def _expsize(val, typ):
        isarray = (type(val) in (list, tuple))
        cnt = len(val) if isarray else 1
        if typ == 0:
            return 0
        elif typ <= 5:
            return struct.calcsize(fmt_type_char[typ]) * cnt
        elif typ == 6 or typ == 8 or typ == 9:
            return sum(len(s)+1 for s in val) if isarray else len(val)+1
        elif typ == 7:
            return len(val)

    # I ran this against every package in F27 GOLD + updates and it passed,
    # so I'm pretty sure this parser works OK!
    def _selftest(self):
        '''
        Compare our data to what the official RPM module thinks.
        Return the set of tags that were checked.
        Raises an AssertionError if any checks fail.
        '''
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
                continue

            # Do we also have this tag?
            assert t in self.hdr.tagtype, terr(t, "not in hdr")

            # Do the types and values match?
            typ = self.hdr.tagtype.get(t)
            myval = self._get_rpm_val(t)
            rpmval = hdr[t]
            if typ == 9:
                assert type(myval) == list, terr(t, "I18NTABLE isn't a list")
                assert rpmval in myval, terr(t, "value {} not in table: {}", rpmval, myval)
            else:
                assert type(myval) == type(rpmval), terr(t,
                           "type mismatch: myval={}, rpmval={}",
                           type(myval).__name__, type(rpmval).__name__)
                assert (myval == rpmval), terr(t, "{} != {}", myval, rpmval)

            # Does the measured size match the expected size?
            off, size = self.hdr.tagrange[t]
            expsize = self._expsize(myval, typ)
            assert size == expsize, terr(t, "size mismatch: {} != {}", size, expsize)

            # OK! Add it to the list!
            checked.add(t)

        return checked
