#!/usr/bin/python3

import os
import hashlib
import requests
import datetime
import xml.etree.cElementTree as ET

def REPO(tag):
    return ET.QName('http://linux.duke.edu/metadata/repo',tag).text

def RPM(tag):
    return ET.QName('http://linux.duke.edu/metadata/rpm',tag).text

def normalize_url(url):
    url = url.rstrip('/')
    if url.endswith("/repodata"):
        url = url[:-9]
    return url.rstrip('/')

def repomd_iter_files(repomd):
    for d in repomd.findall(REPO('data')):
        ty = d.attrib['type']
        fn = d.find(REPO('location')).attrib['href']
        size = int(d.find(REPO('size')).text)
        ck = d.find(REPO('checksum'))
        algo = ck.attrib['type']
        checksum = ck.text
        yield (ty,fn,size,algo,checksum)

def repomd_ts(repomd):
    revision = repomd.find(REPO('revision'))
    return int(revision.text)

def fetch_parse_repomd(url):
    r = requests.get(url+'/repodata/repomd.xml')
    r.raise_for_status()
    r.encoding=('utf-8')
    return ET.fromstring(r.content)


def fetchfile(url, outfile, algo=None):
    r = requests.get(url)
    r.raise_for_status()
    size = 0
    h = None
    if algo in hashlib.algorithms_available:
        h = hashlib.new(algo)
    with open(outfile, 'wb') as fobj:
        for chunk in r.iter_content(chunk_size=4096):
            size += fobj.write(chunk)
            if h:
                h.update(chunk)
    return (size, h.hexdigest() if h else None)

def fetchmd(url, outdir, which=("primary", "filelists", "other", "group")):
    url = normalize_url(url)
    repomd = fetch_parse_repomd(url)
    ts = repomd_ts(repomd)
    dt = datetime.datetime.utcfromtimestamp(ts)
    ts_str = dt.strftime("%Y%m%d.%H%M")
    md_dir = os.path.join(outdir, ts_str)

    if os.path.isdir(md_dir):
        print(md_dir, "already exists")
        return
    os.makedirs(md_dir)
    print(md_dir, "created")

    for ty,fn,size,algo,digest in repomd_iter_files(repomd):
        if ty not in which:
            continue
        print("  fetching {:12}".format(ty+'...'), end=' ', flush=True)
        outfile = os.path.join(md_dir, os.path.basename(fn))
        (wsize, wdigest) = fetchfile(url+'/'+fn, outfile, algo)
        if size != wsize:
            print("ERROR: size mismatch (size={}, expected={})".format(wsize,size))
        elif digest != wdigest:
            print("ERROR: {} mismatch".format(algo))
        else:
            print("{:10} bytes ok {} ok".format(size,algo))

from collections import namedtuple
Image = namedtuple("Image", ["path", "version", "variant", "arch", "name"])
# return list of Image namedtuples
def list_releases(url):
    import re
    release_re = re.compile(r'^(.*/releases/(\d\d)/(\w+)/(\w+).*/([^/]+))$')
    r = requests.get(url)
    r.raise_for_status()
    r.encoding = 'utf-8'
    for line in r.text.splitlines():
        m = release_re.match(line)
        if m:
            yield Image(*m.groups())

if __name__ == '__main__':
    ARCH='x86_64'
    OUTDIR='/srv/metadata'
    MIRROR_URL = 'https://download-ib01.fedoraproject.org/pub/fedora'
    IMAGELIST_URL = MIRROR_URL+'/imagelist-fedora'
    versions = set(i.version for i in list_releases(IMAGELIST_URL) if i.arch == ARCH)
    for v in versions:
        RELEASE_URL = MIRROR_URL+'/linux/releases/{}/Everything/{}/os'.format(v,ARCH)
        if int(v) < 28:
            UPDATES_URL = MIRROR_URL+'/linux/updates/{}/{}'.format(v,ARCH)
        else:
            UPDATES_URL = MIRROR_URL+'/linux/updates/{}/Everything/{}'.format(v,ARCH)
        if not os.path.isdir(OUTDIR):
            print("No such dir", OUTDIR)
            raise SystemExit(1)
        fetchmd(RELEASE_URL, os.path.join(OUTDIR,v,ARCH,'release'))
        fetchmd(UPDATES_URL, os.path.join(OUTDIR,v,ARCH,'updates'))
