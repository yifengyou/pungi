# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import argparse
import os
import sys

from parameterized import parameterized

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi_utils import config_utils


class TestDefineHelpers(unittest.TestCase):
    @parameterized.expand(
        [
            ([], {}),
            (["foo=bar", "baz=quux"], {"foo": "bar", "baz": "quux"}),
            (["foo="], {"foo": ""}),
            (["foo==bar"], {"foo": "=bar"}),
        ]
    )
    def test_extract_defines(self, input, expected):
        self.assertEqual(config_utils.extract_defines(input), expected)

    @parameterized.expand(["foo=bar", "foo=", "foo==bar"])
    def test_validate_define_correct(self, value):
        self.assertEqual(config_utils.validate_definition(value), value)

    @parameterized.expand(["foo", "=", "=foo", "1=2"])
    def test_validate_define_incorrect(self, value):
        with self.assertRaises(argparse.ArgumentTypeError):
            config_utils.validate_definition(value)

    def test_remove_unknown(self):
        conf = {"foo": "bar"}
        config_utils.remove_unknown(conf, ["foo"])
        self.assertEqual(conf, {})

    def test_remove_known(self):
        conf = {"release_name": "bar"}
        config_utils.remove_unknown(conf, ["release_name"])
        self.assertEqual(conf, {"release_name": "bar"})
