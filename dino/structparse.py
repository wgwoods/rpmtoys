# dino.structparser - like argparse and struct had a baby

import sys
from struct import Struct, calcsize
from collections import OrderedDict, Counter, namedtuple

if sys.byteorder == 'big':
    HOST_ENDIAN = '>'
else:
    HOST_ENDIAN = '<'

class StructParser(object):
    '''Kind of like ArgumentParser, but for structs'''
    def __init__(self, structname, endian=HOST_ENDIAN, _LE=None, _BE=None):
        self._fieldmap = OrderedDict()
        self._structobj = None
        self._dataclass = None
        self.structname = structname
        self.LE = None
        self.BE = None

        if endian == 'big':
            endian = '>'
        elif endian == 'little':
            endian = '<'
        if endian not in '<!=>':
            raise ValueError("endian must be one of ('<', '>', '!', '=')")
        self._endian = endian

        if endian == '=':
            endian = HOST_ENDIAN
        if endian == '<':
            self.LE = self
            self.BE = _BE or self.__class__(structname, endian='>', _LE=self)
            self.BE._fieldmap = self._fieldmap
        else:
            self.BE = self
            self.LE = _LE or self.__class__(structname, endian='>', _BE=self)
            self.LE._fieldmap = self._fieldmap

    class StructField(object):
        def __init__(self, name, fmt, type=None, choices=None, default=None):
            self.name = name
            self.fmt = fmt
            self.type = type
            self.choices = choices
            self.default = default

        def parse_val(self, rawval):
            val = self.type(rawval) if self.type else rawval
            if self.choices and val not in self.choices:
                raise ValueError(f"{val!r} not valid for {self.name}")
            return val

        def __repr__(self):
            return (f'<'
                    f'{self.__class__.__name__} {self.name!r}: '
                    f'fmt={self.fmt} ({calcsize(self.fmt)})'
                    f'{f", type={self.type.__name__}" if self.type else ""}'
                    f'{f", type={self.default}" if self.default else ""}'
                    f'>')

    def add_field(self, name, fmt, type=None, choices=None, default=None):
        self._fieldmap[name] = self.StructField(name, fmt, type, choices, default)
        # Adding a new field invalidates the cached struct/dataclass
        self._structobj = None
        self._dataclass = None

    @property
    def endian(self):
        return self._endian

    @property
    def _fields(self):
        return list(self._fieldmap.values())

    @property
    def _struct(self):
        if not self._structobj:
            fmt = ''.join(f.fmt for f in self._fields)
            self._structobj = Struct(self.endian + fmt)
        return self._structobj

    @property
    def structsize(self):
        return self._struct.size

    @property
    def _nstup(self):
        # TODO: this should have a _pack method or something
        # TODO: could totally use a python dataclass here instead...
        if not self._dataclass:
            self._dataclass = namedtuple(self.structname, self._fieldmap)
        return self._dataclass

    def make(self, **kwargs):
        return self._nstup._make(kwargs.get(f.name, f.default) for f in self._fields)

    def pack(self, ns):
        if not isinstance(ns, self._dataclass):
            raise ValueError
        return self._struct.pack(*ns)

    def _unpack2ns(self, tup):
        return self._nstup._make(f.parse_val(v) for f,v in zip(self._fields, tup))

    def iter_parse(self, buf):
        for tup in self._struct.iter_unpack(buf):
            yield self._unpack2ns(tup)

    def parse_bytes(self, buf, offset=0):
        return self._unpack2ns(self._struct.unpack_from(buf, offset))

    def read1_from(self, fobj):
        return self.parse_bytes(fobj.read(self._struct.size))

    def iter_read_from(self, fobj, size):
        return self.iter_parse(fobj.read(size))
