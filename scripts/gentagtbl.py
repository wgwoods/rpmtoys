#!/usr/bin/python
# gentagtbl.py - generate RPM tagtbl, in various formats
# Copyright (C) 2020 Red Hat Inc.
#
# [gplv2+ boilerplate goes here]
#
# Author: Will Woods <wwoods@redhat.com>

# Forgive me if this code seems verbose or un-Pythonic; the point here
# is to demonstrate / document the tagtbl format so that this data can be
# used in languages other than C and Python and on platforms where you might
# not have the latest librpm available.

import re


# These are the typecodes used in the per-tag comments in rpmtag.h, and the
# corresponding rpmTagType and rpmTagReturnType.
RPMTYPECODE = {
    'c':   ("CHAR", "SCALAR"),       'c[]': ("CHAR", "ARRAY"),
    'h':   ("INT16", "SCALAR"),      'h[]': ("INT16", "ARRAY"),
    'i':   ("INT32", "SCALAR"),      'i[]': ("INT32", "ARRAY"),
    'l':   ("INT64", "SCALAR"),      'l[]': ("INT64", "ARRAY"),
    's':   ("STRING", "SCALAR"),
    's[]': ("STRING_ARRAY", "ARRAY"),
    's{}': ("I18NSTRING", "SCALAR"),
    'x':   ("BIN", "SCALAR"),
    None:  ("NULL", "ANY"),
}


# These are keywords that can appear in the RPMTAG comments after the typecode,
# and the corresponding "flag" they should apply to that tag.
#
# Here's how they're used as of rpm-4.16.0:
#
# * Tags marked 'internal' or 'unimplemented' are hidden/not present in the
#   tagtbl used by rpm/rpmtag.h:rpmTagGet* and the Python rpm module.
# * The 'extension' flag is present in librpm's headerTagTableEntry struct,
#   and marks whether this is an "Extension or 'real' tag", according to rpm.
# * The others are not used in the code; they're purely informational.
FLAGWORDS = {
    'internal', 'unimplemented', 'extension',
    'unused', 'deprecated', 'obsolete',
}

# Here we have single-letter codes for the flags. "unused" and "unimplemented"
# are intentionally folded into each other.
FLAGCODES = {
    'internal':      'i',
    'unimplemented': 'u',
    'extension':     'e',
    'unused':        'u',
    'deprecated':    'd',
    'obsolete':      'o',
}


# Known tag/define prefixes, with short abbreviations
GRP_NAME = {
    'HEADER':    'HDR',
    'RPMTAG':    'TAG',
    'RPMDBI':    'DBI',
    'RPMSIGTAG': 'SIG',
}


# Regexes for relevant C #defines and enum items in rpmtag.h, in verbose form:
#ENUMPAT = r'^         \s+ ([A-Z]+_\w+) \s+ = \s+ ([^,/]+)'
#DEFPAT  = r'^\#define \s+ ([A-Z]+_\w+) \s+       ([^,/]+)'

# But hey! Instead of trying to match each line twice, we can merge those to
# make a single regex that matches both #define and enum lines.
# NOTE: For re.MULTILINE matches to work right we have to make sure we match
# and consume the ',' at the end of enum expressions.
TAGPAT = r'^(\#define)? \s+ ([A-Z]+_\w+) \s+ (?:= \s+)? ([^,/]+?) ,?'

# Regex that matches optional C comment that ends at EOL
COMMENT = r'(?:\s*/\*\S*\s+(.*)\s+\S*\*/)?$'

# Compiled pattern for matching tags in rpmtag.h
RPMTAG_RE = re.compile(TAGPAT+COMMENT, re.MULTILINE|re.VERBOSE)

# The actual parsing function.
def iterparse_rpmtag_h(rpmtag_h):
    '''
    Iteratively parse rpmtag.h, matching #define or enum lines that define an
    RPM tag (or an alias), and yield parsed information about that tag.

    For each (name, expr, comment) we match, we:
    - split name to prefix + shortname
    - evaluate expr to an actual numeric value (val)
    - look for any RPMTYPECODE key at the start of the comment
    - look for other FLAGWORDS in the comment (as a set)

    and yield a tuple:
        (prefix, shortname, expr, val, typecode, flags, comment)

    val is an int.
    typecode is one of the keys in RPMTYPECODE (and may be None).
    flags is a set, and a subset of FLAGWORDS (and may be empty).
    '''
    # dict to hold symbols we've encountered while parsing
    syms = dict()

    # simple expression parser - just enough to get the job done
    def evalexpr(expr):
        if '+' in expr:
            l,r = expr.split('+',1)
            return evalexpr(l.strip()) + evalexpr(r.strip())
        elif expr in syms:
            return syms[expr]
        elif expr.startswith('0x'):
            return int(expr, 16)
        else:
            return int(expr)

    # Matches are ('#define|', name, expr, comment) tuples.
    for isdef, name, expr, comment in RPMTAG_RE.findall(rpmtag_h):
        # Evaluate expr to val, and save it to syms[name] for later lookup
        syms[name] = val = evalexpr(expr)
        # Split name into prefix and shortname
        prefix, shortname = name.split('_', 1)
        # If there's a typecode, it'll be the first word of the comment.
        # Split comment (which may be None) on whitespace and check it.
        words = [] if not comment else comment.strip().split()
        typecode = words[0] if words and words[0] in RPMTYPECODE else None
        # Re-split comment, stripping all non-word chars, to find flagwords.
        flags = FLAGWORDS.intersection(re.split(r'\W+', comment))

        yield name, expr, val, typecode, flags, bool(isdef), comment


def dump_tagtbl_txt_compact(rpmtag_h):
    '''Parse rpmtag.h and generate a simple/compact tagtbl.txt format.'''
    tagnames = {grp:{} for grp in GRP_NAME.values()}
    for name, expr, val, typecode, flags, isdef, _ in iterparse_rpmtag_h(rpmtag_h):
        pre, sn = name.split('_', 1)
        typecode = typecode or "-"
        charflags = ''.join(sorted(set(FLAGCODES[f] for f in flags))) or "-"
        grp = GRP_NAME.get(pre)
        if not grp:
            continue
        print(f'{grp:3}  {val:<7}  {sn:30}  {typecode:3}  {charflags:3}')


def dump_tagtbl_txt(rpmtag_h):
    '''
    Parse rpmtag.h and generate a tagtbl.txt with special handling for
    aliased names.
    '''
    taginfo = {grp:{} for grp in GRP_NAME.values()}
    for name, expr, val, typecode, flags, isdef, _ in iterparse_rpmtag_h(rpmtag_h):
        pre, sn = name.split('_', 1)
        typecode = typecode or "-"
        grp = GRP_NAME.get(pre)
        if not grp:
            continue
        if val not in taginfo[grp]:
            taginfo[grp][val] = [sn, typecode, flags]
        else:
            taginfo[grp][val].append(sn)

    for grp, grpinfo in taginfo.items():
        for val, (sn, typecode, flags, *aliases) in grpinfo.items():
            if aliases:
                flags.add(f'alias={",".join(aliases)}')
            outstr = f'{grp:3}  {val:<7}  {sn:30}  {typecode:3}  {" ".join(sorted(flags)) or "-"}'
            print(outstr)


def dump_tagtbl_C(rpmtag_h):
    '''
    Parse rpmtag.h and generate tagtbl.C, just like good ol' gentagtbl.sh,
    except not written in awk. Output should be identical to:

        AWK=awk LC_ALL=C gentagtbl.sh rpmtag.h
    '''
    items = []
    for name, expr, val, typecode, flags, isdef, _ in iterparse_rpmtag_h(rpmtag_h):
        # Only match names starting with RPMTAG_ and _no_ other underscores.
        pre, sn = name.split('_', 1)
        if pre != 'RPMTAG' or '_' in sn:
            continue
        # Skip internal / unimplemented tags
        if 'internal' in flags or 'unimplemented' in flags:
            continue
        # Get typecode and extension flag (tt, ta, ext in gentagtbl.sh)
        tt, ta = RPMTYPECODE[typecode]
        ext = 1 if 'extension' in flags else 0
        sym = expr if isdef else name
        items.append(f'    {{ "{name}", "{sn.capitalize()}", {sym}, RPM_{tt}_TYPE, RPM_{ta}_RETURN_TYPE, {ext} }},')

    print('static const struct headerTagTableEntry_s rpmTagTable[] = {')
    for i in sorted(items):
        print(i)
    print('    { NULL, NULL, RPMTAG_NOT_FOUND, RPM_NULL_TYPE, 0 }')
    print('};')

if __name__ == '__main__':
    # TODO: argparse...
    import sys

    if len(sys.argv) > 1:
        rpmtag_h = open(sys.argv[1]).read()
        dump_tagtbl_txt(rpmtag_h)
        #dump_tagtbl_C(rpmtag_h)
