# dino.util - utility functions

# like shutil.copyfileobj, but with a size limit
def copy_stream(inf, outf, size=None, blocksize=16*1024):
    read, wrote = 0, 0
    left = -1 if size is None else size
    while left:
        buf = inf.read(blocksize if left<0 else min(blocksize,left))
        read += len(buf)
        if not buf:
            break
        wrote += outf.write(buf)
        left -= wrote
    return wrote
