# -*- coding: utf-8 -*-

import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests import helpers
from pungi.ostree import utils


class GetRefFromTreefileTest(helpers.PungiTestCase):
    def setUp(self):
        super(GetRefFromTreefileTest, self).setUp()
        self.json = os.path.join(self.topdir, "treefile.json")
        self.yaml = os.path.join(self.topdir, "treefile.yaml")

    def test_reads_json(self):
        helpers.touch(self.json, """{"ref": "master"}""")
        self.assertEqual(utils.get_ref_from_treefile(self.json), "master")

    def test_reads_yaml(self):
        helpers.touch(self.yaml, """ref: master""")
        self.assertEqual(utils.get_ref_from_treefile(self.yaml), "master")

    @mock.patch("pungi.ostree.utils.getBaseArch")
    def test_replaces_basearch(self, getBaseArch):
        getBaseArch.return_value = "x86_64"
        helpers.touch(self.json, """{"ref": "${basearch}/master"}""")
        self.assertEqual(utils.get_ref_from_treefile(self.json), "x86_64/master")

    @mock.patch("pungi.ostree.utils.getBaseArch")
    def test_replaces_basearch_for_given_arch(self, getBaseArch):
        getBaseArch.return_value = "x86_64"
        helpers.touch(self.json, """{"ref": "${basearch}/master"}""")
        self.assertEqual(
            utils.get_ref_from_treefile(self.json, arch="foo"), "x86_64/master"
        )
        self.assertEqual(getBaseArch.call_args_list, [mock.call("foo")])

    def test_handles_invalid_json(self):
        helpers.touch(self.json, """{"ref" "master"}""")
        self.assertIsNone(utils.get_ref_from_treefile(self.json))

    def test_handles_invalid_yaml(self):
        helpers.touch(self.yaml, """{ ref\n - master""")
        self.assertIsNone(utils.get_ref_from_treefile(self.yaml))

    def test_handles_missing_file(self):
        self.assertIsNone(utils.get_ref_from_treefile(self.json))
