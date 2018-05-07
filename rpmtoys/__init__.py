from .hdr import rpmhdr
from .tags import Tag
from .file import Attrs, VerifyAttrs
from .deps import DepFlags, depinfo, deptypes
from .repo import iter_repo_rpms
from .progress import progress

__all__ = ['rpm', 'Tag', 'Attrs', 'VerifyAttrs', 'DepFlags', 'progress',
           'iter_repo_rpms']

from collections import namedtuple, OrderedDict
from itertools import zip_longest

# (mode, ino, dev, username, groupname, size, mtime)
# ..it's *close* to python's os.stat() output, at least.
rpmstat_tags = OrderedDict([
    ('mode', Tag.FILEMODES),
    ('ino', Tag.FILEINODES),
    ('dev', Tag.FILEDEVICES),
    ('user', Tag.FILEUSERNAME),
    ('group', Tag.FILEGROUPNAME),
    ('size', Tag.FILESIZES),
    ('mtime', Tag.FILEMTIMES),
])
rpmstat = namedtuple("rpmstat", rpmstat_tags)
rpmstat._tags = rpmstat(*rpmstat_tags.values())

# File tags that are unlikely to appear
extra_tags = OrderedDict([
    ('lang', Tag.FILELANGS),
    ('color', Tag.FILECOLORS),
    ('rdev', Tag.FILERDEVS),
    ('caps', Tag.FILECAPS),
    ('linkto', Tag.FILELINKTOS),
    ('names',   Tag.FILENAMES),
    ('provide', Tag.FILEPROVIDE),
    ('require', Tag.FILEREQUIRE),
    ('nlinks',  Tag.FILENLINKS),
    ('signature', Tag.FILESIGNATURES),
    ('contexts', Tag.FILECONTEXTS),
    ('oldnames', Tag.OLDFILENAMES),
])
extras = namedtuple("extras", extra_tags)
extras._tags = extras(*extra_tags.values())

# And here's the big fancy thing that holds all per-file RPM data
rpmfile = namedtuple("rpmfile",
                     "name digest stat fclass flags verifyflags depends extra")

class rpm(rpmhdr):
    '''
    A slightly higher-level interface for inspecting RPM headers.
    '''
    def getval(self, tag, default=None):
        return self.hdr.getval(tag, default)

    def getcount(self, tag):
        return self.hdr.tagcnt.get(tag, 0)

    def zipvals(self, *tags):
        return tuple(zip_longest(*(self.getval(t,[]) for t in tags)))

    def nfiles(self):
        return self.getcount(Tag.BASENAMES)

    def iterfiles(self):
        '''Yield each of the (complete) filenames in this RPM.'''
        # NOTE: we don't use "getval" here because filenames are _always_
        # encoded in UTF-8, regardless of the package encoding. In theory.
        dirnames = self.hdr.tagval.get(Tag.DIRNAMES)
        dirindexes = self.hdr.tagval.get(Tag.DIRINDEXES,[])
        basenames = self.hdr.tagval.get(Tag.BASENAMES,[])
        for diridx, basename in zip(dirindexes, basenames):
            yield (dirnames[diridx]+basename).decode('utf-8')

    def iterfclass(self):
        '''Yield the file "class" for each file in this RPM.'''
        classdict = self.getval(Tag.CLASSDICT)
        for idx in self.getval(Tag.FILECLASS,[]):
            yield classdict[idx]

    def iterfiledeps(self):
        '''
        Yield per-file dependencies for each file in this RPM.
        Each item is a list of (depchar, idx) pairs that correspond to the
        dependency type and an index in that dependency list.
        '''
        dependsdict = self.getval(Tag.DEPENDSDICT,[])
        for x, n in self.zipvals(Tag.FILEDEPENDSX, Tag.FILEDEPENDSN):
            # This is pretty gross right here, RPM...
            yield [(chr(d >> 24), d & 0x00ffffff) for d in dependsdict[x:x+n]]

    def iterfstat(self):
        for s in self.zipvals(*rpmstat._tags):
            yield rpmstat(*s)

    def iterfextras(self):
        for ex in self.zipvals(*extras._tags):
            yield {k:v for k,v in zip(extras._fields, ex) if v}

    def depnames(self):
        return [d.name for d in deptypes if self.getcount(d.nametag)]

    def iterdeps(self, name):
        dep = depinfo[name]
        deptags = (dep.nametag, dep.flagtag, dep.vertag, dep.idxtag)
        for n, f, v, i in self.zipvals(*deptags):
            yield (n, DepFlags(f), v, i)

    def getdeps(self, name):
        return list(self.iterdeps(name))

    def alldeps(self):
        return {name:self.getdeps(name) for name in self.depnames()}

    def payloadinfo(self):
        if not self.nfiles():
            return []
        return (rpmfile(*f) for f in zip_longest(self.iterfiles(),
                                                 self.getval(Tag.FILEDIGESTS),
                                                 self.iterfstat(),
                                                 self.iterfclass(),
                                                 map(Attrs, self.getval(Tag.FILEFLAGS)),
                                                 map(VerifyAttrs, self.getval(Tag.FILEVERIFYFLAGS)),
                                                 self.iterfiledeps(),
                                                 self.iterfextras()))