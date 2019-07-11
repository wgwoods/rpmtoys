from .hdr import rpmhdr, pkgtup
from .tags import Tag, SigTag
from .file import Attrs, VerifyAttrs
from .deps import DepFlags, depinfo, deptypes
from .repo import iter_repo_rpms
from .progress import progress

__all__ = ['rpm', 'Tag', 'Attrs', 'VerifyAttrs', 'DepFlags', 'progress',
           'iter_repo_rpms', 'pkgtup']

from collections import namedtuple, OrderedDict, Counter
from itertools import zip_longest

# optional external dependency
try:
    from .payload import libarchive_payload_reader
except ImportError:
    libarchive_payload_reader = None

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
                     "name digest stat nlink fclass flags verifyflags depends extra")

class rpm(rpmhdr):
    '''
    A slightly higher-level interface for inspecting RPM headers.
    '''
    def __repr__(self):
        return '<{}.{}({!r})>'.format(self.__module__, self.__class__.__name__, self.name)

    def dump(self):
        return {
            # TODO: add lead
            #'lead': self.lead._asdict(),
            'sig': {SigTag(t).shortname:self.sig.getval(t)
                    for t in self.sig.tagval},
            'hdr': {Tag(t).shortname:self.hdr.getval(t)
                    for t in self.hdr.tagval},
        }

    payload_reader = libarchive_payload_reader
    def payload_iter(self):
        with self.payload_reader() as payload:
            for entry in payload:
                yield entry

    def itertags(self, which='all'):
        okvals = ('sig', 'hdr', 'all')
        if which not in okvals:
            raise ValueError(f"'which' should be one of {okvals}")
        if which in ('sig', 'all'):
            for t in self.sig.tagent:
                yield (SigTag(t), self.sig.getval(t))
        if which in ('hdr', 'all'):
            for t in self.hdr.tagent:
                yield (Tag(t), self.hdr.getval(t))

    def getval(self, tag, default=None):
        return self.hdr.getval(tag, default)

    def getcount(self, tag):
        return self.hdr.tagent.get(tag).count if tag in self.hdr.tagent else 0

    def zipvals(self, *tags):
        return tuple(zip_longest(*(self.getval(t,[]) for t in tags)))

    def buildtup(self):
        src = self.getval(Tag.SOURCERPM)
        if src is None:
            return None
        if src.endswith('.rpm'):
            src = src[:-4]
        return pkgtup.fromenvra(src)._replace(epoch=self.pkgtup.epoch,
                                              arch=self.pkgtup.arch)

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

    def iternlink(self):
        # It's super cool how RPM doesn't actually use FILENLINKS so we have to
        # figure out what files are actually hardlinks by making two passes
        # through FILEINODES
        inodes = self.getval(Tag.FILEINODES, [])
        nlinks = Counter(inodes)
        for ino in inodes:
            yield nlinks[ino]

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
                                                 self.iternlink(),
                                                 self.iterfclass(),
                                                 map(Attrs, self.getval(Tag.FILEFLAGS)),
                                                 map(VerifyAttrs, self.getval(Tag.FILEVERIFYFLAGS)),
                                                 self.iterfiledeps(),
                                                 self.iterfextras()))
