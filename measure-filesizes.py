#!/usr/bin/python3

import os
import json
import gzip
from rpmtoys import rpm, Tag, iter_repo_rpms, progress
from base64 import b85encode, b85decode
from binascii import unhexlify

def blob_sizes(r):
    files = r.files()
    sizes = r.getval(Tag.FILESIZES) or [0 for f in files]
    hexblobs = r.getval(Tag.FILEDIGESTS) or ['' for f in files]
    return sorted(zip(files, sizes, (unhexlify(h) for h in hexblobs)),
                  key=lambda i:i[0])

def gather_blob_sizes(repodir, skip_envras=None):
    if not skip_envras:
        skip_envras=set()

    blobsizes = dict()  # {digest:size}
    envrablobs = dict() # {envra:[digest,...]}
    # TODO: fileclasses & compressed sizes?

    rpmiter = (rpm(rpmfn) for rpmfn in iter_repo_rpms(repodir))

    for r in progress(rpmiter, itemfmt=r.nevra):
        r = rpm(rpmfn)
        if r.envra in skip_envras:
            continue
        blobs = list()
        # in theory we should always have one digest for each regular
        # (non-ghost) file, so they'd pair back up with a sorted list of
        # filenames from another source (say filelists.xml.gz)
        for name, size, blob in blob_sizes(r):
            if blob:
                blobs.append(blob)
                blobsizes[blob] = size
        envrablobs[r.envra] = blobs
    return blobsizes, envrablobs

def write_blob_sizes(outfile, blobsizes, envrablobs, atomic=False):
    bloblist = sorted(blobsizes.keys())
    sizelist = [blobsizes[b] for b in bloblist]
    bidx = {b:i for i,b in enumerate(bloblist)}
    envraidx = {envra:[bidx[b] for b in blobs]
                for envra, blobs in envrablobs.items()}
    # if atomic, write to tmpfile then rename to outfile
    # NOTE: this is.. kinda stupid.
    if atomic:
        destfile = outfile
        outfile = outfile + '.tmp' # FIXME!!!!!
    with gzip.open(outfile, 'wt') as outf:
        json.dump({
            'counts':{'blobs':len(bloblist), 'envras':len(envraidx)},
            'blobs':[b85encode(b).decode('ascii') for b in bloblist],
            'sizes':sizelist,
            'envrablobs':envraidx,
        }, outf)
        size = outf.tell()
    if atomic:
        os.rename(outfile, destfile)
    return size

def load_blob_sizes(infile):
    with gzip.open(infile, 'rt') as inf:
        o = json.load(inf)
    bloblist = [b85decode(b) for b in o.pop('blobs')]
    blobsizes = dict(zip(bloblist, o.pop('sizes')))
    envrablobs = {envra:[bloblist[i] for i in indexes]
                  for envra, indexes in o.pop('envrablobs').items()}

    return blobsizes, envrablobs

def update_blob_sizes(infile, repodirs):
    if os.path.exists(infile):
        blobsizes, envrablobs = load_blob_sizes(infile)
    else:
        blobsizes, envrablobs = dict(), dict()
    for d in repodirs:
        print(f'reading {d}... ', flush=True, end='')
        newbs, neweb = gather_blob_sizes(d, skip_envras=set(envrablobs))
        print(f'{len(neweb)} new packages, {len(newbs)} new blobs')
        blobsizes.update(newbs)
        envrablobs.update(neweb)
        print(f'writing {infile}...')
        write_blob_sizes(infile, blobsizes, envrablobs, atomic=True)
    return blobsizes, envrablobs

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        print('TODO USAGE')
    elif sys.argv[1] == 'update':
        blobsizes, envrablobs = update_blob_sizes(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == 'plot':
        blobsizes, envrablobs = load_blob_sizes(sys.argv[2])
        # TODO
