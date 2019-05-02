# rpmtoys.payload - support routines for dealing with RPM payloads

import libarchive

def libarchive_payload_reader(r, block_size=None):
    payload = r.open_payload()
    return libarchive.stream_reader(payload,
                                    format_name=payload.format or 'all',
                                    filter_name=payload.compressor or 'all',
                                    block_size=block_size or 4096)
