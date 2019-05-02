# This is *not* auto-generated, because rpmtag.h isn't set up for that.
# See rpmtag.h:rpmSigTag_e for which tags are actually defined for sig headers.
# TODO: add obsolete/deprecated items?

sigtagtbl = [
    ['Size', 1000, 'INT32', 'SCALAR', False],
    ['PGP', 1002, 'BIN', 'SCALAR', False],
    ['MD5', 1004, 'BIN', 'SCALAR', False],
    ['GPG', 1005, 'BIN', 'SCALAR', False],
    ['Payloadsize', 1007, 'INT32', 'SCALAR', False],
    ['Reservedspace', 1008, 'BIN', 'SCALAR', False],
    ['DSA', 267, 'BIN', 'SCALAR', False],
    ['RSA', 268, 'BIN', 'SCALAR', False],
    ['SHA1', 269, 'STRING', 'SCALAR', False],
    ['Longsize', 270, 'INT64', 'SCALAR', False],
    ['Longarchivesize', 271, 'INT64', 'SCALAR', False],
    ['SHA256', 273, 'STRING', 'SCALAR', False],
    ['Filesignatures', 274, 'STRING_ARRAY', 'ARRAY', False],
    ['Filesignaturelength', 275, 'INT32', 'SCALAR', False],
    # These are header markers of some kind; Headersignatures definitely shows
    # up in real-world RPMs, but I don't know about the others. Still, better
    # to have them here so we can recognize them if they do appear.
    ['Headerimage', 61, 'NULL', 'ANY', False],
    ['Headersignatures', 62, 'NULL', 'ANY', False],
    ['Headerimmutable', 63, 'NULL', 'ANY', False],
    ['Headerregions', 64, 'NULL', 'ANY', False],
]
