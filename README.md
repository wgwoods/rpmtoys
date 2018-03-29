# rpmtoys: fun with packaging!

Hello! This is my repo of RPM toys - little scripts and things that I use to
analyze RPM data and metadata.

What you'll find here:

## `rpm2cpio.sh`

A portable shell script to copy the archive payload out of an RPM and into its
own file, or to stdout.

Should work anywhere with POSIX `sh`, POSIX.2 `od`, and either a `sh`-builtin
`$(( ))` or POSIX `expr`.

## `rpmtoys/`

Python module used by scripts here. Includes low-level pure-Python RPM header
parsing and RPM tag metadata! Fun!

## `measure-metadata.py`

A script to examine actual RPM headers and determine the amount of space used
by each individual tag.

## `dnf-count-rpm-words.py`

Use DNF to fetch a list of all the RPM names in 'fedora' and 'updates', split
them up into meaningful "words", and dump some CSV data about those words.

This isn't particularly useful, but it's part of a blog post I'm writing and
it's also a nice simple example of using DNF directly in Python.

## `LICENSE`

Check the individual files for their licenses. If any file is somehow missing
a license header you may assume it's supposed to be covered by the toplevel
LICENSE file.
