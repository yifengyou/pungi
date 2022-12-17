# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import tempfile
from textwrap import dedent

import six

import os

from pungi.wrappers import fus

from .helpers import touch, PungiTestCase


class TestGetCmd(unittest.TestCase):
    def test_minimum_command(self):
        cmd = fus.get_cmd("conf", "x86_64", repos=[], lookasides=[])
        self.assertEqual(cmd, ["fus", "--verbose", "--arch", "x86_64", "@conf"])

    def test_full_command(self):
        cmd = fus.get_cmd(
            "conf",
            "x86_64",
            ["/tmp/first", "/tmp/second"],
            ["/tmp/fst", "/tmp/snd"],
            platform="f29",
            filter_packages=["foo", "bar"],
        )
        self.assertEqual(
            cmd,
            [
                "fus",
                "--verbose",
                "--arch",
                "x86_64",
                "--repo=lookaside-0,lookaside,/tmp/fst",
                "--repo=lookaside-1,lookaside,/tmp/snd",
                "--repo=repo-0,repo,/tmp/first",
                "--repo=repo-1,repo,/tmp/second",
                "--platform=f29",
                "--exclude=bar",
                "--exclude=foo",
                "@conf",
            ],
        )

    def test_strip_file_protocol(self):
        cmd = fus.get_cmd("conf", "x86_64", ["file:///tmp"], [])
        self.assertEqual(
            cmd,
            [
                "fus",
                "--verbose",
                "--arch",
                "x86_64",
                "--repo=repo-0,repo,/tmp",
                "@conf",
            ],
        )

    def test_preserves_http_protocol(self):
        cmd = fus.get_cmd("conf", "x86_64", [], ["http://r"])
        self.assertEqual(
            cmd,
            [
                "fus",
                "--verbose",
                "--arch",
                "x86_64",
                "--repo=lookaside-0,lookaside,http://r",
                "@conf",
            ],
        )

    def test_strip_file_protocol_lookaside(self):
        cmd = fus.get_cmd("conf", "x86_64", [], ["file:///r"])
        self.assertEqual(
            cmd,
            [
                "fus",
                "--verbose",
                "--arch",
                "x86_64",
                "--repo=lookaside-0,lookaside,/r",
                "@conf",
            ],
        )

    def test_preserves_http_protocol_lookaside(self):
        self.assertEqual(
            fus.get_cmd("conf", "x86_64", [], ["http:///tmp"]),
            [
                "fus",
                "--verbose",
                "--arch",
                "x86_64",
                "--repo=lookaside-0,lookaside,http:///tmp",
                "@conf",
            ],
        )


class TestWriteConfig(PungiTestCase):
    def test_write_sorted_mix(self):
        f = os.path.join(self.topdir, "solvables")
        fus.write_config(f, ["moda:master"], ["pkg", "foo"])
        self.assertFileContent(
            f,
            dedent(
                """\
                module(moda:master)
                pkg
                foo
                """
            ),
        )


class TestParseOutput(unittest.TestCase):
    def setUp(self):
        _, self.file = tempfile.mkstemp(prefix="test-parse-fus-out-")

    def tearDown(self):
        os.remove(self.file)

    def test_skips_debug_line(self):
        touch(self.file, "debug line\n")
        packages, modules = fus.parse_output(self.file)
        self.assertEqual(packages, set())
        self.assertEqual(modules, set())

    def test_separates_arch(self):
        touch(self.file, "pkg-1.0-1.x86_64@repo-0\npkg-1.0-1.i686@repo-0\n")
        packages, modules = fus.parse_output(self.file)
        six.assertCountEqual(
            self,
            packages,
            [("pkg-1.0-1", "x86_64", frozenset()), ("pkg-1.0-1", "i686", frozenset())],
        )
        self.assertEqual(modules, set())

    def test_marks_modular(self):
        touch(self.file, "*pkg-1.0-1.x86_64@repo-0\n")
        packages, modules = fus.parse_output(self.file)
        self.assertEqual(
            packages,
            set([("pkg-1.0-1", "x86_64", frozenset(["modular"]))]),
        )
        self.assertEqual(modules, set())

    def test_extracts_modules(self):
        touch(self.file, "module:mod:master:20181003:cafebeef.x86_64@repo-0\n")
        packages, modules = fus.parse_output(self.file)
        self.assertEqual(packages, set())
        self.assertEqual(modules, set(["mod:master:20181003:cafebeef"]))
