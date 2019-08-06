import os
import re
import unittest
from .test_common import TESTDIR

from rpmtoys.vercmp import rpmvercmp

def iter_rpmvercmp_at():
    vercmpre = re.compile(r'^RPMVERCMP\((\S+), +(\S+), +(\S+)\)')
    with open(os.path.join(TESTDIR, "rpmvercmp.at")) as inf:
        for line in inf:
            m = vercmpre.match(line)
            if m:
                a,b,v = m.groups()
                yield a,b,int(v)

class RPMVerCmp(unittest.TestCase):
    def test_rpmvercmp(self):
        for a,b,v in iter_rpmvercmp_at():
            with self.subTest(a=a,b=b,v=v):
                self.assertEqual(rpmvercmp(a,b), v)
