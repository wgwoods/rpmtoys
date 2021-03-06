#!/usr/bin/python3

import json
import gzip

from os.path import basename
from collections import defaultdict, OrderedDict

from rpmtoys import rpm, Tag, DepFlags, deptup
from rpmtoys import iter_repo_rpms
from rpmtoys.progress import progress, Progress


def dump_deps(repo_paths, outfile="depdata.json.gz"):
    deps = dict()
    rpmcount = 0
    depcount = 0
    for rpmfn in progress(iter_repo_rpms(repo_paths), itemfmt=basename):
        r = rpm(rpmfn)
        # Skip duplicate ENVRAs
        if r.envra in deps:
            continue
        deps[r.envra] = r.alldeps()
        rpmcount += 1
        depcount += len(deps[r.envra])
    print("dumping {}...".format(outfile))
    with gzip.open(outfile, 'wt') as outf:
        o = OrderedDict()
        o['type'] = 'deps'
        o['version'] = 1
        o['counts'] = {'rpms': rpmcount, 'deps': depcount}
        o['deps'] = [{'envra':t, 'deps':d} for t,d in deps.items()]
        json.dump(o, outf)
    return deps

class RPMDepLoader(object):
    '''An object for doing progress reporting while loading depdata'''
    def __init__(self, total, prefix=''):
        self.prog = Progress(total=total, prefix=prefix)

    def hook(self, o):
        keys = set(o.keys())
        if keys == {'envra', 'deps'}:
            envra = o['envra']
            self.prog.item(envra)
            deps = {dt:[deptup(n,DepFlags(f),v,i) for n,f,v,i in di]
                    for dt,di in o['deps'].items()}
            o = (envra, deps)
        elif keys == {'type', 'version', 'counts', 'deps'}:
            self.prog.end()
        return o

def load_deps(datafile):
    data = None
    print("loading {}...".format(datafile))
    with gzip.open(datafile, mode='rt') as inf:
        # Read the first chunk of the file and find the counts
        head = inf.read(4096)
        counts = json.loads(head[head.find('{',1):head.find('}',1)+1])
        # Back to the beginning so we can read the whole deal
        inf.seek(0)
        # set up progress / object conversion and read the datafile
        rc = RPMDepLoader(counts['rpms'], prefix='  ')
        data = json.load(inf, object_hook=rc.hook)

    deps = dict(data['deps'])
    return deps

# TODO: some of these are more namespace-y than others; probably need to
# subdivide this
namespaces = {
    'rpmlib', 'config',
    'pkgconfig', 'cmake', 'mimehandler',
    'mingw32', 'mingw64',
    'perl', 'ocaml', 'mvn', 'mono', 'tex', 'ghc-devel', 'osgi',
    'npm', 'nodejs',
    'golang', 'golang-ipath',
    'rubygem', 'ruby',
    'php-composer', 'php-pear', 'php-autoloader', 'php-pecl', 'php-channel',
    'python', 'python3.7dist', 'python2.7dist', 'python3dist', 'python2dist',
    'font', 'kmod', 'dnf-command', 'drupal7',
}

api = {
    'python', 'octave', 'vala', 'kde4-macros', 'php',
}

abi = {
    'python', 'pypy2', 'gawk', 'lua', 'tcl', 'blender', 'nodejs',
}

# TODO: deal with bundled()

# Gathered from F30 x86_64
autoprov_namespaces = {
    'appdata', 'application', 'cmake', 'debuginfo', 'drupal7',
    'font', 'ghc-devel',
    'golang', 'golang-ipath',
    'gstreamer0.10', 'gstreamer1', 'kmod', 'libtool',
    'metainfo', 'mimehandler',
    'mingw32', 'mingw64', 'mono', 'mvn', 'npm', 'ocaml', 'osgi', 'perl',
    'pkgconfig',
    'plasma4', 'postscriptdriver',
    'python2.6dist', 'python2.7dist', 'python2dist',
    'python3.7dist', 'python3dist',
    'rubygem',
}

autoprov_abi = {
    'debuginfo(build-id)',
}

# TODO: some of these probably need further investigation
# (rtld, python, erlang..)
autoreq_namespaces = {
    'ghc-devel', 'golang', 'golang-ipath',
    'mingw32', 'mingw64', 'mono', 'mvn', 'npm',
    'ocaml', 'osgi', 'perl', 'pkgconfig',
    'python2.7dist', 'python3.7dist',
    'rubygem',
}

autoreq_abi = {
    'ruby(rubygems)', 'drupal7(core)', 'python(abi)',
    'nodejs(abi10)', 'nodejs(abi8)', 'nodejs(engine)', 'nodejs(v8-abi6)',
    'plasma4(scriptengine-declarativeappletscript)',
    'erlang(erl_drv_version)', 'erlang(erl_nif_version)',
    'rtld(GNU_HASH)',
}


# HEIRARCHY OF REQ/PROV
#
# * Provides
#   * Auto
#     * ELF: contains '.so'; SONAME(SYMBOL?)(BITS)
#     * Namespaced: NS(NS-STUFF) (NS is in autoprov_namespaces)
#       * bundled(PROV): can wrap other autoprovs
# * Requires:
#   * Auto
#     * ELF: as above, with bonuses
#       * rtld(GNU_HASH)
#     * Arch/ABI stuff?
#       * ends with (x86-64) or (x86-32)
#       * ends with (abi) or (api) or (ABI) or (API)
#       * nodejs(abi10), nodejs(abi8), nodejs(engine), nodejs(v8-abi6)
#       * python(abi)
#       * ruby(rubygems)
#       * drupal7(core)
#       * plasma4(scriptengine-declarativeappletscript)
#       * erlang(erl_drv_version), erlang(erl_nif_version)
#     * Namespaced: as above, but..
#       * No bundled() [that wouldn't even make sense!]
#       * erlang-XXX() - what?
#
# Misc. notes:
# * There are no auto-provides for file paths
# * There *are* auto-generated Conflicts, Suggests, etc.
#   * rubygem-em-http-request-1.1.5-6.fc30.noarch: Conflicts
#   * nodejs-st-1.2.0-1.fc28.noarch: Suggests
# * Provides can be 'auto', 'manual', or 'config'



if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("TODO USAGE")
    elif sys.argv[1] == "interactive":
        depdata = {f:load_deps(f) for f in sys.argv[2:]}
        print("Data loaded:")
        for f in depdata:
            print(f"  deps = depdata[{f!r}]")
        if len(depdata) == 1:
            deps = next(iter(depdata.values()))
        def iterprov():
            for repo in depdata.values():
                for pkg in repo.values():
                    for d in pkg.get("Provides",[]):
                        yield d
        def iterdeps():
            for repo in depdata.values():
                for pkg in repo.values():
                    for dt, ds in pkg.items():
                        if dt != "Provides":
                            for d in ds:
                                yield d
        print("Convenience functions:")
        print("  iterprov() - generates all Provides items in depdata")
        print("  iterdeps() - generates all non-Provides items in depdata")


    elif sys.argv[1] == "generate":
        deps = dump_deps(sys.argv[3:], sys.argv[2])
