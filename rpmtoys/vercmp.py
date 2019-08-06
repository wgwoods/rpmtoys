# rpmtoys.vercmp - RPM version comparison helper functions
#
# These functions should give the same results as RPM's version comparison
# functions (e.g. rpm.labelCompare() / rpmvercmp() / rpmVersionCompare())
#
# For details, see:
# https://github.com/rpm-software-management/rpm/blob/master/lib/rpmvercmp.c

from ctypes import c_uint32
from string import ascii_letters, digits
from functools import cmp_to_key

def _get_epoch(v):
    try:
        return c_uint32(v).value
    except TypeError:
        return 0

_alnum = ascii_letters + digits
_verch = _alnum + '~' + '^'

def risdigit(ch):
    return ch in digits

def risalpha(ch):
    return ch in ascii_letters

def risalnum(ch):
    return ch in _alnum

def risverch(ch):
    return ch in _verch

def take_while(s, match):
    i = 0
    end = len(s)
    while i < end and match(s[i]):
        i+=1
    return s[:i], s[i:]

def take_until(s, match):
    return take_while(s, lambda ch: not match(ch))

def rpmvercmp(a, b):
    '''
    Compare two version strings, returning (-1, 0, 1) for (a<b, a==b, a>b),
    as per rpm/lib/rpmvercmp.c:rpmvercmp().
    '''
    # "easy comparison to see if versions are identical"
    if a == b:
        return 0

    # This is kinda dumb but I'm trying to make it obvious that this is a
    # direct translation of RPM's algorithm..
    one = a
    two = b

    while one or two:
        # pop characters off 'til we hit a valid version character
        _, one = take_until(one, risverch)
        _, two = take_until(two, risverch)

        ch1 = one[0:1]
        ch2 = two[0:1]

        # tilde sorts lower than anything else
        if ch1 == '~' or ch2 == '~':
            if ch1 != '~': return 1
            if ch2 != '~': return -1
            one = one[1:]
            two = two[1:]
            continue

        # caret works like tilde, except that if one of the strings ends
        # the other is considered "higher"
        if ch1 == '^' or ch2 == '^':
            if one == '': return -1
            if two == '': return 1
            if ch1 != '^': return 1
            if ch2 != '^': return -1
            one = one[1:]
            two = two[1:]
            continue

        # If we hit the end of either string we're done.
        if not (one and two):
            break

        # Break the first completely alpha or numeric segment off each string
        if risdigit(one[0]):
            isnum = True
            s1, one = take_while(one, risdigit)
            s2, two = take_while(two, risdigit)
        else:
            isnum = False
            s1, one = take_while(one, risalpha)
            s2, two = take_while(two, risalpha)

        # If s2 is empty, then we had two segments of different types.
        # In that case, the numeric side is considered higher/newer.
        if not s2:
            return 1 if isnum else -1

        # For numbers, we strip leading zeroes and then assume longer numbers
        # are bigger. If they're the same length, we'll use a simple strcmp.
        if isnum:
            s1 = s1.lstrip('0')
            s2 = s2.lstrip('0')
            if len(s1) > len(s2):
                return 1
            if len(s1) < len(s2):
                return -1

        # Compare the segments as strings
        if s1 < s2:
            return -1
        if s1 > s2:
            return 1
        # No difference found. Keep iterating through the strings.

    # They both ended at the same time - they're equal!
    if not (one or two):
        return 0
    # Otherwise, whichever has characters left over wins
    return 1 if one else -1

# This function signature is gross, but this is how RPM rolls..
def rpm_evr_cmp(a, b):
    '''
    Compare two (e, v, r) tuples, returning (-1, 0, 1) for (a<b, a==b, a>b),
    as per rpm/lib/rpmvercmp.c:rpmVersionCompare()
    '''
    # rpmVersionCompare says:
    # "Missing epoch becomes zero here, which is what we want"
    e1, v1, r1 = _get_epoch(a[0]), a[1], a[2]
    e2, v2, r2 = _get_epoch(b[0]), b[1], b[2]
    # Compare epochs
    if e1 < e2:
        return -1
    elif e1 > e2:
        return 1
    # If epochs match, compare versions
    rc = rpmvercmp(v1, v2)
    if rc:
        return rc
    # If versions match, compare releases
    return rpmvercmp(r1, r2)

rpm_evr_key = cmp_to_key(rpm_evr_cmp)

def pkgtup_cmp(a, b):
    return rpm_evr_cmp((a.epoch, a.ver, a.rel), (b.epoch, b.ver, b.rel))

pkgtup_key = cmp_to_key(pkgtup_cmp)
