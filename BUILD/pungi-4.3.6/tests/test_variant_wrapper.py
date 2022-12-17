# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest
from six.moves import cStringIO

from pungi.wrappers.variants import VariantsXmlParser

VARIANTS_WITH_WHITESPACE = """
<variants>
  <variant id="Foo" name="Foo" type="variant">
    <arches><arch>x86_64 </arch></arches>
    <groups><group> core</group></groups>
    <environments><environment> foo </environment></environments>
  </variant>
</variants>
"""


class TestVariantsXmlParser(unittest.TestCase):
    def test_whitespace_in_file(self):
        input = cStringIO(VARIANTS_WITH_WHITESPACE)

        with self.assertRaises(ValueError) as ctx:
            VariantsXmlParser(input)

        self.assertIn("Tag arch on line 4", str(ctx.exception))
        self.assertIn("Tag group on line 5", str(ctx.exception))
        self.assertIn("Tag environment on line 6", str(ctx.exception))
