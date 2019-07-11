import unittest

from rpmtoys import rpm
from .test_common import RPMFILE

class Digests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._rpm = rpm(RPMFILE['fuse-common'])

    def test_digest(self):
        self.assertEqual(self._rpm.digest(), {
            'SHA1': '0033cbe607424ceed3de1919fb42ae74c9606f99',
            'SHA256': '531893c6a6ad470da7d4bceda8dc5d29fe274d5206717fe03c645b23b8acf37b',
            'MD5': b'\xdc|3<\x03\xab\xdd\x1d\xc5\xc9\xb9;\xacT\x96\x9a'
        })

    def test_checkdigest_hdr(self):
        r = self._rpm.checkdigests(payload=False, filedigests=False)
        self.assertEqual(r, {'hdr': {'SHA1': True, 'SHA256': True}})

    def test_checkdigest_payload(self):
        r = self._rpm.checkdigests(filedigests=False, hdr=False)
        self.assertEqual(r, {'payload': {'MD5': True}})

    def test_checkdigest_filedigests(self):
        r = self._rpm.checkdigests(hdr=False, payload=False)
        self.assertEqual(r, {'filedigests': {'/etc/fuse.conf': True}})

class FileInfo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._rpm = rpm(RPMFILE['fuse-common'])

    def test_nfiles_1(self):
        self.assertEqual(self._rpm.nfiles(), 1)
