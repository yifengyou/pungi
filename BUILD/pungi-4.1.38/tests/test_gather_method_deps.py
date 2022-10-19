# -*- coding: utf-8 -*-

import mock
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.gather.methods import method_deps as deps
from tests import helpers


class TestWritePungiConfig(helpers.PungiTestCase):
    def setUp(self):
        super(TestWritePungiConfig, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

    def assertWritten(self, PungiWrapper, **kwargs):
        wrapper = PungiWrapper.return_value
        self.assertEqual(wrapper.mock_calls,
                         [mock.call.write_kickstart(**kwargs)])

    @mock.patch('pungi.phases.gather.methods.method_deps.PungiWrapper')
    def test_correct(self, PungiWrapper):
        pkgs = [('pkg1', None), ('pkg2', 'x86_64')]
        grps = ['grp1']
        filter = [('pkg3', None), ('pkg4', 'x86_64')]
        white = mock.Mock()
        black = mock.Mock()
        prepopulate = mock.Mock()
        fulltree = mock.Mock()
        deps.write_pungi_config(self.compose, 'x86_64', self.compose.variants['Server'],
                                pkgs, grps, filter, white, black,
                                prepopulate=prepopulate, fulltree_excludes=fulltree)
        self.assertWritten(PungiWrapper, packages=['pkg1', 'pkg2.x86_64'],
                           ks_path=self.topdir + '/work/x86_64/pungi/Server.x86_64.conf',
                           lookaside_repos={}, multilib_whitelist=white, multilib_blacklist=black,
                           groups=['grp1'], prepopulate=prepopulate,
                           repos={'pungi-repo': self.topdir + '/work/x86_64/repo',
                                  'comps-repo': self.topdir + '/work/x86_64/comps_repo_Server'},
                           exclude_packages=['pkg3', 'pkg4.x86_64'],
                           fulltree_excludes=fulltree, package_whitelist=set())

    @mock.patch('pungi.phases.gather.get_lookaside_repos')
    @mock.patch('pungi.phases.gather.methods.method_deps.PungiWrapper')
    def test_with_lookaside(self, PungiWrapper, glr):
        glr.return_value = ['http://example.com/repo']
        pkgs = [('pkg1', None)]
        deps.write_pungi_config(self.compose, 'x86_64', self.compose.variants['Server'],
                                pkgs, [], [], [], [])
        self.assertWritten(PungiWrapper, packages=['pkg1'],
                           ks_path=self.topdir + '/work/x86_64/pungi/Server.x86_64.conf',
                           lookaside_repos={'lookaside-repo-0': 'http://example.com/repo'},
                           multilib_whitelist=[], multilib_blacklist=[],
                           groups=[], prepopulate=None,
                           repos={'pungi-repo': self.topdir + '/work/x86_64/repo',
                                  'comps-repo': self.topdir + '/work/x86_64/comps_repo_Server'},
                           exclude_packages=[], fulltree_excludes=None,
                           package_whitelist=set())
        self.assertEqual(glr.call_args_list,
                         [mock.call(self.compose, 'x86_64', self.compose.variants['Server'])])

    @mock.patch('pungi.phases.gather.methods.method_deps.PungiWrapper')
    def test_with_whitelist(self, PungiWrapper):
        pkgs = [('pkg1', None), ('pkg2', 'x86_64')]
        grps = ['grp1']
        filter = [('pkg3', None), ('pkg4', 'x86_64')]
        mock_rpm = mock.Mock(version='1.0.0', release='1', epoch=0)
        mock_rpm.name = 'pkg'
        self.compose.variants['Server'].pkgset.rpms_by_arch['x86_64'] = [mock_rpm]
        white = mock.Mock()
        black = mock.Mock()
        prepopulate = mock.Mock()
        fulltree = mock.Mock()
        deps.write_pungi_config(self.compose, 'x86_64', self.compose.variants['Server'],
                                pkgs, grps, filter, white, black,
                                prepopulate=prepopulate, fulltree_excludes=fulltree)
        self.assertWritten(PungiWrapper, packages=['pkg1', 'pkg2.x86_64'],
                           ks_path=self.topdir + '/work/x86_64/pungi/Server.x86_64.conf',
                           lookaside_repos={}, multilib_whitelist=white, multilib_blacklist=black,
                           groups=['grp1'], prepopulate=prepopulate,
                           repos={'pungi-repo': self.topdir + '/work/x86_64/repo',
                                  'comps-repo': self.topdir + '/work/x86_64/comps_repo_Server'},
                           exclude_packages=['pkg3', 'pkg4.x86_64'],
                           fulltree_excludes=fulltree,
                           package_whitelist=set(['pkg-0:1.0.0-1']))

    @mock.patch('pungi.phases.gather.methods.method_deps.PungiWrapper')
    def test_without_input(self, PungiWrapper):
        with self.assertRaises(RuntimeError) as ctx:
            deps.write_pungi_config(self.compose, 'x86_64', self.compose.variants['Server'],
                                    [], [], [], [], [])
        self.assertEqual(
            str(ctx.exception),
            'No packages included in Server.x86_64 (no comps groups, no input packages, no prepopulate)')
        self.assertEqual(PungiWrapper.return_value.mock_calls, [])
