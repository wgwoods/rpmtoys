from .hdr import rpmhdr, pkgtup
from .tags import Tag, SigTag
from .file import Attrs, VerifyAttrs
from .deps import DepFlags, depinfo, deptypes, deptup
from .repo import iter_repo_rpms
from .digest import gethasher, digest
from .progress import progress

__all__ = ['rpm', 'Tag', 'Attrs', 'VerifyAttrs', 'DepFlags', 'progress',
           'iter_repo_rpms', 'pkgtup']

from collections import namedtuple, OrderedDict, Counter
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

class cpiohdr(namedtuple("cpiohdr", "name ino mode nlink mtime size dev rdev")):
    def _pack(self):
        magic = 0x070701
        name, ino, mode, nlink, mtime, size, dev, rdev = self
        devmaj, devmin = dev >> 8, dev & 0xff
        rdevmaj, rdevmin = rdev >> 8, rdev & 0xff
        uid, gid = 0, 0
        check = 0
        if name.startswith('/'):
            name = '.'+name
        name = name.rstrip('\0') + '\0'
        hdr = (f'{magic:06x}{ino:08x}{mode:08x}{uid:08x}{gid:08x}{nlink:08x}'
               f'{mtime:08x}{size:08x}{devmaj:08x}{devmin:08x}{rdevmaj:08x}'
               f'{rdevmin:08x}{len(name):08x}{check:08x}{name}')
        padto = (len(hdr)+3) & ~0x3
        hdr += '\0'*(padto-len(hdr))
        return bytes(hdr,'utf8')

    @classmethod
    def _trailer(cls):
        return cls('TRAILER!!!',0,0,1,0,0,0,0)


# And here's the big fancy thing that holds all per-file RPM data
rpmfile = namedtuple("rpmfile",
                     "name digest stat nlink fclass flags verifyflags depends extra")

class rpm(rpmhdr):
    '''
    A slightly higher-level interface for inspecting RPM contents.
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

    def payload_iter(self):
        from libarchive import stream_reader
        with self.open_payload() as payload_fobj:
            with stream_reader(payload_fobj,
                               format_name=payload_fobj.format or 'all',
                               filter_name=payload_fobj.compressor or 'all',
                               ) as payload:
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

    srctup = buildtup

    def digest(self, md5=True, sha1=True, sha256=True):
        '''
        Return digests of this RPM, as rpm would calculate them.
        Note that the MD5 covers the header and payload, while
        SHA1 and SHA256 only cover the header - but the header
        contains digests for each file, so we can still verify the
        integrity of the _contents_ of the payload even if the
        payload itself changes (e.g. if we re-ordered files)
        '''
        return digest(self.name, md5=md5, sha1=sha1, sha256=sha256)

    def _getsigdigests(self):
        from .tags import DIGEST_SIGTAGS
        return {tag.name:self.sig.getval(tag)
                for tag in DIGEST_SIGTAGS
                if tag in self.sig.tagent}

    def _getsignatures(self):
        from .tags import SIGNATURE_SIGTAGS
        return {tag.name:self.sig.getval(tag)
                for tag in SIGNATURE_SIGTAGS
                if tag in self.sig.tagent}

    def checkdigests(self, hdr=True, payload=True, filedigests=True):
        '''
        Check RPM package/file/payload digests against expected values.
        An RPM's signature header can
        contain the following digests (see `digest()`):
            sha1:   SHA1 of the hdr section
            sha256: SHA256 of the hdr section
            md5:    MD5 of the hdr section + payload

        The RPM hdr can also contain the FILEDIGESTS tag, which will have
        digests of each file in the payload. The digest algorithm is specified
        by the FILEDIGESTALGO tag.
        '''
        result = dict()
        if hdr or payload:
            # Get sighdr digest values (if present)
            sig = self._getsigdigests()
            dig = self.digest(md5=payload and 'MD5' in sig,
                              sha1=hdr and 'SHA1' in sig,
                              sha256=hdr and 'SHA256' in sig)
            res = {n:sig[n]==dig[n] for n in dig}
            if payload:
                result['payload'] = {'MD5':res.pop('MD5')}
            if hdr:
                result['hdr'] = res
        if filedigests:
            result['filedigests'] = self.checkfiledigests()
        # TODO: Tag.PAYLOADDIGEST, if present
        return result

    # TODO: this should get imported from rpmtoys.gpg or whatev
    DEFAULT_KEYDIR = '/etc/pki/rpm-gpg'
    def checksigs(self, keydir=None, hdr=True, payload=True):
        if not keydir:
            keydir = self.DEFAULT_KEYDIR
        sig = self._getsignatures() # {'PGP':b'...', RSA:b'...'}
        # TODO: actually check signatures!!
        #   SigTag.RSA for header
        #   SigTag.PGP for header+payload
        raise NotImplementedError

    def iterdigestfiles(self, algo=None):
        if algo is None:
            algo = self.hdr.getval(Tag.FILEDIGESTALGO)
        for e in self.payload_iter():
            if e.isreg:
                h = gethasher(algo)
                for block in e.get_blocks():
                    h.update(block)
                yield (e.name[1:], h.hexdigest())

    def checkfiledigests(self):
        dig = dict(zip(self.iterfiles(), self.getval(Tag.FILEDIGESTS)))
        return {n:dig.get(n)==d for n,d in self.iterdigestfiles()}

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

    def iterdigests(self):
        '''Yield each of the file digests if FILEDIGESTS is present'''
        yield from self.getval(Tag.FILEDIGESTS, [])

    def iterflags(self):
        yield from map(Attrs, self.getval(Tag.FILEFLAGS, []))

    def iterverifyflags(self):
        yield from map(VerifyAttrs, self.getval(Tag.FILEVERIFYFLAGS, []))

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

    def iterlinktos(self):
        yield from self.getval(Tag.FILELINKTOS, [])

    rpmfileiter = dict(
        name=iterfiles,
        digest=iterdigests,
        stat=iterfstat,
        nlink=iternlink,
        fclass=iterfclass,
        flags=iterflags,
        verifyflags=iterverifyflags,
        depends=iterfiledeps,
        extra=iterfextras,
    )

    def iterfileinfo(self, what=("all",)):
        '''
        Return an iterator that yields tuples of each of the rpmfile fields
        listed in `what`.
        If what == ("all",) then you get all fields - but you probably want
        iterrpmfiles(), which yields sensible rpmfile objects.
        '''
        # Possibly unnecessary shortcut..
        if self.nfiles() == 0:
            yield from []
        if "all" in what:
            what = self.rpmfileiter.keys()
        yield from zip_longest(*(self.rpmfileiter[k](self) for k in what))

    def iterrpmfiles(self):
        '''
        Return an iterator that yields rpmfile (q.v.) objects corresponding to
        each file listed in the RPM header.
        '''
        yield from (rpmfile(*f) for f in self.iterfileinfo(what=rpmfile._fields))

    def itercpiohdrs(self):
        for i in zip(self.iterfiles(),
                     self.getval(Tag.FILEINODES),
                     self.getval(Tag.FILEMODES),
                     self.iternlink(),
                     self.getval(Tag.FILEMTIMES),
                     self.getval(Tag.FILESIZES),
                     self.getval(Tag.FILEDEVICES),
                     self.getval(Tag.FILERDEVS)):
            yield cpiohdr._make(i)

    def depnames(self):
        return [d.name for d in deptypes if self.getcount(d.nametag)]

    def iterdeps(self, name):
        dep = depinfo[name]
        deptags = (dep.nametag, dep.flagtag, dep.vertag, dep.idxtag)
        for n, f, v, i in self.zipvals(*deptags):
            yield deptup(n, DepFlags(f), v, i)

    def getdeps(self, name):
        return list(self.iterdeps(name))

    def alldeps(self):
        return {name:self.getdeps(name) for name in self.depnames()}
