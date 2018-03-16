# rpmtoys: fun with packaging!

Hello! This is my repo of RPM toys - little scripts and things that I use to
analyze RPM data and metadata.

What you'll find here:

## `rpm2cpio.sh`

A portable shell script to copy the archive payload out of an RPM and into its
own file, or to stdout.

Should work anywhere with POSIX `sh`, POSIX.2 `od`, and either a `sh`-builtin
`$(( ))` or POSIX `expr`.

## `LICENSE`

Check the individual files for their licenses. If any file is somehow missing
a license header you may assume it's supposed to be covered by the toplevel
LICENSE file.
