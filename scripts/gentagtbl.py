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
import json
import argparse
from collections import namedtuple

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
    'unused', 'deprecated', 'obsolete', 'hidden',
}

# Here we have single-letter codes for the flags.
# "unused" and "unimplemented" are intentionally folded into each other,
# as are "obsolete" and "deprecated".
FLAGCODES = {
    'internal':      'i',
    'unimplemented': 'u',
    'extension':     'e',
    'unused':        'u',
    'deprecated':    'd',
    'obsolete':      'd',
    'hidden':        'h',
}

CODE2FLAG = {
    'i': 'internal',
    'u': 'unimplemented',
    'e': 'extension',
    'd': 'deprecated',
    'h': 'hidden',
}

# Known tag/define prefixes, with short abbreviations
GRP_NAME = {
    'HEADER':    'HDR',
    'RPMTAG':    'TAG',
    'RPMDBI':    'DBI',
    'RPMSIGTAG': 'SIG',
}


# Regexes for relevant C #defines and enum items in rpmtag.h, in verbose form:
ENUMPAT = r'^         \s+ ([A-Z]+_\w+) \s+ = \s+ ([^,/]+) ,?'
DEFPAT  = r'^\#define \s+ ([A-Z]+_\w+) \s+       ([^,/]+)'

# But hey! Instead of trying to match each line twice, we can merge those to
# make a single regex that matches both #define and enum lines.
# NOTE: For re.MULTILINE matches to work right we have to make sure we match
# and consume the ',' at the end of enum expressions.
TAGPAT = r'^(\#define)? \s+ ([A-Z]+_\w+) \s+ (?:= \s+)? ([^,/]+?) ,?'

# Regex that matches optional C comment that ends at EOL
COMMENT = r'(?:\s*/\*\S*\s+(.*)\s+\S*\*/)?$'

# Compiled patterns for matching tags in rpmtag.h
RPMTAG_RE = re.compile(TAGPAT+COMMENT, re.MULTILINE|re.VERBOSE)
ENUM_RE = re.compile(ENUMPAT+COMMENT, re.VERBOSE)
DEF_RE = re.compile(DEFPAT+COMMENT, re.VERBOSE)

class TagLineMatch(namedtuple("TagLineMatch", "isdef name expr comment")):
    @property
    def sym(self):
        return self.expr if self.isdef else self.name

class TagTableItem(namedtuple("TagTableItem", "prefix shortname id typecode flags")):
    @property
    def grp(self):
        return GRP_NAME.get(self.prefix)

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

    and yield a (item, match) pair, where each is a namedtuple:
        match = TagLineMatch(isdef, name, expr, comment)
        item = TagTableItem(prefix, shortname, id, typecode, flags)

    isdef is a bool.
    id is an int.
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

        match = TagLineMatch(bool(isdef), name, expr, comment)
        item = TagTableItem(prefix, shortname, val, typecode, flags)

        yield item, match

# Find & filter out aliases in the parsed output.
def generate_tagtbl_items(rpmtag_h):
    '''
    Parse rpmtag.h, keeping tag alias names as separate items.
    Yields pairs: (tag: TagTableItem, aliases: List[str])
    '''
    buf, aliases = None, []

    for item, _ in iterparse_rpmtag_h(rpmtag_h):
        if not item.grp:
            continue
        # If we see the same group/val as before, it's an alias
        if buf and (item.grp, item.id) == (buf.grp, buf.id):
            aliases.append(item.shortname)
            continue
        if buf:
            yield buf, aliases
        buf, aliases = item, []

    if buf:
        yield buf, aliases


def dump_tagtbl_json(rpmtag_h, indent=2):
    '''
    Parse rpmtag.h and generate tagtbl.json, a more verbose, more portable
    format than tagtbl.C or tagtbl.txt. Example output:
    {
      "TAG": [
        {
          "shortname": "NAME",
          "id": 1000,
          "typecode": "s",
          "flags": [],
          "aliases": ["N"]
        }
      ]
    }

    Note that `typecode` may be null.
    '''
    taginfo = {}
    for tag, aliases in generate_tagtbl_items(rpmtag_h):
        # replace flags with a list (sets aren't serializable) and make a dict
        d = tag._replace(flags=list(tag.flags))._asdict()
        d["aliases"] = aliases
        d.pop("prefix")
        taginfo.setdefault(tag.grp, []).append(d)
    print(json.dumps(taginfo, indent=indent))


def dump_tagtbl_txt(rpmtag_h, normalize_flags=True):
    '''
    Parse rpmtag.h and generate tagtbl.txt, a simple text-based format.
    Example output:

        TAG  1000     NAME                            s    alias=N
        TAG  1032     FILEGIDS                        i[]  deprecated internal
        TAG  1033     FILERDEVS                       h[]  -
        TAG  1054     CONFLICTNAME                    s[]  alias=CONFLICTS,C

    Each line will have 5 or more items: (group, id, name, typecode, *extra)

    Items in `extra` can be one of the FLAGWORDS, or "alias=" (followed by a
    comma-separated list of aliases for this tag).

    '-' will be used as a placeholder when `typecode` or `flags` is empty.
    '''
    for tag, aliases in generate_tagtbl_items(rpmtag_h):
        flags = tag.flags
        if normalize_flags:
            flags = set(CODE2FLAG[FLAGCODES[f]] for f in tag.flags)
        if aliases:
            flags.add(f'alias={",".join(aliases)}')
        outstr = f'{tag.grp:3}  {tag.id:<7}  {tag.shortname:30}  {tag.typecode or "-":3}  {" ".join(sorted(flags)) or "-"}'
        print(outstr)


def dump_tagtbl_C(rpmtag_h):
    '''
    Parse rpmtag.h and generate tagtbl.C, just like good ol' gentagtbl.sh,
    except not written in awk. Output should be identical to:

        AWK=awk LC_ALL=C gentagtbl.sh rpmtag.h
    '''
    items = []
    for item, match in iterparse_rpmtag_h(rpmtag_h):
        # Only match names starting with RPMTAG_ and _no_ other underscores.
        if item.prefix != 'RPMTAG' or '_' in item.shortname:
            continue
        # Skip internal / unimplemented tags
        if 'internal' in item.flags or 'unimplemented' in item.flags:
            continue
        # Get typecode and extension flag (tt, ta, ext in gentagtbl.sh)
        tt, ta = RPMTYPECODE[item.typecode]
        ext = 1 if 'extension' in item.flags else 0
        items.append(f'    {{ "{match.name}", "{item.shortname.capitalize()}", {match.sym}, RPM_{tt}_TYPE, RPM_{ta}_RETURN_TYPE, {ext} }},')

    print('static const struct headerTagTableEntry_s rpmTagTable[] = {')
    for i in sorted(items):
        print(i)
    print('    { NULL, NULL, RPMTAG_NOT_FOUND, RPM_NULL_TYPE, 0 }')
    print('};')


if __name__ == '__main__':
    p = argparse.ArgumentParser(
            description="Parse rpmtag.h and generate tables of tag info.")
    p.add_argument("rpmtag_h",
            type=argparse.FileType('r', encoding='utf8'),
            help="path to rpmtag.h (or '-' for stdin)")
    p.add_argument("-o", "--output",
            choices=("C", "text", "json"), default="json",
            help="output format")
    args = p.parse_args()

    rpmtagdata = args.rpmtag_h.read()

    if args.output == "json":
        dump_tagtbl_json(rpmtagdata)
    elif args.output == "C":
        dump_tagtbl_C(rpmtagdata)
    elif args.output == "text":
        dump_tagtbl_txt(rpmtagdata)
