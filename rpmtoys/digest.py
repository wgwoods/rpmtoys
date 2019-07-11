# rpmtoys.digest - stuff for verifying package digest/hashes

import hashlib
from enum import IntEnum
from .hdr import rpmhdr

# See rpm/rpmio/rpmpgp.h:pgpPubkeyAlgo_e
class HashAlgo(IntEnum):
    MD5         =  1
    SHA1        =  2
    RIPEMD160   =  3
    # Wonder where 4 went!!!
    MD2         =  5
    TIGER192    =  6
    HAVAL_5_160 =  7
    SHA256      =  8
    SHA384      =  9
    SHA512      = 10
    SHA224      = 11

# Not all of these are supported by hashlib, but the important ones
# (md5, sha1, sha256) are guaranteed to be there.
HashName = [None,
            'md5',
            'sha1',
            'ripemd160',
            None,
            'md2',
            'tiger192',
            'haval_5_160',
            'sha256',
            'sha384',
            'sha512',
            'sha224',
]

def gethasher(algo):
    if isinstance(algo, int):
        algo = HashName[algo]
    return hashlib.new(algo)

class RPMVerifier(object):
    def __init__(self):
        self.context = None
        self.expected = None
        self.result = None
        self.done = False

    def start(self, hdr):
        self.done = True
    def update_hdr(self, data):
        pass
    def finish_hdr(self):
        pass
    def update_payload(self, data):
        pass
    def finish_payload(self):
        pass
    def ok(self):
        # default implementation
        return self.expected == self.result

class SHA1Verifier(RPMVerifier):
    def start(self, rpm):
        self.context = hashlib.sha1()
        self.expected = rpm.sig.getval(SigTag.SHA1)
    def update_hdr(self, data):
        self.context.update(data)
    def finish_hdr(self):
        self.result = self.context.hexdigest()
        self.done = True

class SHA256Verifier(RPMVerifier):
    def start(self, rpm):
        self.context = hashlib.sha256()
        self.expected = rpm.sig.getval(SigTag.SHA256)
    def update_hdr(self, data):
        self.context.update(data)
    def finish_hdr(self):
        self.result = self.context.hexdigest()
        self.done = True

class MD5Verifier(RPMVerifier):
    def start(self, hdr):
        self.context = hashlib.md5()
        self.expected = hdr.getval(SigTag.MD5)
    def update_hdr(self, data):
        self.context.update(data)
    def update_payload(self, data):
        self.context.update(data)
    def finish_payload(self):
        self.result = self.context.digest()
        self.done = True

class PayloadDigestVerifier(RPMVerifier):
    def start(self, hdr):
        self.context = gethasher(hdr.getval(Tag.PAYLOADDIGESTALGO))
        self.expected = hdr.getval(Tag.PAYLOADDIGEST)
    def update_payload(self, data):
        self.context.update(data)
    def finish_payload(self):
        self.result = self.context.hexdigest()
        self.done = True

verifiers = {
    'md5':MD5Verifier,
    'sha1':SHA1Verifier,
    'sha256':SHA256Verifier,
    'payloaddigest':PayloadDigestVerifier,
}

# TODO: multithread
# TODO: will probably end up refactoring..
def digest(rpmfn, md5=True, sha1=True, sha256=True):

    if not (md5 or sha1 or sha256):
        return {}

    digests = dict()

    if md5:
        md5 = hashlib.md5()
    if sha1:
        sha1 = hashlib.sha1()
    if sha256:
        sha256 = hashlib.sha256()

    r = rpmhdr(rpmfn)

    with open(rpmfn, 'rb') as fobj:
        # skip lead + sig
        fobj.seek(r.lead._struct.size + r.sig.size)
        # hash the header
        # TODO: buffered io?
        hdr = fobj.read(r.hdr.size)
        for h in (md5, sha1, sha256):
            if h:
                h.update(hdr)
        # sha1 and sha256 just cover the header
        if sha1:
            digests['SHA1'] = sha1.hexdigest()
        if sha256:
            digests['SHA256'] = sha256.hexdigest()

        # md5 also covers payload, and is binary
        if md5:
            # TODO: buffered io?
            md5.update(fobj.read())
            digests['MD5'] = md5.digest()

    return digests
