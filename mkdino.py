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
import argparse

from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from binascii import unhexlify, hexlify
from itertools import zip_longest
from collections import OrderedDict

from rpmtoys import rpm, pkgtup, Tag, SigTag
from rpmtoys.vercmp import rpm_evr_key
from rpmtoys.digest import gethasher, hashsize, HashAlgo
from rpmtoys.progress import progress

from dino import DINO, Arch, CompressionID, DigestID, SectionFlags, ObjectType
from dino.section import RPMSection, IndexSection, FileDataSection
from dino.compression import (available_compressors, get_compressor,
                              get_compressid, DEFAULT_COMPRESSION_LEVEL)

# NOTE: I've switched this to XZ until we've got network fetch and package
# install working - ZSTD is much faster but doesn't compress as well, and
# right now we're looking for apples-to-apples comparisons on disk usage.
DEFAULT_RPMARCHIVE_COMPRESSOR = CompressionID.XZ

# So! A simple rpm-compatible-ish archive might look like this:
#
# [rpm index][rpmhdr, rpmhdr, ...][file index][file, file, file...]
# We can toss the rpm lead completely, since we can regenerate it from the RPM
# header data and RPM doesn't even look at it for anything.
# We can also toss almost everything in the CPIO headers, _except_ that
# I think we need to keep track of the file _ordering_, since it might not
# match the file ordering in the RPM headers, and the MD5 signature
# actually (sadly) does care about the payload ordering.
class DINORPMArchive(object):
    def __init__(self, dino=None,
                 idxalgo=DigestID.SHA256,
                 compression_id=DEFAULT_RPMARCHIVE_COMPRESSOR,
                 compresslevel=None):
        self.idxalgo = idxalgo
        self.compression_id = compression_id
        if dino:
            self.dino = dino
            self.compression_id = dino.compression_id
        else:
            self.dino = DINO(arch=Arch.NONE,
                             compression_id=self.compression_id,
                             objtype=ObjectType.Archive)
            self.make_sections(self.dino)
        self.compresslevel = compresslevel or -1
        # TODO: does that need to be applied to self.dino?
        self.rpmidx = self.dino.findsection(name=".rpmhdr.idx")
        self.rpmhdr = self.rpmidx.othersec
        self.fileidx = self.dino.findsection(name=".filedata.idx")
        self.filedata = self.fileidx.othersec
        self._unz = self.dino.get_decompressor()

    def make_sections(self, dino):
            rpmhdr = RPMSection(flags=SectionFlags.COMPRESSED)
            rpmidx = IndexSection(othersec=rpmhdr,
                                  keysize=hashsize(self.idxalgo),
                                  flags=SectionFlags.COMPRESSED)
            filedata = FileDataSection(flags=SectionFlags.COMPRESSED)
            fileidx = IndexSection(othersec=filedata,
                                   keysize=hashsize(self.idxalgo),
                                   flags=SectionFlags.COMPRESSED)
            dino.add_section(rpmidx, name='.rpmhdr.idx')
            dino.add_section(rpmhdr, name='.rpmhdr')
            dino.add_section(fileidx, name='.filedata.idx')
            dino.add_section(filedata, name='.filedata')

    def rpmids(self):
        return self.rpmidx.keys()

    def has_rpmid(self, key):
        return key in self.rpmidx

    # TODO: get key(s) that match abbreviated hex names
    # TODO: NEVRA/ENVRA -> key(s)
    # TODO: update existing .dino

    def get_rpmhdr(self, key):
        tup = self.rpmidx.get(key)
        if not tup:
            return None
        off, size = self.rpmidx.get(key)[0:2] # we don't use unc_size here
        self.rpmhdr.fobj.seek(off)
        hdr = self._unz.decompress(self.rpmhdr.fobj.read(size))
        r = rpm(hdrbytes=hdr)
        if len(hdr) > r.headersize:
            r.payload_order = struct.iter_unpack("I", hdr[r.headersize:])
        else:
            r.payload_order = None
        return r

    def iter_rpmhdrs(self):
        for k in self.rpmids():
            yield k, self.get_rpmhdr(k)

    def _write_rpm_hdrs(self, r, outf):
        outf.write(r.make_lead()._pack())
        # TODO: should just be dumping the sig/hdr data rather than re-packing
        outf.write(r.sig.pack())
        outf.write(r.hdr.pack())

    def _write_rpm_payload(self, r, outf):
        inocount = dict()
        # FIXME: check payload_order!
        for digest, c, linkto in zip_longest(r.iterdigests(), r.itercpiohdrs(), r.iterlinktos()):
            filekey = unhexlify(digest)
            inocount.setdefault(c.ino, 0)
            inocount[c.ino] += 1
            if inocount[c.ino] < c.nlink:
                outf.write(c._replace(size=0)._pack())
                continue
            outf.write(c._pack())
            wrote = 0
            if filekey:
                wrote = self.write_file(filekey, outf)
            elif linkto:
                # TODO: we shouldn't need to convert back to bytes here;
                # we should be iterating through raw header data..
                wrote = outf.write(bytes(linkto, 'utf8'))
            if wrote:
                outf.write(b'\0'*(pad4(wrote) - wrote))
        outf.write(cpio_trailer)

    def write_rpm(self, key, outf):
        r = self.get_rpmhdr(key)
        self._write_rpm_hdrs(r, outf)
        # FIXME: compress payload if requested by user (or required for RPM)
        #outz = get_rpm_compressor(r)
        self._write_rpm_payload(r, outf)

    def iter_rpm_filekeys(self, rpmkey):
        r = self.get_rpmhdr(key)
        # return i

    def fileids(self):
        return self.fileidx.keys()

    def has_fileid(self, key):
        return key in self.fileidx

    def write_file(self, key, outf):
        inf = self.fileidx.othersec.fobj
        off, size = self.fileidx.get(key)[0:2]

        # XXX FIXME: copy_stream gives errors here, possibly because of frame
        # endings?
        #inf.seek(off)
        #read, wrote = self._unz.copy_stream(inf, outf)

        # XXX FIXME: I thought this might fix it, but nope?
        #infv = FileView(inf, off, size)
        #read, wrote = self._unz.copy_stream(infv, outf)

        # XXX FIXME: This definitely works, but we probably don't want to
        # decompress the whole thing all at once...
        inf.seek(off)
        wrote = outf.write(self._unz.decompress(inf.read(size)))

        return wrote

class VerifyError(ValueError):
    pass

def rpmlister(dirs):
    '''list RPMs under topdir, grouped by .src.rpm name, sorted newest-oldest'''
    print("Finding RPMs, one moment..")
    rpmps = [p for d in dirs for p in Path(d).glob('**/*.rpm')]
    # read RPM headers and get source RPM tuple for each package
    srctup = dict()
    for p in progress(rpmps, prefix='Reading RPM headers ', itemfmt=lambda p: p.name):
        # TODO: we should also gather header/payload sizes and warn if we're
        # probably going to blow up 32-bit offsets. (Or, like.. auto-split
        # files at that point...)
        srctup[p] = rpm(p).srctup()
    src = rpm_src_groupsort(srctup.items())
    return {name:[p for pkgs in src[name].values() for p in pkgs] for name in src}

def rpm_src_groupsort(srctups, reverse=True):
    '''
    Takes an iterable that gives (value, srctup) pairs, and returns a
    dictionary of the form:
        {src.name: OrderedDict(srcevr1:[value, value, ...], ...) }
    For example, maybe you construct a dict like so:
        rpmfile_to_srctup = {rpmfn:rpm(rpmfn).srctup() for rpmfn in repolist}
    This function will group the RPMs by their source package name, and
    under that is an OrderedDict where the keys are build (e,v,r) tuples and
    the values are whatever values you passed in that came from that NEVR.
    '''
    src = dict()
    for v, srctup in srctups:
        srcevr = (srctup.epoch, srctup.ver, srctup.rel)
        src.setdefault(srctup.name, {})
        src[srctup.name].setdefault(srcevr, [])
        src[srctup.name][srcevr].append(v)
    for n in src:
        srcevr_pkgs = src[n]
        srcevrs = sorted(srcevr_pkgs, key=rpm_evr_key, reverse=reverse)
        src[n] = OrderedDict((v, srcevr_pkgs[v]) for v in srcevrs)
    return src

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

# Some CPIO utility bits..

def pad4(i):
    return (i+0x3)&~0x3

def unc_payloadsize(r):
    # header: 110 bytes + len('.'+filename+'\0'), padded to 4-byte alignment
    # file data also padded to 4-byte alignment
    # file ends with 'TRAILER!!!' entry, 110+12+pad = 124
    return (sum(pad4(112+len(f)) for f in r.iterfiles()) +
            sum(pad4(s) for s in r.getval(Tag.FILESIZES,[])) + 124)

cpio_trailer = (b'0707010000000000000000000000000000000000000001000000000'
                b'0000000000000000000000000000000000000000000000b00000000'
                b'TRAILER!!!\x00\x00\x00\x00')

# And some compression utility stuff..

def get_rpm_compressor(r):
    compr = r.getval(Tag.PAYLOADCOMPRESSOR)
    try:
        level = int(r.getval(Tag.PAYLOADFLAGS))
    except ValueError:
        level = -1
    return get_compressor(compr, level=level)

# FIXME this is a long, awful mess; most of the interesting stuff here should
# move into the dino library itself, DINORPMArchive, or more generic tools
def merge_rpms(rpmiter, outfile, **dino_kwargs):
    # Start with a new header object
    d = DINORPMArchive(**dino_kwargs)
    count, rpmsize, rpmtotal = 0, 0, 0

    # separate contexts for compressing headers vs. files.
    # TODO: it might be helpful if we made dictionaries for each?
    fzst = d.dino.get_compressor(level=d.compresslevel)
    hzst = d.dino.get_compressor(level=d.compresslevel)

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
                    # TODO: parallelize? parallelize!
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
                    offset = d.filedata.fobj.tell()
                    usize, size = fzst.copy_stream(tmpf, d.filedata.fobj, size=item.size)
                    vprint(f"wrote {size} bytes to filedata sec at offset {offset}")
                    d.fileidx.add(filekey, offset, size, usize)
                    assert d.filedata.fobj.tell() == offset + size
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
            h.update(hdr[-r.hdr.size:])
            if sigkey != h.hexdigest():
                raise VerifyError(f"SHA256 mismatch in {r.name}: expected {sigkey} got {h.hexdigest()}")

        # Add the payload ordering
        if not payload_in_order:
            hdr += b''.join(struct.pack('I',i) for i in payload_order)

        # Add it to the rpmhdr section
        offset = d.rpmhdr.fobj.tell()
        usize, size = hzst.copy_stream(BytesIO(hdr), d.rpmhdr.fobj, size=len(hdr))
        assert d.rpmhdr.fobj.tell() == offset + size
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
        d.rpmidx.add(pkgkey, offset, size, usize)

    # We did it! Write the data to the output file!
    with open(outfile, 'wb') as outf:
        wrote = d.dino.write_to(outf)
    sizediff = wrote-rpmtotal
    print(f'packed {count} packages ({rpmtotal} bytes) into {outfile} '
          f'({sizediff/rpmtotal:<+.1%} -> {wrote} bytes)'
          f'{" (!)" if wrote > rpmtotal else ""}')
    return rpmtotal, wrote

###### Below here we have some CLI-oriented helpers etc.

class PartialKey(object):
    def __init__(self, hex=None, bin=None):
        self._halfbyte = False
        if isinstance(bin, bytes):
            self._bytes = bin
        elif hex is not None:
            if len(hex) & 1:
                self._bytes = unhexlify(hex+'0')
                self._halfbyte = True
            else:
                self._bytes = unhexlify(hex)
        self.size = len(self._bytes)

    def __repr__(self):
        h = str(self)
        return (f'{__class__.__name__}(hex={h!r})')

    def __str__(self):
        h = hexlify(self._bytes).decode('ascii')
        if self._halfbyte:
            h = h[:-1]
        return h

    def match(self, key):
        k = key[:self.size]
        if self._halfbyte:
            k = k[:-1] + k[-1] & 0xf0
        return k == self._bytes

def DINOObjectName(arg):
    # Check if it's a path
    p = Path(arg)
    if p.is_file():
        return p
    # Maybe it's a partial key?
    try:
        return PartialKey(hex=arg)
    except ValueError:
        pass
    # Well, maybe it's an RPM NEVRA/ENVRA.
    if '-' in arg:
        if ':' in arg and arg[:arg.index(':')].isdigit():
            return pkgtup.fromenvra(arg)
        else:
            return pkgtup.fromnevra(arg)
    # Okay, I don't know what this is.
    raise argparse.ArgumentTypeError(f"{arg!r} is not a filename, hex key, or RPM name")


def make_arg_parser():
    # Toplevel parser and global options
    p = argparse.ArgumentParser(
        description="make/examine .dino RPM packfiles",
    )
    p.add_argument("--verbose", "-v", action="store_true",
        help="verbose output")
    sp = p.add_subparsers(dest="cmd", metavar="COMMAND",
        help="action to perform")

    # build
    default_compressor_name = get_compressid(DEFAULT_RPMARCHIVE_COMPRESSOR).name.lower()
    assert default_compressor_name in available_compressors
    default_compress_level = DEFAULT_COMPRESSION_LEVEL[DEFAULT_RPMARCHIVE_COMPRESSOR]
    default_compress_levels = (", ".join(f'{n}={DEFAULT_COMPRESSION_LEVEL[get_compressid(n)]}'
                        for n in available_compressors))
    build = sp.add_parser("build",
        help="make a new repo or packfile")
    build.add_argument("-c", "--compress",  metavar="NAME",
        choices=available_compressors, default=default_compressor_name,
        help="compressor to use [%(choices)s] (default: %(default)s)")
    build.add_argument("--compresslevel", metavar="LEVEL", type=int, default=-1,
        help=f"compression level (defaults: {default_compress_levels})")
    for i in range(1,10):
        build.add_argument(f"-{i}", action="store_const", dest="compresslevel", const=i, help=argparse.SUPPRESS)
    # TODO: --index-varint, --index-compress, etc.
    build.add_argument("dinodir", metavar="DINODIR", type=Path,
        help="output directory")
    build.add_argument("rpmdirs", metavar="RPMDIR", nargs='+', type=Path,
        help="directories containing RPMs")

    # list
    ls = sp.add_parser("list",
        help="list contents of a packfile")
    ls.add_argument("dinofile", type=Path, metavar="DINOFILE",
        help="DINO packfile to examine")

    # info
    info = sp.add_parser("info",
        help="get more info about packfiles and objects")
    info.add_argument("dinofile", type=Path, metavar="DINOFILE",
        help="DINO packfile to examine")
    info.add_argument("object", type=DINOObjectName, metavar="OBJECT", nargs="?",
        help="object to examine")

    # extract
    extract = sp.add_parser("extract-rpm",
        help="extract RPM header and payload")
    extract.add_argument("dinofile", type=Path, metavar="DINOFILE",
        help="DINO packfile to examine")
    extract.add_argument("rpmid", type=DINOObjectName, metavar="OBJECT",
        help="RPM to extract (object ID or ENVRA/NEVRA)")
    extract.add_argument("headername", type=Path, nargs="?",
        help="Filename for RPM header (default: NEVRA.hdr)")
    extract.add_argument("payloadname", type=Path, nargs="?",
        help="Filename for RPM payload (default: NEVRA.cpio)")
    # TODO: use this
    extract.add_argument("--force", "-f", action="store_true",
        help="Overwrite existing files")
    # TODO: Just hdr or just payload
    # TODO: extract payload contents directly to OUTDIR


    return p

def build_dinodir(dinodir, rpmdirs, **dino_kwargs):
    rpmcount, rpmtotal, dinocount, dinototal = 0,0,0,0
    for name, rpms in rpmlister(rpmdirs).items():
        dinofile = (dinodir/name).with_suffix(".dino")
        print()
        rpmsize, dinosize = merge_rpms(rpms, dinofile, **dino_kwargs)
        dinocount += 1
        rpmcount += len(rpms)
        rpmtotal += rpmsize
        dinototal += dinosize
        # TODO: write index(es) into dinodir
    return rpmcount, rpmtotal, dinocount, dinototal

def list_rpms(d):
    # Group the package headers by source RPM name and build version, and
    # show each package under its respective source
    src = rpm_src_groupsort(((r.envra,k), r.srctup()) for k, r in d.iter_rpmhdrs())
    for name, evrpkgs in src.items():
        for evr, pkgs in evrpkgs.items():
            e, v, r = evr
            buildkey = 'xxxxxxxx'
            print(f'build {buildkey} {name}-{f"{e}:" if e is not None else ""}{v}-{r}')
            for p,k in pkgs:
                abbr = hexlify(k[:4]).decode('ascii')
                print(f'  rpm {abbrkey(k)} {p}')

def abbrkey(k):
    return hexlify(k[:4]).decode('ascii')

def hexkey(k):
    return hexlify(k).decode('ascii')

def print_matches(msg="matches:", rpmkeys=None, filekeys=None):
    print(msg)
    for k in rpmkeys or []:
        print(f" rpm {hexkey(k)}")
    for k in filekeys or []:
        print(f"file {hexkey(k)}")

if __name__ == '__main__':
    p = make_arg_parser()
    args = p.parse_args()
    verbose = args.verbose # TODO vprint() is silly, use logging

    if args.cmd == "build":
        if not args.dinodir.exists():
            args.dinodir.mkdir()
        if not args.dinodir.is_dir():
            p.error("{args.dinodir} exists but isn't a directory")
        r = build_dinodir(args.dinodir, args.rpmdirs,
                          compression_id=get_compressid(args.compress),
                          compresslevel=args.compresslevel)
        rpmcount, rpmtotal, dinocount, dinototal = r
        if rpmtotal:
            print(f"read {rpmcount} packages ({rpmtotal} bytes), wrote {dinocount}"
                  f" packfiles ({dinototal} bytes, {(dinototal-rpmtotal)/rpmtotal:+.1%})")
        else:
            p.exit(1, "No RPMs found. Nothing to do!\n")

    elif args.cmd == "list":
        d = DINORPMArchive(dino=DINO.from_path(args.dinofile))
        list_rpms(d)
        for k,v in sorted(d.rpmidx.items(), key=lambda i:i[0]):
            print(f" rpm {abbrkey(k)} size {v[1]:08x} offset {v[0]:08x}")

    elif args.cmd == "extract-rpm":
        d = DINORPMArchive(dino=DINO.from_path(args.dinofile))
        # TODO: refactor keymatch stuff here so multiple commands can use it
        if isinstance(args.rpmid, PartialKey):
            if args.rpmid.size == d.rpmidx.keysize:
                key = args.rpmid._bytes
                r = d.get_rpmhdr(k)
            else:
                rpmkeys = [k for k in d.rpmidx.keys() if args.rpmid.match(k)]
                if len(rpmkeys) == 0:
                    p.exit(1, f'no match for {args.rpmid}\n')
                if len(rpmkeys) > 1:
                    print_matches(msg="Multiple RPM keys matched:", rpmkeys=rpmkeys)
                    p.exit(3)
                key = rpmkeys.pop()
                r = d.get_rpmhdr(key)
        elif isinstance(args.rpmid, pkgtup):
            parttup = args.rpmid
            rpmmatches = [(k,r) for (k,r) in d.iter_rpmhdrs()
                          if parttup.match(r.pkgtup)]
            if len(rpmmatches) == 0:
                p.exit(1, f"no match for '{parttup}'\n")
            elif len(rpmmatches) > 1:
                print("Multiple RPMs matched:")
                for k, r in rpmmatches:
                    print(f" rpm {hexkey(k)} {r.envra}")
                p.exit(3)
            key, r = rpmmatches.pop()
        else:
            p.exit(1, "Don't know how to extract '{args.rpmid}'\n")

        nvra = r.envra if ':' not in r.envra else r.envra.partition(':')[2]
        pkgstem = Path(nvra)
        if not args.headername:
            args.headername = pkgstem.with_suffix(".hdr")
        if not args.payloadname:
            args.payloadname = pkgstem.with_suffix(".cpio")

        if args.force:
            mode = 'wb'
        else:
            mode = 'xb'

        print(f"{r.envra}:")
        print(f" hdr: {args.headername}")
        with open(args.headername, mode) as outf:
            d._write_rpm_hdrs(r, outf)
        print(f"cpio: {args.payloadname}")
        with open(args.payloadname, mode) as outf:
            d._write_rpm_payload(r, outf)

    elif args.cmd == "info":
        from dino import HeaderEncoding
        d = DINORPMArchive(dino=DINO.from_path(args.dinofile))
        if args.object is None:
            print(f'{args.dinofile}: {d.rpmidx.count} rpms, {d.fileidx.count} files')
            print(f'  type: {d.dino.objtype.name}, version {d.dino.VERSION}')
            print(f'  encoding: {"64" if d.dino.encoding & HeaderEncoding.SEC64 else "32"}-bit, {d.dino.encoding.byteorder().name}')
            print(f'  compression: {d.compression_id.name}')
            print(f'  name_table: {d.dino.namtab.size()} bytes')
            print(f'  section_table:')
            print('  {i:3} {name:16} {size:8} {typename:8}'.format(
                i="idx", name="name", size="size", typename="type"))
            for i,(name, sec) in enumerate(d.dino.sections()):
                # TODO: sections should handle this, so they can decode 'info'
                print(f'  {i:3} {name:16} {sec.size:08x} {sec.typeid.name:8}')
        if isinstance(args.object, Path):
            print(f'STUB: list file path {args.object}')
        elif isinstance(args.object, PartialKey):
            partkey = args.object
            # TODO: index sections should handle this
            rpmkeys = [k for k in d.rpmidx.keys() if partkey.match(k)]
            filekeys = [k for k in d.fileidx.keys() if partkey.match(k)]
            if len(rpmkeys) + len(filekeys) > 1:
                print("matches:")
                for k in rpmkeys:
                    print(f" rpm {hexkey(k)}")
                for k in filekeys:
                    print(f"file {hexkey(k)}")
            elif rpmkeys:
                k = rpmkeys.pop()
                r = d.get_rpmhdr(k)
                print(f'{r.envra} {hexkey(k)}')
                # TODO: detailed RPM info (can we do rpm -q output?)
            elif filekeys:
                k = filekeys.pop()
                print(f'fileid {hexkey(k)}')
                # TODO: file size, what RPMs contain it, etc.
            else:
                p.exit(1, f'no match for {args.object}\n')
        elif isinstance(args.object, pkgtup):
            parttup = args.object
            rpmmatches = [(k,r) for (k,r) in d.iter_rpmhdrs()
                          if parttup.match(r.pkgtup)]
            if rpmmatches:
                for k, r in rpmmatches:
                    print(f" rpm {hexkey(k)} {r.envra}")
            elif len(rpmmatches) == 1:
                k, r = rpmmatches.pop()
                # FIXME: do more info for a specific package
                print(f" rpm {hexkey(k)} {r.envra}")
            else:
                p.exit(1, f"no match for '{parttup}'\n")
