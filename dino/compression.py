# dino.compression - compression/decompression helpers

import logging as log

from .const import CompressionID

# TODO: Define a CompressionOpts structure that we can store in the header,
# like squashfs does...

available_compressors = {"zstd", "xz"}

DEFAULT_COMPRESSION_LEVEL = {
    CompressionID.XZ: 2,        # Fedora default (ca. F30)
    CompressionID.ZSTD: 10,     # Diminishing returns above here...
}

DEFAULT_CHUNK_SIZE = 4*1024



class CompressionStreamWriter(object):
    def __init__(self, cobj, fobj):
        self._cobj = cobj
        self._fobj = fobj

    def write(self, data):
        return self._fobj.write(self._cobj.compress(data))

    def flush(self):
        r = self._fobj.write(self._cobj.flush())
        self._cobj = None
        return r

class MultiCompressor(object):
    def __init__(self, make_compress_obj, **kwargs):
        if not callable(make_compress_obj):
            raise ValueError(f'{make_compress_obj} is not callable')
        self._mkcobj = make_compress_obj
        self.args = kwargs
        log.debug("MultiCompressor(%s, kwargs=%s)", make_compress_obj, kwargs)

    def copy_stream(self, inf, outf, size=0, read_size=None, write_size=None):
        if read_size is None:
            read_size = DEFAULT_CHUNK_SIZE
        if write_size is None:
            write_size = DEFAULT_CHUNK_SIZE
        read = 0
        wrote = 0
        to_read = size or -1
        cobj = self._mkcobj(**self.args)
        while to_read and (read < to_read):
            chunk = inf.read(min(read_size, to_read))
            if not chunk:
                break
            read += len(chunk)
            wrote += outf.write(cobj.compress(chunk))
        wrote += outf.write(cobj.flush())
        return read, wrote

class CopyStreamMultiCompressor(MultiCompressor):
    def __init__(self, cctx):
        self._cctx = cctx
    def copy_stream(self, inf, outf, size=0, read_size=None, write_size=None):
        kwargs = dict()
        if size:
            kwargs['size'] = size
        if read_size:
            kwargs['read_size'] = read_size
        if write_size:
            kwargs['write_size'] = write_size
        return self._cctx.copy_stream(inf, outf, **kwargs)


# Utility function to get CompressionID by id or name (or None)
cidmap = {n.lower():cid for n,cid in CompressionID.__members__.items()}
cidmap['gzip'] = cidmap['zlib']
cidmap['gz'] = cidmap['gzip']
def get_compressid(which):
    if isinstance(which, int):
        return CompressionID(which)
    if which is None:
        return CompressionID.NONE
    if not isinstance(which, str):
        which = str(which, 'ascii', 'ignore')
    return cidmap.get(which.lower())

# We don't import the compression modules at the toplevel because I want this
# to work even if you don't have Every Compression Library installed.
# As long as you have the ones you actually use, we should be fine.

def get_compressor(which, level=None):
    which = get_compressid(which)
    if level is None or level < 0:
        level = DEFAULT_COMPRESSION_LEVEL.get(which)
    if which == CompressionID.ZSTD:
        import zstandard as zstd
        cctx = zstd.ZstdCompressor(write_content_size=True, level=level)
        return CopyStreamMultiCompressor(cctx)
    elif which == CompressionID.XZ:
        import lzma
        return MultiCompressor(lzma.LZMACompressor, preset=level)
    else:
        raise NotImplementedError(f"{which.name} not implemented!")

def get_decompressor(which):
    which = get_compressid(which)
    if which == CompressionID.ZSTD:
        import zstandard as zstd
        return zstd.ZstdDecompressor()
    elif which == CompressionID.XZ:
        import lzma
        return lzma.LZMADecompressor()
    else:
        raise NotImplementedError("{which.name} not implemented!")

# FIXME: need tests to confirm that each chunk of output from the compressor
# can be individually uncompressed....
# FIXME: also need some benchmarks to compare performance of algorithms
# (compresion ratio, decompression speed/mem use)
