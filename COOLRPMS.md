# COOL RPMS

Here I'm documenting a nice selection of RPMs that can be used as a
representative sample of Fedora content.

The goal is to pick a set of RPMs that cover the most common categories of
packages, plus interesting corner cases (like empty packages or %verify
scripts).

There's two distinct sets of criteria: interesting _metadata_, and interesting
_payloads_. Dealing with metadata and payloads are very closely related
problems, but there's different use cases and requirements for each, so be
sure to consider that when you're, uh, doing whatever you're doing with this
stuff.

## Basic packages

* Simple binary package
  * gzip, which
* Simple library package
  * libidn, zlib
* Super-common / important packages
  * glibc, kernel, systemd
* Big app with frequent updates
  * libreoffice
* Packages that had day-2 updates on my F33 workstation:
  * Large-ish packages with few files:
    * nodejs-libs      (43MB, 10 files)
    * nodejs-full-i18n (28MB, 2 files)
    * llvm-libs        (87MB, 19 files)
  * Largest packages:
    * containerd  (135MB, 53 files)
    * firefox     (255MB, 204 files)
    * ansible     (102MB, 17851 files)
    * nodejs-docs (62MB,  794 files)

## Interesting metadata

* Library that requires another library
  * libpng
* Package with rich deps
  * annobin, redhat-rpm-config, dnf, hexchat
* Packages with "virtual provides"
  * exim, sendmail, postfix (`Provides: server(smtp)`)
* Packages that require a virtual provides
  * sagator-core (`Requires: server(smtp)`)
* Packages with triggers
  * varnish, tuned, rpcbind
* Package with filetriggers
  * systemd
* Package with a verify script
  * ksh
* Packages with no files
  * setools, wine, R, systemtap
* Packages with %ghost files
  * gnupg2, jwhois, tuned, pax, at
* Packages with %config files
  * samba, arpwatch, ddd, john
* Packages with hardlinks
  * git, git-core
* Packages with symlinks
  * geronimo-jta
* Packages with filecaps
  * sway, wireshark-cli, iputils, fping
* Packages with epoch explicitly set to 0
  * ?TODO

## Common / interesting payloads

* An extremely small package, for unit tests etc
  * fuse-common
* A sampling of packages that are updated frequently
  * kernel, git, vim, wine, cargo, cockpit, flatpak
* A sampling of Python packages
  * **TODO**
* A sampling of Ruby packages
  * **TODO**
* A sampling of Java packages
  * **TODO**
* [and so on for golang, nodejs, haskell, rust, php, perl]
  * **TODO**
* Some docs packages
  * **TODO**
* Some javadoc packages
  * **TODO**
* Some fonts
  * **TODO**
* Some package with arbitrary binary data (firmware? game levels?)
  * **TODO**
