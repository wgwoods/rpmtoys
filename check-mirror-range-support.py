#!/usr/bin/python3

import requests
import argparse
from urllib.parse import urlparse

def known_arch(a):
    if a not in {'x86_64', 'i386', 'aarch64', 'armhfp', 'ppc64', 'ppc64le',
                 's390', 's390x'}:
        raise ValueError("unknown arch '{}'".format(a))
    return a

def country_code_list(a):
    if a in {'none', 'default'}:
        return None
    if a in {'global', 'all', 'any'}:
        return 'global'
    countries = []
    for cc in a.lower().split(','):
        cc = cc.strip()
        if len(cc) == 2:
            raise ValueError("Invalid 2-letter country code '{}'".format(cc))
        countries.append(cc)
    return ','.join(countries)

def parse_args():
    p = argparse.ArgumentParser(
        description="Check Fedora mirrors for HTTP/1.1 Range Request support",
        epilog="""
        Check support for HTTP/1.1 Range Requests (RFC7233) on a set of Fedora
        mirrors by getting a list of mirrors for the given repo (default:
        Fedora 29 x86_64) from MirrorManager, then trying to get part of
        `repodata/repomd.xml` from each mirror.
        """)
    p.add_argument("--version", "-v", type=int,
                   help="Fedora version to use (default: 29)",
                   default=29)
    p.add_argument("--arch", "-a", type=known_arch,
                   help="Arch to use (default: x86_64)",
                   default='x86_64')
    p.add_argument("--country", "-c", type=country_code_list,
                   help="Location of mirrors to check (2-letter ISO code)",
                   default="global")
    p.add_argument("--mirrorlist", action='store_true', default=True,
                   help="Get plain-text mirrorlist (default)")
    p.add_argument("--nomirrorlist", action='store_false', dest="mirrorlist",
                   help="Don't get the plain-text mirrorlist")
    p.add_argument("--scrape", action='store_true',
                   help="Scrape the mirrormanager HTML for mirror URLs")
    p.add_argument("--metalink", action='store_true',
                   help="Get metalink XML instead of plain-text mirrorlist")
    return p.parse_args()

def getmirrorlist(version='29', arch='x86_64', repo='fedora', country='global'):
    metalink_url = 'http://mirrors.fedoraproject.org/mirrorlist?repo={repo}-{version}&arch={arch}'
    if country:
        metalink_url += '&country={}'.format(country)
    resp = requests.get(metalink_url.format(repo=repo, version=version, arch=arch))
    return [line.strip() for line in resp.text.splitlines() if line.startswith('http')]

def getmetalinkmirrorlist(version='29', arch='x86_64', repo='fedora', country='global'):
    from xml.etree import cElementTree as ET
    metalink_url = 'http://mirrors.fedoraproject.org/metalink?repo={repo}-{version}&arch={arch}'
    if country:
        metalink_url += '&country={}'.format(country)
    resp = requests.get(metalink_url.format(repo=repo, version=version, arch=arch))
    xml = ET.fromstring(resp.text)
    ts = int(xml.find('.//{http://fedorahosted.org/mirrormanager}timestamp').text)
    mirrors = list(url.text for url in xml.iter('{http://www.metalinker.org/}url'))
    return (ts, mirrors)


def scrapemirrormanager(version='29', arch='x86_64'):
    # This is gross but mirrorlist doesn't give us a full list so..
    from html.parser import HTMLParser
    class MirrorlistScraper(HTMLParser):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._tagstack = list()
            self._curhost = None
            self._cursect = None
            self._href = None
            self._mirrors = dict()
            self._row = 0
            self._col = 0

        def handle_starttag(self, tag, attrs):
            self._tagstack.append(tag)
            if self._cursect:
                if tag == 'a':
                    for name, val in attrs:
                        if name == 'href':
                            self._href = val
                            break
                elif tag == 'br':
                    self._cursect = None

        def handle_data(self, data):
            # FIXME: this could be called in the middle of the data
            curtag = self._tagstack[-1] if self._tagstack else ''
            if curtag == 'td':
                if self._col == 2:
                    self._curhost = data
                    self._mirrors[self._curhost] = dict()
                elif self._col == 3:
                    if 'Fedora Linux' in data:
                        self._cursect = 'fedora'
                    # TODO: epel
            elif curtag == 'a' and self._href:
                self._mirrors[self._curhost][data] = self._href

        def handle_endtag(self, tag):
            self._tagstack.pop()
            if tag == 'tr':
                self._row += 1
                self._col = 0
                self._cursect = None
                self._curhost = None
            elif tag == 'td':
                self._col += 1
            elif tag == 'a':
                self._href = None

    s = MirrorlistScraper()
    r = requests.get('https://admin.fedoraproject.org/mirrormanager/mirrors/Fedora/{}'.format(version))
    s.feed(r.text)
    repomd_path = '/releases/{}/Everything/{}/os/repodata/repomd.xml'.format(version, arch)
    mirrors = [baseurl+repomd_path for host, proto in s._mirrors.items()
                                   for scheme, baseurl in proto.items()
                                   if baseurl.startswith("http")]
    return mirrors

# TODO: try multipart request
# TODO: see if we can pipeline requests with Transfer-Encoding: chunked
# TODO: also check HTTP/2?
def supports_range_request(url):
    try:
        rr = requests.get(url, headers={'Range':'bytes=0-31'})
        rr_ok = (rr.status_code == 206 and len(rr.content) == 32)
        httpver = rr.raw.version # (10 == HTTP/1.0, 11 == HTTP/1.1)
        # mp = requests.get(url, headers={'Range':'bytes=16-24,28-31'})
        #TODO: gotta parse multipart/byteranges response..
    except requests.exceptions.ConnectionError:
        return None
    else:
        return (rr.status_code == 206 and len(rr.content) == 32)


if __name__ == '__main__':
    args = parse_args()
    mirrors = []
    if args.mirrorlist:
        print("getting mirrorlist...")
        m = getmirrorlist(version=args.version, arch=args.arch, country=args.country)
        print("got {} mirrors".format(len(m)))
        mirrors += m
    if args.scrape:
        print("scraping mirrormanager...")
        m = scrapemirrormanager(version=args.version, arch=args.arch)
        print("got {} mirrors".format(len(m)))
        mirrors += m
    if args.metalink:
        print("getting metalink...")
        m = getmetalinkmirrorlist(version=args.version, arch=args.arch, country=args.country)
        print("got {} mirrors".format(len(m)))
        mirrors += m
    print("removing duplicates...")
    http_mirrors = {u.netloc:u.geturl()
                    for u in (urlparse(m) for m in mirrors)
                    if u.scheme in ("http", "https")}
    results = dict()
    num_mirrors = len(http_mirrors)
    print("{} hosts to check".format(num_mirrors))

    for n, (host, url) in enumerate(http_mirrors.items(), 1):
        print("[{:3}/{:3}] {}: ".format(n, num_mirrors, host), end='', flush=True)
        if supports_range_request(url):
            print("yes")
            results[host] = True
        else:
            print("no")
            results[host] = False

    range_ok_count = sum(1 for r in results.values() if r)
    print("{:3}/{:3} ({:.1%}) support Range requests!".format(range_ok_count, num_mirrors, range_ok_count/num_mirrors))
