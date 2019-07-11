import unittest
from .test_common import RPMFILE

from rpmtoys import Tag
from rpmtoys.hdr import rpmhdr, TagEntry

# Yeah, I know these are more like functional tests than unit tests, but this
# is a toy library and these get the job done.
class RPMhdr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filename = RPMFILE['fuse-common']
        cls.r = rpmhdr(cls.filename)
        #cls.filedata = open(cls.filename, 'rb').read()
        #cls.fileobj = io.BytesIO(cls.filedata)

    def test_verify_region(self):
        self.assertEqual(self.r.hdr.regiontag, 63)
        self.assertEqual(self.r.sig.regiontag, 62)

    def test_tagent_by_tag(self):
        self.assertEqual(self.r.hdr.tagent[1048],
                         TagEntry(1048, 4, 444, 5, 20, 20))

    def test_tagent_ordering(self):
        # Tag 1048 (REQUIREFLAGS) is the 30th tag in this RPM
        self.assertEqual(list(self.r.hdr.tagent).index(1048), 30)

    def test_encoding_val(self):
        self.assertEqual(self.r.hdr.encoding,
                         self.r.hdr.tagval[Tag.ENCODING].decode('ascii'))


class TagEntryStruct(unittest.TestCase):
    te_item = TagEntry(1048, 4, 444, 5, 20, 20)
    te_bytes = b'\0\0\x04\x18\0\0\0\x04\0\0\x01\xbc\0\0\0\x05'

    def test_unpack(self):
        self.assertEqual(TagEntry._unpack(self.te_bytes),
                         TagEntry(1048, 4, 444, 5, None, None))

    def test_pack(self):
        self.assertEqual(self.te_item._pack(), self.te_bytes)

    def test_fields(self):
        self.assertEqual(self.te_item.tag, 1048)
        self.assertEqual(self.te_item.type, 4)
        self.assertEqual(self.te_item.offset, 444)
        self.assertEqual(self.te_item.count, 5)
        self.assertEqual(self.te_item.size, 20)
        self.assertEqual(self.te_item.realsize, 20)

