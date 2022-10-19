# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import mock
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.gather.sources.source_module import GatherSourceModule
from tests import helpers
from pungi import Modulemd


@unittest.skipUnless(Modulemd is not None, "Skipped test, no module support.")
class TestGatherSourceModule(helpers.PungiTestCase):
    def setUp(self):
        super(TestGatherSourceModule, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

    def _add_pkg(self, arch):
        mock_rpm = mock.Mock(
            version="1.0.0",
            release="1",
            epoch=0,
            excludearch=None,
            exclusivearch=None,
            sourcerpm="pkg-1.0.0-1",
            nevra="pkg-0:1.0.0-1.%s" % arch,
            arch=arch,
        )
        mock_rpm.name = "pkg"
        self.compose.variants["Server"].nsvc_to_pkgset[
            "testmodule:master:1:2017"
        ].rpms_by_arch[arch] = [mock_rpm]

    def test_without_modules(self):
        source = GatherSourceModule(self.compose)
        packages, groups = source("x86_64", self.compose.variants["Server"])
        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(groups, [])

    def test_include_two_packages(self):
        self.compose.variants["Server"].add_fake_module(
            "testmodule:master:1:2017",
            rpm_nvrs=["pkg-0:1.0.0-1.x86_64", "pkg-0:1.0.0-1.i686"],
            with_artifacts=True,
            mmd_arch="x86_64",
        )

        self._add_pkg("x86_64")
        self._add_pkg("i686")

        source = GatherSourceModule(self.compose)
        packages, groups = source("x86_64", self.compose.variants["Server"])
        self.assertItemsEqual(
            [(rpm[0].nevra, rpm[1]) for rpm in packages],
            [("pkg-0:1.0.0-1.x86_64", None), ("pkg-0:1.0.0-1.i686", None)],
        )
        self.assertItemsEqual(groups, [])

    def test_does_not_include_unlisted(self):
        self.compose.variants["Server"].add_fake_module(
            "testmodule:master:1:2017",
            rpm_nvrs=[],
            with_artifacts=True,
            mmd_arch="x86_64",
        )

        self._add_pkg("x86_64")

        source = GatherSourceModule(self.compose)
        packages, groups = source("x86_64", self.compose.variants["Server"])
        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(groups, [])
