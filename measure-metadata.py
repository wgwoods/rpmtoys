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

import json
import gzip

from rpmtoys.tags import getname
from rpmtoys.hdr import iter_repo_rpms, rpmhdr
from collections import Counter

def dump_sizedata(repo_paths, outfile="sizedata.json.gz"):
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
    tagsizes = Counter()
    tagcounts = Counter()
    for (s,h,p),ts in sizedata.values():
        tsd = Counter({getname(t):rs for t,o,s,rs in ts})
        tagsizes.update(tsd)
        tagcounts.update(tsd.keys())
    return tagsizes, tagcounts

# THIS IS A ROUGH HACK, MY FRIENDS.
if __name__ == '__main__':
    import os
    import sys
    prog = os.path.basename(sys.argv[0])
    usage = """
usage: {0} generate SIZEFILE REPODIR [REPODIR...]
       {0} analyze SIZEFILE
       {0} interactive SIZEFILE""".strip().format(prog)

    if len(sys.argv) <= 2:
        print(usage)
    elif sys.argv[1] == "generate":
        sizedata = dump_sizedata(sys.argv[3:], sys.argv[2])
    elif sys.argv[1] == "analyze":
        sizedata = json.load(gzip.open(sys.argv[2]))
        # this could be nicer..
        tagsizes, tagcounts = analyze_sizedata(sizedata)
        for tag, size in tagsizes.most_common():
            print("{:26}: {:5} times, {} bytes".format(tag, tagcounts[tag], size))
    elif sys.argv[1] == "interactive":
        import IPython
        print("loading sizedata from {}...".format(sys.argv[2]))
        sizedata = json.load(gzip.open(sys.argv[2]))
        print("generating tagsizes, tagcounts...")
        tagsizes, tagcounts = analyze_sizedata(sizedata)
        IPython.embed()
    else:
        print("error: unknown command '{}'".format(sys.argv[1]))
        print(usage)
        raise SystemExit(2)
