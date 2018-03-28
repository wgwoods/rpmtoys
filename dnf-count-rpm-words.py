#!/usr/bin/python3

import dnf
import json
from collections import Counter, defaultdict


# A dictionary of known "words" from RPM names.
#
# Partly this is useful to generate nosplit_words, so "gnome-shell" doesn't get
# broken into "gnome" and "shell".
# It also gets used to guess the "meaning" of each part of the name.
#
# NOTE: These should be listed from least to most specific categories, so when
# we make the all_words reverse-lookup dict the result for, say, "gtk" is
# "framework" instead of just "project name".
known_words = {
    "project name": [
        "texlive", "eclipse", "glibc", "libreoffice", "drupal7", "pcp", "vim",
        "globus", "root", "coin-or", "asterisk", "uwsgi", "gimp", "gcc",
        "qemu", "boost", "tesseract", "gallery2", "nagios", "maven",
        "jboss", "apache-commons", "glassfish", "jetty", "collectd", "kde",
        "kf5", "qt5", "qt", "plasma", "gnome", "gnome-shell", "sugar", "mate",
        "lxqt", "xfce4", "hunspell", "aspell", "autocorr", "fawkes",
        "openrdf-sesame", "google-noto", "fence", "jenkins",
        "emacs", "ibus", "derelict", "django", "qpid", "libvirt", "lodash",
        "matreshka", "plexus", "shrinkwrap", "soletta", "springframework",
        "trytond", "oslo", "pulp", "geany", "NetworkManager", "yum", "felix",
        "fusionforge", "opensips", "jackson", "vdsm", "horde", "sblim",
        "gcompris", "glite", "arquillian", "geronimo", "binutils",
        "asterisk-sounds-core", "xorg-x11", "xorg", "man-pages",
        "libjpeg-turbo", "util-linux", "xkb-utils", "gnome-getting-started",
        "subscription-manager", "virt-manager", "gtk", "gtk2", "gtk3",
        "aws-sdk",
    ],
    # FUTURE: could get clever and use this to merge variant words?
    "variants": {
        "python": ["python2", "python3"],
        "mingw": ["mingw32", "mingw64"],
        "gtk": ["gtk2", "gtk3"],
        "qt": ["qt4", "qt5"],
    },
    "programming language": [
        "perl", "python", "python2", "python3", "js", "ruby",
        "rubygem", "php", "go", "ocaml", "R", "erlang", "rust", "java", "lua",
        "tcl", "ghc", "ocaml", "mono", "gambas3", "octave", "gap", "c++",
        "cpp", "c", "sharp",
    ],
    # FUTURE: could get clever and ignore "words" after a packaging prefix
    # (until we hit a known suffix...)
    "package prefix": [
        "perl", "php-pear", "php-pecl", "gap-pkg", "rubygem", "golang",
        "nodejs", "ghc", "XStatic",
    ],
    "vendor": [
        "google", "fedora", "redhat", "hashicorp",
    ],
    "framework": [
        "gtk", "gtk2", "gtk3", "glib", "dbus",
        "qt", "qt4", "qt5", "kf5", "plasma",
        "ibus", "boost", "lodash", "grunt", "django",
        "openmpi", "mpich",
        "sqlite", "mysql", "pgsql", "postgresql",
        "selinux", "device-mapper", "git", "docker",
        "syntastic", "zendframework", "zend", "gl", "flask",
        "maven", "trac", "nautilus", "lv2",
    ],
    "protocol": [
        "http", "ldap", "x11", "ssh",
    ],
    "data format": [
        "json", "yaml", "xml", "el", "latex", "html", "HTML", "XML", "text",
    ],
    "environment": [
        "gnome", "kde", "mate", "lxde", "lxqt", "xfce", "xfce4", "sugar",
    ],
    "build-variant": [
        "mingw32", "mingw64", "python2", "python3",
        "compat", "static", "debug", "linux-gnu",
    ],
    "file-type": [
        "devel", "doc", "docs", "javadoc", "fonts", "libs", "bin", "data",
        "info", "parent", "theme", "lib", "config", "filesystem", "firmware",
        "macros", "backgrounds", "bundle", "icon", "rpm-macros", "srpm-macros",
        "source", "mythes",
    ],
    "font-type": [
        "sans", "serif",
    ],
    "file-purpose": [
        "tests", "test", "unit-test", "unit-tests", "client", "server",
        "tools", "examples", "cli", "gui", "daemon", "util", "utils",
        "daemon", "manual", "api", "demo", "web", "console", "log",
        "agent", "manager", "parser", "runtime", "cache", "bridge",
        "session-manager", "power-manager", "font-manager", "help",
        "agents", "proxy", "desktop", "sounds",
    ],
    # FUTURE: could get clever and use the (singular, plural) pairings
    "extends/enhances": [
        "plugin", "plugins",
        "plug-in", "plug-ins",
        "extension", "extensions",
        "provider", "providers",
        "module", "modules",
        "driver", "drivers",
        "addon", "addons",
    ],
    "core/extras": [
        "core", "common", "base", "extra", "extras", "others", "contrib",
    ],
    "release name": [
        "spherical-cow", "beefy-miracle", "schroedinger-cat",
    ],
    "concept": [
        "file", "system", "stream", "net", "map", "path", "app",
    ],
    "translation": [
        "langpack", "langpacks", "i18n", "l10n",
        "fr", "ru", "it", "es", "de", "en", "ja", "pl", "cs", "gb",
        "utf-8", "KOI8-R",
    ],
}


all_words = {w:desc for desc,words in known_words.items() for w in words}
nosplit_words = set(w for w in all_words if '-' in w)

def wordsplit(rpmname):
    # empty string
    if not rpmname:
        return []
    # nothing to split
    if '-' not in rpmname or rpmname in nosplit_words:
        return [rpmname]
    # check for nosplit_words
    for w in nosplit_words:
        p = w+'-'
        if rpmname.startswith(p):
            rest = rpmname[len(p):]
            return [w] + wordsplit(rest)
    # otherwise just split on dashes
    w, rest = rpmname.split('-', 1)
    return [w] + wordsplit(rest)

# --- Okay, ready to start doing stuff? Here we go!

print("fetching DNF metadata..")
b = dnf.Base()
b.read_all_repos()
b.repos.all().disable()
b.repos['fedora'].enable()
b.repos['updates'].enable()
sack = b.fill_sack(load_system_repo=False)


print("analyzing package names..")
names = dict()
subpkgs = defaultdict(list)
namewords = list()
wordnames = defaultdict(set)
for pkg in sack.query():
    name = pkg.name
    src = pkg.source_name
    words = wordsplit(name)
    # name -> src
    names[name] = src
    # src -> [name, name, ...]
    subpkgs[src].append(name)
    # [[word, word, ...], ...]
    namewords.append(words)
    # word -> [name, name, ...]
    for w in words:
        wordnames[w].add(name)

# Count raw number of uses for every word in every package name
words = Counter(w for nw in namewords for w in nw)
prefixes = Counter(nw[0] for nw in namewords if len(nw) > 1)
suffixes = Counter(nw[-1] for nw in namewords if len(nw) > 1)

# How many different source packages - i.e. spec files - use each word?
# (this reduces noise from things like texlive...)
srcwords = Counter({w:len(set(names[n] for n in wordnames[w])) for w in words})
prefixes = Counter({w:len(set(names[n] for n in wordnames[w] if n.startswith(w+'-'))) for w in words})
suffixes = Counter({w:len(set(names[n] for n in wordnames[w] if n.endswith('-'+w))) for w in words})

commonwords = Counter({w:srcwords[w] for cat in (srcwords, prefixes, suffixes)
                                     for w,c in cat.most_common(100)})

# bonus stuff for finding words like "coin-or"
def iterpairs(iterable):
    i = iter(iterable)
    left = next(i)
    for right in i:
        yield left, right
        left = right
pairs = Counter(p for nw in namewords for p in iterpairs(nw))

# run with "ipython3 -i dnf-count-rpm-words.py" to do interactive exploration!
if __name__ == '__main__':
    with open("rpm-name-word-counts.csv", 'wt') as fobj:
        print("writing {}...".format(fobj.name))
        fobj.write("word,pkgs,prefix,suffix,meaning\n")
        for word, count in srcwords.most_common():
            fobj.write("{},{},{},{},{}\n".format(word, count,
                                                 prefixes.get(word, 0),
                                                 suffixes.get(word, 0),
                                                 all_words.get(word, '')))
    with open("rpm-name-word-counts-common.csv", 'wt') as fobj:
        print("writing {}...".format(fobj.name))
        fobj.write("word,pkgs,prefix,suffix,meaning\n")
        for word,count in commonwords.most_common():
            fobj.write("{},{},{},{},{}\n".format(word, count,
                                                 prefixes.get(word, 0),
                                                 suffixes.get(word, 0),
                                                 all_words.get(word, '')))
