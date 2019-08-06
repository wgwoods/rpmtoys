#!/usr/bin/python3

import gzip
import json

from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import namedtuple
from binascii import unhexlify
from base64 import b85encode, b85decode

from repotoys import Primary

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

from matplotlib.ticker import FuncFormatter

def ts2datetime(ts):
    return datetime.strptime(ts, "%Y%m%d.%H%M")

def datetime2ts(dt):
    return dt.strftime("%Y%m%d.%H%M")


@dataclass(frozen=True)
class FedoraMD:
    id: bytes = field(repr=False, compare=True)
    name: str
    path: Path
    ver: int
    arch: str
    repo: str
    time: datetime

    @classmethod
    def from_path(cls, p):
        # .../metadata/30/x86_64/release/20190425.1949/[SHA256]-primary.xml.gz
        (*rest, ver, arch, repo, ts, fn) = p.parts
        mdid, name = fn.split('-',1)
        return cls(id=unhexlify(mdid),
                   name=name,
                   path=p,
                   ver=int(ver),
                   arch=arch,
                   repo=repo,
                   time=ts2datetime(ts))

    def iter_pkgs(self, mdsize=False):
        yield from Primary(str(self.path)).iter_package_elem(mdsize=mdsize)

def iter_fedora_md(topdir):
    for p in Path(topdir).glob("**/*primary.xml.gz"):
        try:
            yield FedoraMD.from_path(p)
        except ValueError:
            continue

def read_size_data(topdir):
    pkgsizes = dict()  # {nevra:size}
    hdrsizes = dict()  # {nevra:hdrsize}
    instsizes = dict() # {nevra:instsize}
    mditems = dict()   # {nevra:mditems}
    repopkgs = dict()  # {repokey:{isotime:[nevra,nevra..]}}
    # TODO: progress()
    for md in iter_fedora_md(topdir):
        pkgs = set()
        repokey = f'f{md.ver}-{md.arch}-{md.repo}'
        isotime = md.time.isoformat()
        repopkgs.setdefault(repokey, {})
        print(f'reading {repokey} ({isotime}): ', end='', flush=True)
        for pkg in md.iter_pkgs():
            pkgsizes[pkg.nevra] = pkg.size
            hdrsizes[pkg.nevra] = pkg.hdrsize
            instsizes[pkg.nevra] = pkg.instsize
            mditems[pkg.nevra] = pkg.mditems
            pkgs.add(pkg.nevra)
        repopkgs[repokey][isotime] = pkgs
        print('{} packages'.format(len(pkgs)), flush=True)
    return pkgsizes, hdrsizes, instsizes, mditems, repopkgs

def dump_size_data(outfile, pkgsizes, hdrsizes, instsizes, mditems, repopkgs):
    import json, gzip
    # split dicts to three lists
    pkgkeys = sorted(pkgsizes.keys())
    sizelist = [pkgsizes[p] for p in pkgkeys]
    hdrlist = [hdrsizes[p] for p in pkgkeys]
    instlist = [instsizes[p] for p in pkgkeys]
    mdlist = [mditems[p] for p in pkgkeys]
    # build a key->idx lookup table
    pidx = {pkg:idx for idx,pkg in enumerate(pkgkeys)}
    # make indexed version of repopkgs
    repoidx = {repokey:{isotime:[pidx[p] for p in pkgs]
                        for isotime, pkgs in repotimes.items()}
               for repokey, repotimes in repopkgs.items()}
    with gzip.open(outfile, 'wt') as outf:
        # TODO: instlist
        json.dump({'pkgkeys': pkgkeys,
                   'sizes': sizelist,
                   'hdrsizes': hdrlist,
                   'instlist': instlist,
                   'mditems': mdlist,
                   'repoidx':repoidx}, outf)
        size = outf.tell()
    return size

def load_size_data(infile):
    import json, gzip
    with gzip.open(infile, 'rt') as inf:
        # load data from json object
        o = json.load(inf)
    # get our idx->key lookup table.. better known as.. a "list"
    pkgkeys = o.pop('pkgkeys')
    sizelist = o.pop('sizes')
    hdrlist = o.pop('hdrsizes')
    instlist = o.pop('instlist')
    mdlist = o.pop('mditems')
    # reconstruct pkgsizes/hdrsizes/mditems
    pkgsizes = dict(zip(pkgkeys,sizelist))
    hdrsizes = dict(zip(pkgkeys,hdrlist))
    instsizes = dict(zip(pkgkeys,instlist))
    mditems = dict(zip(pkgkeys,mdlist))
    # reconstruct repopkgs
    repopkgs = {repokey:{isotime:{pkgkeys[i] for i in pkgi}
                         for isotime, pkgi in repotimes.items()}
                for repokey, repotimes in o.pop('repoidx').items()}
    return pkgsizes, hdrsizes, instsizes, mditems, repopkgs

def mditems2size(i):
    # NOTE: these values came from running a linear regression on
    # mdsize vs. mditems for a few different metadata files; they're a
    # very good approximation (R^2 ~0.91, stderr ~0.194)
    # TODO: how good an approximation is this for large numbers? e.g.:
    # how close is sum(mditems2size(i) for i in mditems)
    # and how close is mditems2size(sum(mditems))?
    return 626+(i*63)

def calc_size_data(pkgsizes, hdrsizes, instsizes, mditems, samples):
    c_pkgs = set()
    c_md = 0
    c_repo = 0
    c_inst = 0
    for t in sorted(samples.keys()):
        pkgs = set(samples[t])
        # size of metadata, repository, and installed pkg payloads
        md = sum(mditems2size(mditems[p]) for p in pkgs)
        repo = sum(pkgsizes[p] for p in pkgs)
        inst = sum(instsizes[p] for p in pkgs)

        # TODO: might be more useful to have columns for (added, removed) and
        # calculate the cumulative data as-needed?
        newpkgs = pkgs.difference(c_pkgs)
        c_md += sum(mditems2size(mditems[p]) for p in newpkgs)
        c_inst += sum(instsizes[p] for p in newpkgs)
        c_repo += sum(pkgsizes[p] for p in newpkgs)
        c_pkgs.update(newpkgs) # should be the same result as .update(pkgs)
        yield (datetime.fromisoformat(t),
               len(pkgs),   repo,   md,   inst,
               len(c_pkgs), c_repo, c_md, c_inst,
               )

# TODO: use this
def calc_dedup_instsize(envrablobs, blobsizes, instsizes, samples):
    c_blobs = set()
    c_dedup_inst = 0
    for t in sorted(samples.keys()):
        pkgs = set(samples[t])
        blobs = set(b for p in pkgs for b in envrablobs.get(p,[]))
        newblobs = blobs.difference(c_blobs)
        dedup_inst = sum(blobsizes[b] for b in blobs)
        c_dedup_inst += sum(blobsizes[b] for b in newblobs)
        c_blobs.update(newblobs)
        yield (datetime.fromisoformat(t),
               len(blobs), dedup_inst,
               len(c_blobs), c_dedup_inst,
               )

RELEASEDATE = {
    'f26':datetime.fromisoformat('2017-04-30'),
    'f27':datetime.fromisoformat('2017-11-18'),
    'f28':datetime.fromisoformat('2018-05-01'),
    'f29':datetime.fromisoformat('2018-10-31'),
    'f30':datetime.fromisoformat('2019-04-30'),
}

def make_data_frames(pkgsizes, hdrsizes, instsizes, mditems, repopkgs):
    releases = dict()
    updates = dict()
    for repokey, reposamples in repopkgs.items():
        v, a, r = repokey.split('-')
        if r == 'updates':
            df = pd.DataFrame(list(calc_size_data(pkgsizes, hdrsizes, instsizes, mditems, reposamples)),
                              columns=('date',
                                       'packages', 'reposize', 'mdsize', 'instsize',
                                       'c_packages', 'c_reposize', 'c_mdsize', 'c_instsize'))
            df.set_index('date', inplace=True)
            if v in RELEASEDATE:
                df = df[RELEASEDATE[v]:]
                df['age'] = df.index - RELEASEDATE[v]
            updates[v] = df
        else:
            ts = sorted(reposamples.keys())[-1]
            pkgs = reposamples[ts]
            repo = sum(pkgsizes[p] for p in pkgs)
            md = sum(mditems2size(mditems[p]) for p in pkgs)
            inst = sum(instsizes[p] for p in pkgs)
            releases[v] = (datetime.fromisoformat(ts), len(pkgs), repo, md, inst)
    return updates, releases

def set_changes(set_iter):
    prev = set()
    for s in set_iter:
        cur = set(s)
        added, removed = cur.difference(prev), prev.difference(cur)
        yield added, removed
        prev = cur

def format_size(y, pos):
    from dnf.cli.format import format_number
    return format_number(y, SI=1)

def plot_updates_sizes(updates, inches=(11,8.5)):
    fig, ax = plt.subplots(2,2, sharey='row', sharex='col')
    for v,df in updates.items():
        if len(df) < 10: continue
        df.plot(ax=ax[0,0], x='age', y='mdsize', label=v)
        df.plot(ax=ax[0,1], x='age', y='c_mdsize', label=v)
        df.plot(ax=ax[1,0], x='age', y='reposize', label=v)
        df.plot(ax=ax[1,1], x='age', y='c_reposize', label=v)
    ax[0,0].set_title('Metadata Size')
    ax[0,1].set_title('Metadata Size (cumulative)')
    ax[1,0].set_title('Repository Size')
    ax[1,1].set_title('Repository Size (cumulative)')
    for a in ax.flat:
        a.yaxis.set_major_formatter(FuncFormatter(format_size))
        a.xaxis.set_label_text("Days since release")
        # TODO: this seems like a janky way to do this..
        a.xaxis.set_major_formatter(FuncFormatter(lambda y,p: str(int(y))))
    fig.set_size_inches(inches)
    plt.show()
    return fig, ax

# FIXME this is bunk
def plot_updates_sizes_dedup(updates, inches=(11,8.5)):
    fig, ax = plt.subplots(1,2, sharey='row')
    for v, df in updates.items():
        if 'dedup_inst' not in df: continue
        df.plot(ax=ax[0,0], x='age', y='c_instsize', label="size (all pkgs)")
        df.plot(ax=ax[0,0], x='age', y='instsize', label="size")
        df.plot(ax=ax[0,0], x='age', y='dedup_inst', label="size (dedup)")
        df.plot(ax=ax[0,0], x='age', y='c_dedup_inst', label="size (all pkgs + dedup)")
        ax[0,0].set_title(f"Total file sizes, {v}")
    for a in ax:
        a.yaxis.set_major_formatter(FuncFormatter(format_size))
    # TODO: better ticks on x axis
    fig.set_size_inches(inches)
    plt.show()
    return fig, ax



if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        print("usage: {sys.argv[0]} generate DATAFILE METADATA_DIR")
        print("   or: {sys.argv[0]} plot DATAFILE")
    elif sys.argv[1] == "generate":
        datafile, topdir = sys.argv[2:4]
        pkgsizes, hdrsizes, instsizes, mditems, repopkgs = read_size_data(topdir)
        print(f'writing {datafile}... ', end='', flush=True)
        size = dump_size_data(datafile, pkgsizes, hdrsizes, instsizes, mditems, repopkgs)
        csize = Path(datafile).stat().st_size
        print(f"ok, {size} bytes ({csize} compressed)")
    elif sys.argv[1] == "plot":
        datafile = sys.argv[2]
        pkgsizes, hdrsizes, instsizes, mditems, repopkgs = load_size_data(datafile)
        updates, releases = make_data_frames(pkgsizes, hdrsizes, instsizes, mditems, repopkgs)
        plot_updates_sizes(updates)

