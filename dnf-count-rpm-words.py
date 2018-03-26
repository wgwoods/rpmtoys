#!/usr/bin/python3

import dnf
from collections import Counter

# things that we should consider a single "word"
nosplit_words = [
    "unit-test", "apache-commons", "openrdf-sesame", "coin-or",
    "device-mapper", "libjpeg-turbo", "getting-started", "man-pages",
    "linux-gnu", "gnome-shell", "util-linux",
    "asterisk-sounds-core", "google-noto", "spherical-cow", "beefy-miracle",
    "schroedinger-cat",
]


def rpmwordsplit(rpmname):
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
            return [w] + rpmwordsplit(rest)
    # otherwise just split on dashes
    w, rest = rpmname.split('-', 1)
    return [w] + rpmwordsplit(rest)


known_prefixes = {
    "programming language": [
        "perl", "python", "python2", "python3", "js", "nodejs", "ruby",
        "rubygem", "php", "php-pear", "php-pecl", "golang", "ocaml", "R",
        "erlang", "rust", "java", "lua", "tcl", "ghc", "ocaml", "mono",
        "gambas3", "octave", "gap",
    ],
    "vendor": [
        "google", "fedora",
    ],
    "project name": [
        "texlive", "eclipse", "glibc", "libreoffice", "drupal7", "pcp", "vim",
        "globus", "root", "coin-or", "asterisk", "uwsgi", "gimp", "gcc",
        "qemu", "boost", "tesseract", "gallery2", "nagios", "aws", "maven",
        "jboss", "apache-commons", "glassfish", "jetty", "collectd", "kde",
        "kf5", "qt5", "qt", "plasma", "gnome", "gnome-shell", "sugar", "mate",
        "lxqt", "xfce4", "hunspell", "aspell", "autocorr", "fawkes",
        "openrdf-sesame", "google-noto", "xorg", "x11", "fence", "jenkins",
        "emacs", "ibus", "derelict", "django", "qpid", "libvirt", "lodash",
        "matreshka", "plexus", "shrinkwrap", "soletta", "springframework",
        "trytond", "oslo", "pulp", "geany", "NetworkManager", "yum", "felix",
        "fusionforge", "opensips", "jackson", "vdsm", "horde", "sblim",
        "gcompris", "glite", "arquillian", "geronimo", "binutils",
    ],
    "build-variant": [
        "mingw32", "mingw64", "compat",
    ],
    "translations": [
        "langpacks",
    ],
}

known_suffixes = {
    "file type": [
        "devel", "libs", "lib", "doc", "docs", "javadoc", "bin", "fonts",
        "data", "config", "firmware", "info", "backgrounds", "macros",
        "filesystem", "manual", "selinux", "bundle", "el", "help",
    ],
    "build-variant": [
        "static", "linux-gnu", "debug", "compat",
    ],
    "common module names": [
        "Simple", "Parser", "Tiny", "XS", "manager", "log", "console", "web",
        "demo", "driver", "api", "parent", "agent", "runtime", "stream",
        "parser", "cache",
    ],
    "executable purpose": [
        "tests", "test", "unit-test", "client", "server", "tools", "utils",
        "examples", "cli", "gui", "daemon", "util",
    ],
    "extends/enhances": [
        "plugin", "plugins", "theme", "extensions", "module", "modules",
        "bridge", "addon", "addons",
    ],
    "programming language": [
        "java", "perl", "python", "python3", "ruby", "tcl", "c", "sharp", "c++"
    ],
    "built-with/support-for": [
        "qt", "qt4", "qt5", "gtk", "gtk2", "gtk3",
        "mysql", "gnome", "sqlite", "kde", "mate", "glib", "postgresql",
        "xfce", "ldap", "xml", "json", "pgsql",
        "openmpi", "mpich",
    ],
    "core/extras": [
        "core", "common", "base", "extra", "extras", "contrib",
    ],
    "translations": [
        "fr", "ru", "it", "es", "de", "en", "ja", "pl", "cs", "gb",
        "l10n", "i18n",
    ],
}

known_midwords = {
    "file type": [
        "sounds", "backgrounds",
    ],
    "common concept": [
        "system", "manager", "sdk", "file", "http", "json", "daemon", "util",
        "xml", "agent", "test", "unit-test", "driver",
    ],
    "extends/enhances": [
        "plugin", "plugins",
    ],
    "core/extras": [
        "core", "common", "base", "extra", "extras", "contrib",
    ],
    "build-variant": [
        "compat", "linux-gnu", "mingw32", "mingw64",
    ],
    "built-with/support-for": [
        "qt", "qt5", "gtk", "gtk2", "gtk3", "mpich", "openmpi", "x11",
        "pgsql", "postgresql", "mysql", "glib",
    ],
    "programming language": [
        "c", "java", "c++",
    ],
    "common module names": [
        "github", "go",
        "Test", "Plugin", "Net", "horde", "Horde", "Class",
        "lodash",
        "django", "oslo",
        "pst", "bin", "hyphen", "babel", "datetime2",
        "sans", "serif",
    ],
    "translations": [
        "langpack", "i18n", "l10n",
    ],
}

all_suffixes = {w:n for n,s in known_suffixes.items() for w in s}
all_midwords = {w:n for n,s in known_midwords.items() for w in s}
all_prefixes = {w:n for n,s in known_prefixes.items() for w in s}


b = dnf.Base()
b.read_all_repos()
b.repos.all().disable()
b.repos['fedora'].enable()
b.repos['updates'].enable()
sack = b.fill_sack(load_system_repo=False)

names = {pkg.name:pkg.source_name for pkg in sack.query()}
words = Counter(w for n in names for w in rpmwordsplit(n))
prefixes = Counter(nw[0] for nw in (rpmwordsplit(n) for n in names)
                   if len(nw) > 1)
suffixes = Counter(nw[-1] for nw in (rpmwordsplit(n) for n in names)
                   if len(nw) > 1)
commonwords = Counter({w:words[w] for cat in (words, prefixes, suffixes)
                                  for w,c in cat.most_common(100)})


# TODO: consider only suffixes that come from actual subpackages
subpkg_suffixes = Counter(w for n,sn in names.items()
                            for w in rpmwordsplit(n[len(sn)+1:])
                            if n.startswith(sn+'-'))


# bonus stuff for finding words like "coin-or"
def iterpairs(iterable):
    i = iter(iterable)
    left = next(i)
    for right in i:
        yield left, right
        left = right
pairs = Counter(p for n in names for p in iterpairs(n.split('-')))


# Pick a primary "meaning" for a given word
def guess_meaning(word):
    count = words.get(word, 0)
    prefix = prefixes.get(word, 0)
    suffix = suffixes.get(word, 0)
    if prefix * 2 >= count:
        meaning = all_prefixes.get(word, 'project-name?')
    elif suffix * 2 >= count:
        meaning = all_suffixes.get(word, 'subpackage?')
    else:
        meaning = all_midwords.get(word, '?')
    return meaning


# dump CSV data for the given words
def dump_csv(fobj, wordlist):
    hdr="word,count,prefix,suffix,meaning"
    fobj.write(hdr+"\n")
    for word in wordlist:
        count = words.get(word, 0)
        prefix = prefixes.get(word, 0)
        suffix = suffixes.get(word, 0)
        meaning = guess_meaning(word)
        line = ",".join([word, str(count), str(prefix), str(suffix), meaning])
        fobj.write(line+'\n')

# for fun experimentation, run with "ipython3 -i dnf-count-rpm-words.py"
if __name__ == '__main__':
    with open("rpm-name-words-common.csv", 'wt') as fobj:
        print("writing {}...".format(fobj.name))
        dump_csv(fobj, (w for w,c in commonwords.most_common()))
    with open("rpm-name-words-all.csv", 'wt') as fobj:
        print("writing {}...".format(fobj.name))
        dump_csv(fobj, (w for w,c in words.most_common()))
