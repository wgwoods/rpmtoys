#!/usr/bin/python3
# mkdino.py - hacky script to generate .dino packfiles from sets of RPMs
#
# Copyright (c) 2019, Red Hat, Inc.
#
# TODO: proper GPLv3 boilerplate here; see LICENSE
#
# Author: Will Woods <wwoods@redhat.com>

# This is a gnarly demo of one way we could build some .dino packfiles.
#
# TODO:
# * Build indexes over output directory contents
# * Command to list contents of .dino/.didx
# * Command to extract RPM from .dino
# * Multithreading: uncompression, hashing, compression
# * Binary deltas
#
# Known bugs:
# * Crashes if you try to build a .dino >= 4GB (no 64-bit support)
# * Compression is weirdly bad for certain packages (like git?)

import struct

from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from binascii import unhexlify, hexlify

from rpmtoys import rpm, pkgtup, Tag, SigTag
from rpmtoys.vercmp import rpm_evr_key
from rpmtoys.digest import gethasher, hashsize, HashAlgo
from rpmtoys.progress import progress

from dino import DINO, Arch, CompressionID, DigestID, SectionFlags, ObjectType
from dino.section import RPMSection, IndexSection, FileDataSection

# So! A simple rpm-compatible-ish archive might look like this:
#
# [rpm index][rpmhdr, rpmhdr, ...][file index][file, file, file...]
# I *think* we can toss the rpm lead completely, since we can mostly
# regenerate it from the RPM header data and RPM doesn't even look at it
# for anything.
# We can also toss almost everything in the CPIO headers, _except_ that
# I think we need to keep track of the file _ordering_, since it might not
# match the file ordering in the RPM headers, and the MD5 signature
# actually (sadly) does care about the payload ordering.
class DINORPMArchive(DINO):
    idxalgo = DigestID.SHA256

    def __init__(self, arch=Arch.NONE, compression_id=CompressionID.ZSTD):
        DINO.__init__(self, arch=arch, compression_id=compression_id,
                      objtype=ObjectType.Archive)
        # TODO: this should be in the headers somewhere, right?
        # Make sections to hold RPM header data
        self.rpmhdr = RPMSection(flags=SectionFlags.COMPRESSED)
        self.rpmidx = IndexSection(othersec=self.rpmhdr,
                                   keysize=hashsize(self.idxalgo),
                                   flags=SectionFlags.COMPRESSED)
        # Make sections to hold file data
        self.filedata = FileDataSection(flags=SectionFlags.COMPRESSED)
        self.fileidx = IndexSection(othersec=self.filedata,
                                    keysize=hashsize(self.idxalgo),
                                    flags=SectionFlags.COMPRESSED)
        # Add the sections to the section table
        self.add_section(self.rpmidx, name='.rpmhdr.idx')
        self.add_section(self.rpmhdr, name='.rpmhdr')
        self.add_section(self.fileidx, name='.filedata.idx')
        self.add_section(self.filedata, name='.filedata')

    def rpmids(self):
        return self.rpmidx.keys()

    def has_rpmid(self, key):
        return key in self.rpmidx

    def fileids(self):
        return self.fileidx.keys()

    def has_fileid(self, key):
        return key in self.fileidx


class VerifyError(ValueError):
    pass

def rpmlister(dirs):
    '''list RPMs under topdir, grouped by .src.rpm name, sorted newest-oldest'''
    src = dict()
    print("Finding RPMs, one moment..")
    rpmps = [p for d in dirs for p in Path(d).glob('**/*.rpm')]
    for rpmp in progress(rpmps, prefix='Reading RPM headers ', itemfmt=lambda p: p.name):
        r = rpm(rpmp)
        srctup = r.srctup()
        evr = (srctup.epoch, srctup.ver, srctup.rel)
        src.setdefault(srctup.name, {})
        src[srctup.name].setdefault(evr, [])
        src[srctup.name][evr].append(rpmp)
    rpms = dict()
    for name in src:
        pkgs = src[name]
        vers = sorted(pkgs, key=rpm_evr_key, reverse=True)
        rpms[name] = [p for v in vers for p in pkgs[v]]
    return rpms

# TODO: sometimes the output is larger than the input:
#
#    COOLRPMS/git-core-2.17.0-1.fc28.x86_64.rpm
#    writing section data
#      0: .rpmhdr.idx (Index)
#      1: .rpmhdr (RPMHdr)
#      2: .filedata.idx (Index)
#      3: .filedata (FileData)
#    packed 1 packages (4216572 bytes) into COOLDINO/git.dino (11739923 bytes)
#
# Obviously, only having one package in a packfile is a weird corner case, but
# we should generally try not end up with output that's significantly larger
# than the input...
# TODO: * Make fanout table (or indexes?) optional for small packages
#       * If compressed filesize is >= original, store uncompressed
#       * Sort files so more similar files (e.g. time-series copies of the same
#         filename) are stored near each other
#       * Pack small files into a block, `size` is the offset within it
#         (and other tricks used by squashfs!)
#       * Use a dictionary for/in each packfile?
#       * Support XZ compression (or, really, figure out why certain packages
#         compress better as .cpio.xz than .dino.zst)

# TODO: use logging for this, and get the flag from the commandline..
verbose = True
def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)

def pad4(i):
    return (i+0x3)&~0x3

def unc_payloadsize(r):
    # header: 110 bytes + len('.'+filename+'\0'), padded to 4-byte alignment
    # file data also padded to 4-byte alignment
    # file ends with 'TRAILER!!!' entry, 110+12+pad = 124
    return (sum(pad4(112+len(f)) for f in r.iterfiles()) +
            sum(pad4(s) for s in r.getval(Tag.FILESIZES,[])) + 124)

# FIXME this is a long, awful mess; most of the interesting stuff here should
# move into the dino library itself, DINORPMArchive, or more generic tools
def merge_rpms(rpmiter, outfile):
    # Start with a new header object
    d = DINORPMArchive()
    count, rpmsize, rpmtotal = 0, 0, 0

    # separate contexts for compressing headers vs. files.
    # TODO: it might be helpful if we made dictionaries for each
    fzst = d.get_compressor(level=-1)
    hzst = d.get_compressor(level=-1)

    # Okay let's start adding some RPMs!
    if not verbose:
        rpmiter = progress(rpmiter, prefix=Path(outfile).name+': ', itemfmt=lambda p: p.name)
    for rpmfn in rpmiter:
        vprint(f'{rpmfn}:')
        r = rpm(rpmfn)

        # update stats
        count += 1
        rpmsize = r.payloadsize + r.headersize
        rpmtotal += rpmsize

        # We handle the files before the RPM header because while _nearly_
        # everything in the RPM payload can be reconstructed from the RPM
        # header itself, there are a couple tiny things that could be
        # different, like the ordering of the files in the archive.
        # NOTE: I'm almost sure we can reproduce the original _uncompressed_
        # payload, but I'm really not certain that we can get the exact
        # compression context (or timestamps or whatever else) are needed.

        # Grab the filenames and digests from the rpmhdr
        fnames = ["."+f for f in r.iterfiles()]
        rpmalgo = r.getval(Tag.FILEDIGESTALGO)
        digests = r.getval(Tag.FILEDIGESTS)

        # show RPM header/file sizes
        vprint(f'  RPM: hdr={r.headersize-0x60:<6} files={len(fnames):<3} filesize={r.payloadsize}'
               f' compr={r.payloadsize/unc_payloadsize(r):<6.2%}')


        # Keep track of the order of the files in the payload
        payload_in_order = True
        payload_order = []
        hdridx = {f:n for n,f in enumerate(fnames)}

        # Start running through the RPM payload
        filecount, filesize, unc_filesize = 0, 0, 0
        for n,item in enumerate(r.payload_iter()):
            # Does the payload name match the corresponding header name?
            # If not, find the header index for the payload filename.
            if item.name == fnames[n]:
                idx = n
            else:
                payload_in_order = False
                idx = hdridx[item.name]
            payload_order.append(idx)

            # We only store regular files with actual data
            if not (item.isreg and item.size):
                continue

            # Set up hashers
            hashers = {algo:gethasher(algo) for algo in (rpmalgo, d.idxalgo)}

            # Uncompress file, hash it, and write it to a temporary file.
            # If the calculated file key isn't in the index, compress the
            # temporary file contents into the filedata section.
            with SpooledTemporaryFile() as tmpf:
                # Uncompress and hash the file contents
                for block in item.get_blocks():
                    # TODO: parallelize?
                    tmpf.write(block)
                    for h in hashers.values():
                        h.update(block)
                # Check digest to make sure the file is OK
                h = hashers[rpmalgo]
                if h.hexdigest() != digests[idx]:
                    act = h.hexdigest()
                    exp = digests[idx]
                    raise VerifyError(f"{fnames[idx]}: expected {exp}, got {act}")
                # Add this if it's not already in the fileidx
                filekey = hashers[d.idxalgo].digest()
                if filekey not in d.fileidx:
                    # Write file data into its own compressed frame.
                    tmpf.seek(0)
                    offset = tmpf.tell()
                    usize, size = fzst.copy_stream(tmpf, d.filedata.fobj, size=item.size)
                    d.fileidx.add(filekey, offset, size)
                    filecount += 1
                    filesize += size
                    unc_filesize += item.size

        # Okay, files are added, now we can add the rpm header.
        # FIXME: we shouldn't have to do this manually..
        hdr = None
        with open(r.name, 'rb') as fobj:
            fobj.seek(0x60) # don't bother with the lead
            hdr = fobj.read(r.headersize-0x60)

        # Check signature header digest (if present)
        sigkey = r.sig.getval(SigTag.SHA256, '')
        if sigkey:
            h = gethasher(HashAlgo.SHA256)
            h.update(hdr[r.sig.size:])
            if sigkey != h.hexdigest():
                raise VerifyError(f"SHA256 mismatch in {r.name}")

        # Add the payload ordering
        if not payload_in_order:
            hdr += b''.join(struct.pack('I',i) for i in payload_order)

        # Add it to the rpmhdr section
        offset = d.rpmhdr.fobj.tell()
        usize, size = hzst.copy_stream(BytesIO(hdr), d.rpmhdr.fobj, size=len(hdr))
        sizediff = (size+filesize)-rpmsize
        vprint(f' DINO: hdr={size:<6} files={filecount:<3} filesize={filesize}'
               f' {f"compr={filesize/unc_filesize:<6.2%}" if filesize else ""}'
               f' diff={sizediff:+} ({sizediff/rpmsize:+.1%})'
               f' {"(!)" if sizediff/rpmsize > 0.02 else ""}')

        # Generate pkgkey (TODO: maybe copy_into should do this..)
        # TODO: y'know, it might be more useful to use the sha256 of the
        # package envra - which, in theory, should also be unique, but also
        # gives us fast package lookups by name...
        #pkgid = hashlib.sha256(bytes(r.envra, 'utf8')).hexdigest()
        hasher = gethasher(d.idxalgo)
        hasher.update(hdr)
        pkgkey = hasher.digest()
        # Add package key to the index
        d.rpmidx.add(pkgkey, offset, size)

    # We did it! Write the data to the output file!
    with open(outfile, 'wb') as outf:
        wrote = d.write_to(outf)
    sizediff = wrote-rpmtotal
    print(f'packed {count} packages ({rpmtotal} bytes) into {outfile} '
          f'({sizediff/rpmtotal:<+.1%} -> {wrote} bytes)'
          f'{" (!)" if wrote > rpmtotal else ""}')
    return rpmtotal, wrote

# TODO: so yeah how do we actually open/read the files we wrote tho.
# This stuff should all end up in the dino module.
class DinoError(Exception):
    pass

def dino_open(filename):
    from dino import Dhdrp, Shdrp, StringTable, MAGIC_V0
    #import mmap
    inf = open(filename, mode='r+b')
    d = DINO()

    # read DINO header
    # TODO: d.from_file()
    dhdr = Dhdrp.read1_from(inf)
    if dhdr.magic != MAGIC_V0:
        raise DinoError(f'{filename} has bad magic')

    # read section table
    shdrs = list(Shdrp.iter_read_from(inf, dhdr.sectab_size))
    # TODO: d.sectab.from_bytes(inf.read(dhdr.sectab_size))

    # read name table
    d.namtab.from_bytes(inf.read(dhdr.namtab_size))

    # Get the current file offset
    offset = inf.tell()

    return (d, dhdr, shdrs, offset)

if __name__ == '__main__':
    # TODO: ugh real cmdline parsing come on dude
    import sys

    if len(sys.argv) < 2:
        print("usage: mkdino.py DINODIR RPMDIR [RPMDIR..]")
        print("or:    ipython3 -i mkdino.py DINOFILE")
        raise SystemExit(2)

    elif len(sys.argv) == 2:
        from rpmtoys import dino # convenience for ipython
        dinofile = sys.argv[1]
        d, dhdr, shdrs, offset = dino_open(dinofile)
        print(f'dinofile={dinofile!r}')
        print(f'dhdr={dhdr}')
        print(f'shdrs=[')
        for sh in shdrs:
            print('  '+str(sh._replace(name=d.namtab.get(sh.name)))+',')
        print(']')
        print(f'offset={offset!r}')

    elif len(sys.argv) > 2:
        dinodir = Path(sys.argv[1])
        if not dinodir.exists():
            dinodir.mkdir()
        if not dinodir.is_dir():
            print("ERROR: {dinodir} exists but isn't a directory")
            raise SystemExit(2)
        rpmcount, rpmtotal, dinocount, dinototal = 0,0,0,0
        for name, rpms in rpmlister(sys.argv[2:]).items():
            dinofile = (dinodir/name).with_suffix(".dino")
            print()
            rpmsize, dinosize = merge_rpms(rpms, dinofile)
            dinocount += 1
            rpmcount += len(rpms)
            rpmtotal += rpmsize
            dinototal += dinosize
            # TODO: write index(es) into dinodir
        print(f"read {rpmcount} packages ({rpmtotal} bytes), wrote {dinocount}"
              f" packfiles ({dinototal} bytes, {(dinototal-rpmtotal)/rpmtotal:+.1%})")
