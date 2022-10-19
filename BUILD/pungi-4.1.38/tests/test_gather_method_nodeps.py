# -*- coding: utf-8 -*-

import mock
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.gather.methods import method_nodeps as nodeps
from tests import helpers

COMPS_FILE = os.path.join(helpers.FIXTURE_DIR, 'comps.xml')


class TestWritePungiConfig(helpers.PungiTestCase):
    def setUp(self):
        super(TestWritePungiConfig, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.compose.paths.work.comps = mock.Mock(return_value=COMPS_FILE)

    def test_expand_group(self):
        packages = nodeps.expand_groups(self.compose, 'x86_64', None, ['core', 'text-internet'])
        self.assertItemsEqual(packages, [('dummy-bash', 'x86_64'),
                                         ('dummy-elinks', 'x86_64'),
                                         ('dummy-tftp', 'x86_64')])
