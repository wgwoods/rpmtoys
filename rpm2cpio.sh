#!/bin/sh
# rpm2cpio.sh: minimal, portable script to extract the cpio payload from an rpm
#
# Copyright (c) 2016 Red Hat, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Author: Will Woods <wwoods@redhat.com>

# This script should work pretty much anywhere; it just needs:
#
#   1) some kind of /bin/sh,
#   2) $(( )) or expr(1) for math, and
#   3) a POSIX.2 (IEEE Std 1003.2-1992) compliant od(1) binary.
#
# I'm open to making it work using weird od or hexdump programs but this
# works with everything *I* have access to, so I'm calling it good.
#
# For more information about the RPM file format, see the docs at rpm.org:
#   http://ftp.rpm.org/max-rpm/s1-rpm-file-format-rpm-file-format.html
# or the "Package File Format" section in the LSB (version 1.3.0 and later):
#   http://refspecs.linuxfoundation.org/LSB_1.3.0/gLSB/gLSB/swinstall.html

_prog="rpm2cpio.sh"
_file="<stdin>"

# Check if the shell can handle $(( )) or not.
# NOTE: keep it inside quotes or it'll blow up ancient shells like heirloom-sh
if ( eval 'f=$((1+1))' >/dev/null 2>&1 ); then
    # NOTE: busybox ash doesn't handle $@ correctly here, so we use $*
    math() { eval 'echo $(( $* ))'; }
else
    # fallback: use expr(1)
    math() { expr "$@"; }
fi
# Quick test to make sure we can do math correctly
if [ `math 6 \* 8 - 14 % 8` != 42 ]; then
    echo "$_prog: this shell can't do math?"
    exit 255
fi

# abort "msg": print error message to stderr and exit the shell
abort() {
    echo "$_prog: $_file: error: $@" >&2
    exit 1
}

# read_magic_bytes: read 4 bytes from stdin, print them as 8 hex digits
read_magic_bytes() {
    set -- `od -A n -t x1 -N 4`
    echo "$1$2$3$4"
}

# skip_bytes N: read and discard N bytes from stdin
skip_bytes() {
    od -N "$1" > /dev/null
}

# read_u32be: read 4 bytes from stdin, print value as a big-endian u32int
read_u32be() {
    set -- `od -A n -t u1 -N 4`
    math $1 \* 16777216 + $2 \* 65536 + $3 \* 256 + $4
}

# check the RPM magic and skip over the Lead section
check_rpm_lead() {
    magic=`read_magic_bytes`
    if [ "$magic" != "edabeedb" ]; then return 1; fi
    skip_bytes 92 # lead is 0x60 (96) bytes long, we've read 4, so skip 92 more
}

# read an RPM Header Section header (yes, that's what they're called)
read_section_header() {
    magic=`read_magic_bytes`
    if [ "$magic" != "8eade801" ]; then return 1; fi
    reserved=`read_u32be` # 4 reserved, empty bytes
    icount=`read_u32be`
    dsize=`read_u32be`
    secsize=`math 16 \* $icount + $dsize`
    echo $secsize
}

# skip over the RPM lead, Signature section, and Header section to the payload
rpm_skip_to_payload() {
    # handle the lead
    check_rpm_lead || abort "not an RPM"

    # read the Signature section header
    secsize=`read_section_header` || abort "bad RPM signature section header"

    # pad section size to multiple of 8 bytes
    extra=`math $secsize % 8`
    if [ $extra -gt 0 ]; then
        secsize=`math $secsize + 8 - $extra`
    fi

    # skip Signature section
    skip_bytes $secsize

    # read Header section header
    secsize=`read_section_header` || abort "can't find RPM header section"

    # skip Header section
    skip_bytes $secsize

    # we're now at the payload! yay!
    cat
}

# magic2ext HEXMAGIC: print the file extension for the given file magic bytes
magic2ext() {
    case $1 in
        1f8b*) echo gz ;;       # 0x1f 0x8b
        377a*) echo 7z ;;       # "7z"
        504b*) echo zip ;;      # "PK"
        425a68*) echo bz2 ;;    # "BZh"
        fd377a58) echo xz ;;    # 0xfd "7zX"
        4c5a4950) echo lz ;;    # "LZIP"
        4c5a5249) echo lrz ;;   # "LRZI"
        2?b52ffd) echo zst ;;   # 0xFD2FB52?, but little-endian
        30373037) echo cpio ;;  # "0707"
        75737461) echo tar ;;   # "usta"
        *) echo unk ;;
    esac
}

# TODO: could have a better fallback for systems without mktemp..
_mktemp() {
    local tmpstem="${TMPDIR:-/tmp}/${_prog}"
    mktemp "${tmpstem}.XXXXXXXXXXXX" || echo "${tmpstem}.$$"
}

# rpm2cpio RPMFILE: dump RPMFILE payload to RPMFILE.[ext], print output filename
rpm2cpio() {
    rpm="$1"
    outf=""
    tmpfile=`_mktemp`
    # remove tmpfile on exit or error
    trap "rm -f \"$tmpfile\"" 0 1 2 3 15
    # dump the RPM payload to a temporary file
    rpm_skip_to_payload < "$rpm" > "$tmpfile"
    # figure out the proper extension for the payload
    magic=`read_magic_bytes < "$tmpfile"`
    ext=`magic2ext $magic`
    case $ext in
        tar|zip|cpio) outf="$rpm.$ext" ;;
        *)            outf="$rpm.cpio.$ext" ;;
    esac
    # move tempfile to proper output filename
    mv "$tmpfile" "$outf" && echo "$outf" && trap 0 1 2 3 15
}

if [ $# = 0 ]; then
    echo "Usage: $_prog RPMFILE"
    echo "Copy archive out of RPMFILE to RPMFILE.<EXT>, and print its name."
    echo "<EXT> is guessed from the archive file header."
    echo "If RPMFILE is -, read stdin and write to stdout."
elif [ "$1" = "-" ]; then
    rpm_skip_to_payload
else
    _file="$1"
    rpm2cpio "$1"
fi
