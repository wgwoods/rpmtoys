# repotoys.primary - parse primary.xml

import gzip
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from binascii import unhexlify

# Some helpers for xmlns handling / tag comparison..
def MD(tag):
    return ET.QName('http://linux.duke.edu/metadata/common',tag).text
def RPM(tag):
    return ET.QName('http://linux.duke.edu/metadata/rpm',tag).text
def FL(tag):
    return ET.QName('http://linux.duke.edu/metadata/filelists',tag).text

#ET.register_namespace('repo', 'http://linux.duke.edu/metadata/repo')
#def REPO(tag):
#    return ET.QName('http://linux.duke.edu/metadata/repo',tag).text

# TODO: check for other tags in filelists, other, etc.
MDTAG = {tag:MD(tag) for tag in
         ('metadata', 'package', 'name', 'arch', 'version', 'checksum',
          'summary', 'description', 'packager', 'url', 'time', 'size',
          'location', 'format', 'file')}

RPMTAG = {tag:RPM(tag) for tag in
          ('buildhost', 'conflicts', 'enhances', 'entry', 'group',
           'header-range', 'license', 'obsoletes', 'provides', 'recommends',
           'requires', 'sourcerpm', 'suggests', 'supplements', 'vendor')}

FLTAG = {tag:FL(tag) for tag in
         ('filelists', 'package', 'version', 'file')}

# Register the XML namespaces used by primary.xml so our serialization looks
# like the existing file contents..
ET.register_namespace('',    'http://linux.duke.edu/metadata/common')
ET.register_namespace('rpm', 'http://linux.duke.edu/metadata/rpm')


@dataclass(frozen=True)
class PackageElement:
    elem: Any = field(repr=False)
    name: str
    epoch: int
    version: str
    release: str
    arch: str

    # TODO: maybe I oughtta just write my own __repr__..
    pkgid: bytes = field(repr=False, compare=True)
    size: int = field(repr=False)
    instsize: int = field(repr=False)
    filetime: int = field(repr=False)
    buildtime: int = field(repr=False)
    hdrsize: int = field(repr=False)
    mditems: int = field(repr=False)
    # NOTE: calculating mdsize precisely takes an extra ~1ms per element,
    # or ~10-20sec per repo -> ~3hrs for my dataset of ~800 metadata samples,
    # so... it'll default to being None.
    # mdsize correlates very closely with mditems, which is 100x faster to
    # calculate, so you'll generally be fine using that instead.
    # (We can approximate mdsize by (mditems*62)+626 or (mditems*90).. or at
    # least that's what scipy.stats.linregress() etc. are telling me.)
    mdsize: int = field(repr=False, default=None)

    @property
    def nevra(self):
        if self.epoch == 0:
            return f'{self.name}-{self.version}-{self.release}.{self.arch}'
        else:
            return f'{self.name}-{self.epoch}:{self.version}-{self.release}.{self.arch}'

    @property
    def envra(self):
        if self.epoch == 0:
            return self.nevra
        else:
            return f'{self.epoch}:{self.name}-{self.version}-{self.release}.{self.arch}'

    @staticmethod
    def find_pkgid(elem):
        for ck in elem.iterfind(MDTAG['checksum']):
            if ck.attrib.get('pkgid','') == 'YES':
                return unhexlify(ck.text)

    @staticmethod
    def elem_mdsize(elem):
        # FIXME: this is a goofy, snow, inefficient way to handle this.
        # I'd rather just get the file offsets in _iterparse() but we can't
        # be sure that fobj.tell() is correct and the parser doesn't otherwise
        # tell us how much data it's read.

        s = ET.tostring(elem)
        # Tweak size so it skips the xmlns stuff and extra spaces
        return len(s) - 93 - s.count(b' />')

    @staticmethod
    def elem_mditems(elem):
        return sum(1 for _ in elem.find(MDTAG['format']).iter('*')) - 1


    @classmethod
    def from_elem(cls, e, mdsize=False, save_elem=False):
        # NOTE: you'd think it'd be faster to manually iterate through the
        # child tags exactly once rather than searching through them
        # repeatedly, but that actually turns out to be slower. Weird, huh?
        v = e.find(MDTAG['version'])
        n = e.find(MDTAG['name'])
        a = e.find(MDTAG['arch'])
        s = e.find(MDTAG['size'])
        t = e.find(MDTAG['time'])
        h = e.find(f"{MDTAG['format']}/{RPMTAG['header-range']}")
        return cls(
            elem=e if save_elem else None,
            name=n.text,
            epoch=int(v.attrib['epoch']),
            version=v.attrib['ver'],
            release=v.attrib['rel'],
            arch=a.text,
            pkgid=PackageElement.find_pkgid(e),
            size=int(s.attrib['package']),
            instsize=int(s.attrib['installed']),
            filetime=int(t.attrib['file']),
            buildtime=int(t.attrib['build']),
            hdrsize=int(h.attrib['end'])-int(h.attrib['start']),
            mditems=PackageElement.elem_mditems(e),
            mdsize=PackageElement.elem_mdsize(e) if mdsize else None,
        )

@dataclass(frozen=True)
class RPMEntryElement:
    name: str
    flags: str # FIXME: rpmtoys.DepFlags
    epoch: int
    ver: str # FIXME: rpmtoys.pkgtup?
    rel: str

@dataclass(frozen=True)
class RPMFormatElement:
    license: str
    vendor: str
    group: str
    buildhost: str
    sourcerpm: str
    header_range: (int, int)
    provides: [RPMEntryElement]
    requires: [RPMEntryElement]
    conflicts: [RPMEntryElement]
    obsoletes: [RPMEntryElement]
    recommends: [RPMEntryElement]
    suggests: [RPMEntryElement]
    supplements: [RPMEntryElement]
    enhances: [RPMEntryElement]

@dataclass(frozen=True)
class FilelistPackage:
    name: str
    epoch: str
    version: str
    release: str
    arch: str
    pkgid: bytes = field(repr=False, compare=True)
    fileitems = [(str, str)]

    @property
    def dirs(self):
        return [p for t,p in self.fileitems if t == 'dir']

    @property
    def files(self):
        return [p for t,p in self.fileitems if t == '']

    @property
    def ghosts(self):
        return [p for t,p in self.fileitems if t == 'ghost']

    @classmethod
    def from_elem(cls, e):
        if not (e.tag == FLTAG['package']):
            raise ValueError("Invalid element tag {e.tag!r}")
        v = e.find(MDTAG['version'])
        fi = e.iterfind(FLTAG['file'])
        return cls(name=e.attrib.get('name'),
                   arch=e.attrib.get('arch'),
                   epoch=int(v.attrib.get('epoch','0')),
                   version=v.attrib.get('ver'),
                   release=v.attrib.get('rel'),
                   files=[(f.attrib.get('type',''), f.text) for f in fi],
                   )




class XMLMD(object):
    def __init__(self, xmlfn):
        self.name = xmlfn

    def _open(self):
        if self.name.endswith(".xml.gz"):
            return gzip.open(self.name)
        elif self.name.endswith(".xml"):
            return open(self.name)
        else:
            raise NotImplementedError("unhandled metadata filetype")

    def _iterparse(self, events=None):
        with self._open() as fobj:
            yield from ET.iterparse(fobj, events=events)

    def num_packages(self):
        for event, elem in self._iterparse(events=('start',)):
            if elem.tag == self.TOPLEVELTAG:
                return int(elem.attrib['packages'])


class Primary(XMLMD):
    TOPLEVEL_TAG = MDTAG['package']

    def iter_package_elem(self, mdsize=False):
        for event, elem in self._iterparse(events=('end',)):
            if elem.tag == MDTAG['package']:
                yield PackageElement.from_elem(elem, mdsize=mdsize)
                elem.clear()

class Filelists(XMLMD):
    TOPLEVEL_TAG = FLTAG['filelists']

    def iter_package_filelists(self):
        for event, elem in self._iterparse(events=('end',)):
            if elem.tag == FLTAG['package']:
                yield FilelistPackage.from_elem(elem)
                elem.clear()

if __name__ == '__main__':
    import sys
    for fn in sys.argv[1:]:
        prim = Primary(fn)
        pkgs = []
        for pkg in prim.iter_package_elem():
            print(pkg)
            pkgs.append(pkg)
            assert(pkg.name)
