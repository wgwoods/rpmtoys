#!/usr/bin/python3

from rpmtoys import rpm, Attrs
from os import makedev
from stat import S_ISDIR

def checkprob(itemname, rpmval, payloadval):
    if payloadval is not None and rpmval is None:
        return "{} value missing from rpm (payloadval={!r})".format(itemname, payloadval)
    if payloadval is None and rpmval is not None:
        return "{} value missing from payload (rpmval={!r})".format(itemname, rpmval)
    try:
        if rpmval != payloadval:
            return "{} mismatch (rpmval={!r}, payloadval={!r})".format(itemname, rpmval, payloadval)
    except ValueError as e:
        return "{} ValueError (rpmval={!r}, payloadval={!r})".format(itemname, rpmval, payloadval)
    except TypeError as e:
        return "{} TypeError (rpmval={!r}, payloadval={!r})".format(itemname, rpmval, payloadval)

def checkprobs(probspecs):
    probs = []
    for itemname, rpmval, payloadval in probspecs:
        prob = checkprob(itemname, rpmval, payloadval)
        if prob:
            probs.append(prob)
    return probs

def cpio_sorted(hdrinfo):
    hardlinks = []
    for i in hdrinfo:
        # %ghost files don't show up in the payload, obviously
        if Attrs.GHOST in i.flags:
            continue
        # hardlinks get shuffled to the end of the archive
        if i.nlink > 1:
            hardlinks.append(i)
        # spit out everything else in header order
        else:
            yield i
    # spit out hardlinks at the end
    while hardlinks:
        yield hardlinks.pop(0)

def compare_payload_to_hdr(rpmfn):
    r = rpm(rpmfn)
    probcount = 0
    probs = []
    names = []
    with r.payload_reader() as payload:
        for payi, hdri in zip(payload, cpio_sorted(r.payloadinfo())):
            names.append(hdri.name)
            p = checkprobs([
                ('name',  '.'+hdri.name,   payi.name),
                ('mtime', hdri.stat.mtime, payi.mtime),
                ('mode',  hdri.stat.mode,  payi.mode),
                ('rdev',  hdri.extra.get('rdev',0), makedev(payi.rdevmajor, payi.rdevminor)),
                # It seems these things are always 0 in the CPIO headers...
                #('user',  hdri.stat.user,  payi.uid or "root"),
                #('group', hdri.stat.group, payi.gid or "root"),
                ('uid',   0,               payi.uid),
                ('gid',   0,               payi.gid),
                ('atime', 0,               payi.atime),
                ('ctime', 0,               payi.ctime),
                ('birthtime', 0,           payi.birthtime),
            ])
            # CPIO doesn't store size for directories or hardlinks, I guess?
            if not (payi.isdir or (hdri.nlink > 1 and not payi.islnk)):
                p += checkprobs([('size',  hdri.stat.size,  payi.size)])
            # Stash list of problems for this file
            probs.append(p)
            # Increase counter if we found any problems
            if p:
                probcount += 1

    print("{}: {} files checked, {} problems".format(rpmfn, len(names), probcount))
    if probcount:
        for fname, fprobs in zip(names, probs):
            if fprobs:
                print("  "+fname+":")
                for p in fprobs:
                    print("    "+p)

if __name__ == '__main__':
    import sys
    for fn in sys.argv[1:]:
        compare_payload_to_hdr(fn)
