# dino.fileview: treat a chunk of a file as its own file-like object

from os import SEEK_SET, SEEK_CUR, SEEK_END

# FIXME This probably isn't MT-safe at all
class FileView(object):
    def __init__(self, fobj, offset, size):
        self._file = fobj
        self._base = offset
        self._size = size
        self._offset = 0

    def tell(self):
        return self._offset

    def seek(self, offset, whence=SEEK_SET):
        if whence == SEEK_SET:
            self._offset = offset
        elif whence == SEEK_CUR:
            self._offset += offset
        elif whence == SEEK_END:
            self._offset = self._size + offset
        return self._file.seek(self._base+self._offset, SEEK_SET)

    def read(self, size=-1):
        maxsize = self._size - self._offset
        if size < 0:
            size = maxsize
        oldpos = self._file.tell()
        self.seek(self._offset)
        d = self._file.read(min(size, maxsize))
        self._file.seek(oldpos)
        return d

    # TODO: readable, readinto, readinto1, etc.


