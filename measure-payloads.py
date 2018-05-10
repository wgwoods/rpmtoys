#!/usr/bin/python3

import json
import gzip

from collections import defaultdict

from rpmtoys import rpm, Tag, Attrs, VerifyAttrs
from rpmtoys import iter_repo_rpms, progress, rpmfile, rpmstat

# RPM per-file data!!
# The following are obsolete in current RPMs:
#   names contexts
# These tags are extensions that we don't use:
#   nlinks provide require signatures signaturelength
# These are only used for installed files:
#   states
# These are rare:
#   caps
# These universal but not present if not used:
#   dependsx dependsn
# These are universal but not present in some (older) RPMs:
# (e.g. python-subvertpy-0.9.1-6.fc23.x86_64)
#   class colors
# These are universal and rpm-specific:
#   langs verifyflags flags colors
# These are universal but unused:
#   rdevs
# These are universal and used in rpmstat:
#   modes inodes devices linktos username groupname mtimes sizes
# These are universal non-stat file data:
#   digests class

# TODO: explain filecolor

# SHA256 of an empty file / 0-byte string
EMPTY = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

# TODO use this!
expected_vals = {
    Tag.FILECOLORS: 0,
    Tag.FILELANGS: '',
    Tag.FILEDEVICES: 1,
    Tag.FILEVERIFYFLAGS: VerifyAttrs.ALL,
    Tag.FILEGROUPNAME: 'root',
    Tag.FILEUSERNAME: 'root',
    Tag.FILELINKTOS: '',
    Tag.FILERDEVS: 0,
    Tag.FILEMODES: 0o100644,
    Tag.FILENAMES: None,
    Tag.FILEPROVIDE: None,
    Tag.FILENLINKS: None,
    Tag.FILESIGNATURES: None,
    Tag.FILECONTEXTS: None,
    Tag.OLDFILENAMES: None,
}

def rpm_basename(rpmfn):
    return rpmfn[rpmfn.rfind('/')+1:rpmfn.rfind('.')]

def mkrpmfile(tup):
    f = rpmfile(*tup)
    return f._replace(stat=rpmstat(*f.stat),
                   flags=Attrs(f.flags),
                   verifyflags=VerifyAttrs(f.verifyflags))

def combine_hardlinks(fileinfos):
    fi = iter(fileinfos)
    fileinfo = next(fi)
    links = [(f.name, f.flags, f.verifyflags) for f in fi]
    return fileinfo, links

def expand_hardlinks(fileinfo, links):
    return [fileinfo] + [fileinfo._replace(name=n,
                                           flags=Attrs(f),
                                           verifyflags=VerifyAttrs(vf))
                         for n,f,vf in links]

# Just like normal filesystems, every rpm "inode" represents one file's
# contents and metadata, but can have multiple names (hardlinks) on a
# single filesystem. It also flattens all devices to the same
# value, so we can ignore `stat.dev`, and it flattens `stat.ino` to a
# list of ints starting from 1 - which means they have no inherent
# significance other than indicating which file entries are hardlinks.
# So 'stat', 'fclass', 'depends', and (AFAICT) 'extra' are always the same
# for two hardlinked files, and the only things that vary are the filename,
# and RPM's flags/verifyflags values.
# So we can represent the files in an RPM with a list like this:
# [(fileinfo, [(name,flags,verifyflags), ...]), ...]
def payloadinfo(rpmfn):
    inode = defaultdict(list)
    r = rpm(rpmfn)
    for f in r.payloadinfo():
        # make sure we put file entries with digests at the beginning
        if f.digest:
            inode[f.stat.ino].insert(0, f)
        else:
            inode[f.stat.ino].append(f)
    return r.envra, [inode[i] for i in sorted(inode)]

class idmap(dict):
    '''a cruddy bidirectional mapping of str <-> int'''
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        for key, val in list(self.items()):
            # watch out for key/val collisions. that's on you.
            dict.__setitem__(self, val, key)

    def __setitem__(self, key, val):
        dict.__setitem__(self, key, val)
        dict.__setitem__(self, val, key)

    def first_free_id(self):
        i = 0
        while i in self:
            i += 1
        return i

    def add(self, key):
        if type(key) != str:
            raise ValueError("key must be a string")
        if key not in self:
            self[key] = self.first_free_id()
        return self[key]

    def strdict(self):
        return {k: self[k] for k in self if type(k) != int}

# lil self-test / seed value
assert idmap(root=0)[0] == 'root'


def dump_payloaddata(repo_paths, outfile="payloaddata.json.gz"):
    uids = idmap()
    gids = idmap()
    files = dict()
    for rpmfn in progress(iter_repo_rpms(repo_paths), itemfmt=rpm_basename):
        envra, payload = payloadinfo(rpmfn)
        files[envra] = []
        for inode_ents in payload:
            f, links = combine_hardlinks(inode_ents)
            # find or allocate uid/gid
            uid = uids.add(f.stat.user)
            gid = gids.add(f.stat.group)
            # fix up the stat
            f = f._replace(stat=f.stat._replace(user=uid, group=gid))
            # add it to the list
            files[envra].append((f, links))
    print("dumping {}...".format(outfile))
    with gzip.open(outfile, 'wt') as outf:
        json.dump(dict(uid=uids.strdict(),
                       gid=gids.strdict(),
                       files=files), outf)
    return uids, gids, files


def load_payloaddata(datafile):
    # TODO: probably this doesn't convert real efficiently..
    # TODO: progress reporting?
    data = json.load(gzip.open(datafile))
    uids = idmap(data['uid'])
    gids = idmap(data['gid'])
    files = {envra:tuple(expand_hardlinks(mkrpmfile(fileinfo), links) for fileinfo, links in payload)
             for envra, payload in data['files'].items()}
    return uids, gids, files

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("TODO USAGE")
    elif sys.argv[1] == "interactive":
        pass
    elif sys.argv[1] == "generate":
        uids, gids, files = dump_payloaddata(sys.argv[3:], sys.argv[2])
