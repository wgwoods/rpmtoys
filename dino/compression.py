# dino.compression - compression/decompression helpers

from .const import CompressionID

# TODO: Define a CompressionOpts structure that we can store in the header

# We don't import the compression modules at the toplevel because I want this
# to work even if you don't have Every Compression Library installed.
# As long as you have the ones you actually use, we should be fine.

def get_compressor(which, level=None):
    which = CompressionID(which)
    if which == CompressionID.ZSTD:
        import zstandard as zstd
        if level and level < 0:
            level = zstd.MAX_COMPRESSION_LEVEL
        cctx = zstd.ZstdCompressor(write_content_size=True, level=level)
        return cctx
    elif which == CompressionID.XZ:
        import lzma
        if level and level < 0:
            level = 9
        # TODO: this doesn't support zstd's copy_stream function.
        # Might need a wrapper object to make the different compressors
        # all play nice, while still making sure they can flush and
        # start a new compression frame when needed..
        cctx = lzma.LZMACompressor(preset=level)
        return cctx
    else:
        raise NotImplementedError(f"{which.name} not implemented!")

def get_decompressor(which):
    which = CompressionID(which)
    if which == CompressionID.ZSTD:
        import zstandard as zstd
        return zstd.ZstdDecompressor()
    elif which == CompressionID.XZ:
        import lzma
        return lzma.LZMADecompressor()
    else:
        raise NotImplementedError("{which.name} not implemented!")
