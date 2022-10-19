#!/usr/bin/env python2
# -*- coding: utf-8 -*-


try:
    import unittest2 as unittest
except ImportError:
    import unittest
import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.buildinstall import (BuildinstallPhase, BuildinstallThread, link_boot_iso,
                                       BOOT_CONFIGS, tweak_configs)
from tests.helpers import DummyCompose, PungiTestCase, touch


class BuildInstallCompose(DummyCompose):
    def __init__(self, *args, **kwargs):
        super(BuildInstallCompose, self).__init__(*args, **kwargs)
        self.variants = {
            'Server': mock.Mock(uid='Server', arches=['x86_64', 'amd64'],
                                type='variant', buildinstallpackages=['bash', 'vim'],
                                is_empty=False),
            'Client': mock.Mock(uid='Client', arches=['amd64'],
                                type='variant', buildinstallpackages=[],
                                is_empty=False),
        }
        self.all_variants = self.variants.copy()
        self.has_comps = True
        self.just_phases = []
        self.skip_phases = []


class TestBuildinstallPhase(PungiTestCase):

    def test_config_skip_unless_bootable(self):
        compose = BuildInstallCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []

        phase = BuildinstallPhase(compose)

        self.assertTrue(phase.skip())

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_skip_option(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'buildinstall_method': 'lorax',
            'buildinstall_skip': [
                ('^Server$', {
                    'amd64': True
                }),
                ('^Client$', {
                    '*': True,
                }),
            ]
        })

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        pool = poolCls.return_value
        self.assertEqual(1, len(pool.queue_put.mock_calls))

    def test_does_not_skip_on_bootable(self):
        compose = BuildInstallCompose(self.topdir, {'bootable': True})
        compose.just_phases = None
        compose.skip_phases = []

        phase = BuildinstallPhase(compose)

        self.assertFalse(phase.skip())

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_starts_threads_for_each_cmd_with_lorax(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax',
            'disc_types': {'dvd': 'DVD'},
        })

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        # Three items added for processing in total.
        # Server.x86_64, Client.amd64, Server.x86_64
        pool = poolCls.return_value
        self.assertEqual(3, len(pool.queue_put.mock_calls))
        self.assertItemsEqual(
            [call[0][0][3] for call in pool.queue_put.call_args_list],
            ['rm -rf %s/work/amd64/buildinstall/Client && lorax ...' % self.topdir,
             'rm -rf %s/work/amd64/buildinstall/Server && lorax ...' % self.topdir,
             'rm -rf %s/work/x86_64/buildinstall/Server && lorax ...' % self.topdir])

        # Obtained correct lorax commands.
        self.assertItemsEqual(
            loraxCls.return_value.get_lorax_cmd.mock_calls,
            [mock.call('Test', '1', '1',
                       [self.topdir + '/work/x86_64/repo',
                        self.topdir + '/work/x86_64/comps_repo_Server'],
                       self.topdir + '/work/x86_64/buildinstall/Server',
                       buildarch='x86_64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/x86_64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Server'],
                       self.topdir + '/work/amd64/buildinstall/Server',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Client'],
                       self.topdir + '/work/amd64/buildinstall/Client',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Client-logs')])
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'x86_64', variant=compose.variants['Server'], disc_type='DVD'),
             mock.call(compose, 'amd64', variant=compose.variants['Client'], disc_type='DVD'),
             mock.call(compose, 'amd64', variant=compose.variants['Server'], disc_type='DVD')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_lorax_skips_empty_variants(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax'
        })

        get_volid.return_value = 'vol_id'
        compose.variants['Server'].is_empty = True
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        pool = poolCls.return_value
        self.assertEqual(1, len(pool.queue_put.mock_calls))
        self.assertItemsEqual(
            [call[0][0][3] for call in pool.queue_put.call_args_list],
            ['rm -rf %s/work/amd64/buildinstall/Client && lorax ...' % self.topdir])

        # Obtained correct lorax command.
        lorax = loraxCls.return_value
        lorax.get_lorax_cmd.assert_has_calls(
            [mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Client'],
                       self.topdir + '/work/amd64/buildinstall/Client',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Client-logs')],
            any_order=True)
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'amd64', variant=compose.variants['Client'], disc_type='dvd')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_starts_threads_for_each_cmd_with_buildinstall(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'buildinstall',
            'disc_types': {'dvd': 'DVD'},
        })

        get_volid.return_value = 'vol_id'

        phase = BuildinstallPhase(compose)

        phase.run()

        # Two items added for processing in total.
        pool = poolCls.return_value
        self.assertEqual(2, len(pool.queue_put.mock_calls))

        # Obtained correct lorax commands.
        self.assertItemsEqual(
            loraxCls.return_value.get_buildinstall_cmd.mock_calls,
            [mock.call('Test', '1', '1', self.topdir + '/work/x86_64/repo',
                       self.topdir + '/work/x86_64/buildinstall',
                       buildarch='x86_64', is_final=True, volid='vol_id'),
             mock.call('Test', '1', '1', self.topdir + '/work/amd64/repo',
                       self.topdir + '/work/amd64/buildinstall',
                       buildarch='amd64', is_final=True, volid='vol_id')])
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'x86_64', disc_type='DVD'),
             mock.call(compose, 'amd64', disc_type='DVD')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_uses_lorax_options(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax',
            'lorax_options': [
                ('^.*$', {'*': {}}),
                ('^Server$', {
                    'x86_64': {
                        'bugurl': 'http://example.com',
                        'add_template': ['foo', 'FOO'],
                        'add_arch_template': ['bar'],
                        'add_template_var': ['baz=1'],
                        'add_arch_template_var': ['quux=2'],
                        "rootfs_size": 3,
                        "version": "1.2.3",
                    },
                    'amd64': {'noupgrade': False}
                }),
                ('^Client$', {
                    '*': {'nomacboot': False}
                }),
                ('^.*$', {'*': {}}),
            ]
        })

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        # Three items added for processing in total.
        # Server.x86_64, Client.amd64, Server.x86_64
        pool = poolCls.return_value
        self.assertEqual(3, len(pool.queue_put.mock_calls))
        self.assertItemsEqual(
            [call[0][0][3] for call in pool.queue_put.call_args_list],
            ['rm -rf %s/work/amd64/buildinstall/Client && lorax ...' % self.topdir,
             'rm -rf %s/work/amd64/buildinstall/Server && lorax ...' % self.topdir,
             'rm -rf %s/work/x86_64/buildinstall/Server && lorax ...' % self.topdir])

        # Obtained correct lorax commands.
        self.assertItemsEqual(
            loraxCls.return_value.get_lorax_cmd.mock_calls,
            [mock.call('Test', '1.2.3', '1.2.3',
                       [self.topdir + '/work/x86_64/repo',
                        self.topdir + '/work/x86_64/comps_repo_Server'],
                       self.topdir + '/work/x86_64/buildinstall/Server',
                       buildarch='x86_64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       add_template=['foo', 'FOO'], add_arch_template=['bar'],
                       add_template_var=['baz=1'], add_arch_template_var=['quux=2'],
                       bugurl='http://example.com',
                       rootfs_size=3,
                       log_dir=self.topdir + '/logs/x86_64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Server'],
                       self.topdir + '/work/amd64/buildinstall/Server',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=False,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Client'],
                       self.topdir + '/work/amd64/buildinstall/Client',
                       buildarch='amd64', is_final=True, nomacboot=False, noupgrade=True,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Client-logs')])
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'x86_64', variant=compose.variants['Server'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Client'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Server'], disc_type='dvd')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_multiple_lorax_options(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax',
            'lorax_options': [
                ('^.*$', {
                    'x86_64': {'nomacboot': False},
                    '*': {'noupgrade': False}
                }),
            ]
        })

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        # Three items added for processing in total.
        # Server.x86_64, Client.amd64, Server.x86_64
        pool = poolCls.return_value
        self.assertEqual(3, len(pool.queue_put.mock_calls))
        self.assertItemsEqual(
            [call[0][0][3] for call in pool.queue_put.call_args_list],
            ['rm -rf %s/work/amd64/buildinstall/Client && lorax ...' % self.topdir,
             'rm -rf %s/work/amd64/buildinstall/Server && lorax ...' % self.topdir,
             'rm -rf %s/work/x86_64/buildinstall/Server && lorax ...' % self.topdir])

        # Obtained correct lorax commands.
        self.assertItemsEqual(
            loraxCls.return_value.get_lorax_cmd.mock_calls,
            [mock.call('Test', '1', '1',
                       [self.topdir + '/work/x86_64/repo',
                        self.topdir + '/work/x86_64/comps_repo_Server'],
                       self.topdir + '/work/x86_64/buildinstall/Server',
                       buildarch='x86_64', is_final=True, nomacboot=False, noupgrade=False,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/x86_64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Server'],
                       self.topdir + '/work/amd64/buildinstall/Server',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=False,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Client'],
                       self.topdir + '/work/amd64/buildinstall/Client',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=False,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Client-logs')])
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'x86_64', variant=compose.variants['Server'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Client'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Server'], disc_type='dvd')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_uses_lorax_options_buildinstall_topdir(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax',
            'buildinstall_topdir': '/buildinstall_topdir',
            'translate_paths': [(self.topdir, "http://localhost/")],
        })

        buildinstall_topdir = os.path.join(
            "/buildinstall_topdir", "buildinstall-" + os.path.basename(self.topdir))
        self.maxDiff = None

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        # Three items added for processing in total.
        # Server.x86_64, Client.amd64, Server.x86_64
        pool = poolCls.return_value
        self.assertEqual(3, len(pool.queue_put.mock_calls))
        self.assertItemsEqual(
            [call[0][0][3] for call in pool.queue_put.call_args_list],
            ['rm -rf %s/amd64/Client && lorax ...' % buildinstall_topdir,
             'rm -rf %s/amd64/Server && lorax ...' % buildinstall_topdir,
             'rm -rf %s/x86_64/Server && lorax ...' % buildinstall_topdir])

        # Obtained correct lorax commands.
        self.assertItemsEqual(
            loraxCls.return_value.get_lorax_cmd.mock_calls,
            [mock.call('Test', '1', '1',
                       ['http://localhost/work/x86_64/repo',
                        'http://localhost/work/x86_64/comps_repo_Server'],
                       buildinstall_topdir + '/x86_64/Server/results',
                       buildarch='x86_64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       bugurl=None,
                       rootfs_size=None,
                       log_dir=buildinstall_topdir + '/x86_64/Server/logs'),
             mock.call('Test', '1', '1',
                       ['http://localhost/work/amd64/repo',
                        'http://localhost/work/amd64/comps_repo_Server'],
                       buildinstall_topdir + '/amd64/Server/results',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=buildinstall_topdir + '/amd64/Server/logs'),
             mock.call('Test', '1', '1',
                       ['http://localhost/work/amd64/repo',
                        'http://localhost/work/amd64/comps_repo_Client'],
                       buildinstall_topdir + '/amd64/Client/results',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=buildinstall_topdir + '/amd64/Client/logs')])
        self.assertItemsEqual(
            get_volid.mock_calls,
            [mock.call(compose, 'x86_64', variant=compose.variants['Server'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Client'], disc_type='dvd'),
             mock.call(compose, 'amd64', variant=compose.variants['Server'], disc_type='dvd')])

    @mock.patch('pungi.phases.buildinstall.ThreadPool')
    @mock.patch('pungi.phases.buildinstall.LoraxWrapper')
    @mock.patch('pungi.phases.buildinstall.get_volid')
    def test_uses_lorax_extra_repos(self, get_volid, loraxCls, poolCls):
        compose = BuildInstallCompose(self.topdir, {
            'bootable': True,
            'release_name': 'Test',
            'release_short': 't',
            'release_version': '1',
            'buildinstall_method': 'lorax',
            'lorax_extra_sources': [
                ('^Server$', {
                    'x86_64': "http://example.com/repo1",
                }),
                ('^Client$', {
                    '*': ["http://example.com/repo2", "http://example.com/repo3"],
                }),
            ]
        })

        get_volid.return_value = 'vol_id'
        loraxCls.return_value.get_lorax_cmd.return_value = ['lorax', '...']

        phase = BuildinstallPhase(compose)

        phase.run()

        self.maxDiff = None
        self.assertItemsEqual(
            loraxCls.return_value.get_lorax_cmd.mock_calls,
            [mock.call('Test', '1', '1',
                       [self.topdir + '/work/x86_64/repo',
                        "http://example.com/repo1",
                        self.topdir + '/work/x86_64/comps_repo_Server'],
                       self.topdir + '/work/x86_64/buildinstall/Server',
                       buildarch='x86_64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       bugurl=None,
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/x86_64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        self.topdir + '/work/amd64/comps_repo_Server'],
                       self.topdir + '/work/amd64/buildinstall/Server',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Server', buildinstallpackages=['bash', 'vim'],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Server-logs'),
             mock.call('Test', '1', '1',
                       [self.topdir + '/work/amd64/repo',
                        "http://example.com/repo2",
                        "http://example.com/repo3",
                        self.topdir + '/work/amd64/comps_repo_Client'],
                       self.topdir + '/work/amd64/buildinstall/Client',
                       buildarch='amd64', is_final=True, nomacboot=True, noupgrade=True,
                       volid='vol_id', variant='Client', buildinstallpackages=[],
                       bugurl=None,
                       add_template=[], add_arch_template=[],
                       add_template_var=[], add_arch_template_var=[],
                       rootfs_size=None,
                       log_dir=self.topdir + '/logs/amd64/buildinstall-Client-logs')])


@mock.patch(
    'pungi.phases.buildinstall.get_volid', new=lambda *args, **kwargs: "dummy-volid"
)
class BuildinstallThreadTestCase(PungiTestCase):

    def setUp(self):
        super(BuildinstallThreadTestCase, self).setUp()
        self.pool = mock.Mock(finished_tasks=set())
        self.cmd = mock.Mock()

    @mock.patch('pungi.phases.buildinstall.link_boot_iso')
    @mock.patch('pungi.phases.buildinstall.tweak_buildinstall')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_buildinstall_thread_with_lorax_in_runroot(
        self, run, get_buildroot_rpms, KojiWrapperMock, mock_tweak, mock_link
    ):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'lorax',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
            'runroot_weights': {'buildinstall': 123},
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        get_runroot_cmd = KojiWrapperMock.return_value.get_runroot_cmd

        run_runroot_cmd = KojiWrapperMock.return_value.run_runroot_cmd
        run_runroot_cmd.return_value = {
            'output': 'Foo bar baz',
            'retcode': 0,
            'task_id': 1234,
        }

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, 'x86_64', compose.variants['Server'], self.cmd), 0)

        destdir = os.path.join(self.topdir, "work/x86_64/buildinstall/Server")
        self.assertItemsEqual(
            get_runroot_cmd.mock_calls,
            [mock.call(
                'rrt', 'x86_64', self.cmd, channel=None,
                use_shell=True, task_id=True,
                packages=['lorax'], mounts=[self.topdir], weight=123,
                chown_paths=[
                    destdir,
                    os.path.join(self.topdir, "logs/x86_64/buildinstall-Server-logs"),
                ],
            )])
        self.assertItemsEqual(
            run_runroot_cmd.mock_calls,
            [mock.call(get_runroot_cmd.return_value,
                       log_file=self.topdir + '/logs/x86_64/buildinstall-Server.x86_64.log')])
        with open(self.topdir + '/logs/x86_64/buildinstall-Server-RPMs.x86_64.log') as f:
            rpms = f.read().strip().split('\n')
        self.assertItemsEqual(rpms, ['bash', 'zsh'])
        self.assertItemsEqual(self.pool.finished_tasks, [('Server', 'x86_64')])

        self.assertEqual(
            mock_tweak.call_args_list,
            [
                mock.call(
                    compose,
                    destdir,
                    os.path.join(self.topdir, "compose/Server/x86_64/os"),
                    "x86_64",
                    "Server",
                    "",
                    "dummy-volid",
                    self.pool.kickstart_file,
                )
            ],
        )
        self.assertEqual(
            mock_link.call_args_list,
            [mock.call(compose, "x86_64", compose.variants["Server"], False)],
        )

    @mock.patch('pungi.phases.buildinstall.link_boot_iso')
    @mock.patch('pungi.phases.buildinstall.tweak_buildinstall')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_buildinstall_thread_with_buildinstall_in_runroot(
        self, run, get_buildroot_rpms, KojiWrapperMock, mock_tweak, mock_link
    ):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'buildinstall',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        get_runroot_cmd = KojiWrapperMock.return_value.get_runroot_cmd

        run_runroot_cmd = KojiWrapperMock.return_value.run_runroot_cmd
        run_runroot_cmd.return_value = {
            'output': 'Foo bar baz',
            'retcode': 0,
            'task_id': 1234,
        }

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, "amd64", None, self.cmd), 0)

        destdir = os.path.join(self.topdir, "work/amd64/buildinstall")
        self.assertItemsEqual(
            get_runroot_cmd.mock_calls,
            [mock.call(
                "rrt", "amd64", self.cmd, channel=None,
                use_shell=True, task_id=True,
                packages=['anaconda'], mounts=[self.topdir], weight=None,
                chown_paths=[destdir],
            )])
        self.assertItemsEqual(
            run_runroot_cmd.mock_calls,
            [mock.call(get_runroot_cmd.return_value,
                       log_file=self.topdir + "/logs/amd64/buildinstall.amd64.log")])
        with open(self.topdir + "/logs/amd64/buildinstall-RPMs.amd64.log") as f:
            rpms = f.read().strip().split('\n')
        self.assertItemsEqual(rpms, ['bash', 'zsh'])
        self.assertItemsEqual(self.pool.finished_tasks, [(None, 'amd64')])
        self.assertItemsEqual(
            mock_tweak.call_args_list,
            [
                mock.call(
                    compose,
                    destdir,
                    os.path.join(self.topdir, "compose", var, "amd64/os"),
                    "amd64",
                    var,
                    "",
                    "dummy-volid",
                    self.pool.kickstart_file,
                )
                for var in ["Client", "Server"]
            ],
        )
        self.assertItemsEqual(
            mock_link.call_args_list,
            [
                mock.call(compose, "amd64", compose.variants["Client"], False),
                mock.call(compose, "amd64", compose.variants["Server"], False),
            ],
        )

    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_buildinstall_fail_exit_code(self, run, get_buildroot_rpms, KojiWrapperMock):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'buildinstall',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.+$', {'*': ['buildinstall']})
            ],
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        run_runroot_cmd = KojiWrapperMock.return_value.run_runroot_cmd
        run_runroot_cmd.return_value = {
            'output': 'Foo bar baz',
            'retcode': 1,
            'task_id': 1234,
        }

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, 'x86_64', None, self.cmd), 0)

        compose._logger.error.assert_has_calls([
            mock.call('[FAIL] Buildinstall (variant None, arch x86_64) failed, but going on anyway.'),
            mock.call('Runroot task failed: 1234. See %s/logs/x86_64/buildinstall.x86_64.log for more details.'
                      % self.topdir)
        ])
        self.assertItemsEqual(self.pool.finished_tasks, [])

    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_lorax_fail_exit_code(self, run, get_buildroot_rpms, KojiWrapperMock):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'lorax',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.+$', {'*': ['buildinstall']})
            ],
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        run_runroot_cmd = KojiWrapperMock.return_value.run_runroot_cmd
        run_runroot_cmd.return_value = {
            'output': 'Foo bar baz',
            'retcode': 1,
            'task_id': 1234,
        }

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, 'x86_64', compose.variants['Server'], self.cmd), 0)

        compose._logger.error.assert_has_calls([
            mock.call('[FAIL] Buildinstall (variant Server, arch x86_64) failed, but going on anyway.'),
            mock.call('Runroot task failed: 1234. See %s/logs/x86_64/buildinstall-Server.x86_64.log for more details.' % self.topdir)
        ])
        self.assertItemsEqual(self.pool.finished_tasks, [])

    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_skips_on_existing_output_dir(self, run, get_buildroot_rpms, KojiWrapperMock):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'lorax',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.+$', {'*': ['buildinstall']})
            ],
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        dummy_file = os.path.join(self.topdir, 'work/x86_64/buildinstall/Server/dummy')
        touch(os.path.join(dummy_file))

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, 'x86_64', compose.variants['Server'], self.cmd), 0)

        self.assertEqual(0, len(run.mock_calls))

        self.assertTrue(os.path.exists(dummy_file))
        self.assertItemsEqual(self.pool.finished_tasks, [])

    @mock.patch('pungi.phases.buildinstall.link_boot_iso')
    @mock.patch('pungi.phases.buildinstall.tweak_buildinstall')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    @mock.patch('pungi.wrappers.kojiwrapper.get_buildroot_rpms')
    @mock.patch('pungi.phases.buildinstall.run')
    @mock.patch('pungi.phases.buildinstall.copy_all')
    def test_buildinstall_thread_with_lorax_custom_buildinstall_topdir(
            self, copy_all, run, get_buildroot_rpms, KojiWrapperMock, mock_tweak, mock_link
    ):
        compose = BuildInstallCompose(self.topdir, {
            'buildinstall_method': 'lorax',
            'runroot_tag': 'rrt',
            'koji_profile': 'koji',
            'runroot_weights': {'buildinstall': 123},
            'buildinstall_topdir': '/buildinstall_topdir',
        })

        get_buildroot_rpms.return_value = ['bash', 'zsh']

        get_runroot_cmd = KojiWrapperMock.return_value.get_runroot_cmd

        run_runroot_cmd = KojiWrapperMock.return_value.run_runroot_cmd
        run_runroot_cmd.return_value = {
            'output': 'Foo bar baz',
            'retcode': 0,
            'task_id': 1234,
        }

        t = BuildinstallThread(self.pool)

        with mock.patch('time.sleep'):
            t.process((compose, 'x86_64', compose.variants['Server'], self.cmd), 0)

        self.assertItemsEqual(
            get_runroot_cmd.mock_calls,
            [mock.call(
                'rrt', 'x86_64', self.cmd, channel=None,
                use_shell=True, task_id=True,
                packages=['lorax'], mounts=[self.topdir], weight=123,
                chown_paths=[
                    "/buildinstall_topdir/buildinstall-%s/x86_64/Server" % os.path.basename(self.topdir),
                    "/buildinstall_topdir/buildinstall-%s/x86_64/Server/logs" % os.path.basename(self.topdir),
                ],
            )])
        self.assertItemsEqual(
            run_runroot_cmd.mock_calls,
            [mock.call(get_runroot_cmd.return_value,
                       log_file=self.topdir + '/logs/x86_64/buildinstall-Server.x86_64.log')])
        with open(self.topdir + '/logs/x86_64/buildinstall-Server-RPMs.x86_64.log') as f:
            rpms = f.read().strip().split('\n')
        self.assertItemsEqual(rpms, ['bash', 'zsh'])
        self.assertItemsEqual(self.pool.finished_tasks, [('Server', 'x86_64')])

        buildinstall_topdir = os.path.join(
            "/buildinstall_topdir", "buildinstall-" + os.path.basename(self.topdir))
        self.assertItemsEqual(
            copy_all.mock_calls,
            [mock.call(os.path.join(buildinstall_topdir, 'x86_64/Server/results'),
                       os.path.join(self.topdir, 'work/x86_64/buildinstall/Server')),
             mock.call(os.path.join(buildinstall_topdir, 'x86_64/Server/logs'),
                       os.path.join(self.topdir, 'logs/x86_64/buildinstall-Server-logs'))]
        )

        self.assertEqual(
            mock_tweak.call_args_list,
            [
                mock.call(
                    compose,
                    os.path.join(self.topdir, "work/x86_64/buildinstall/Server"),
                    os.path.join(self.topdir, "compose/Server/x86_64/os"),
                    "x86_64",
                    "Server",
                    "",
                    "dummy-volid",
                    self.pool.kickstart_file,
                )
            ],
        )
        self.assertEqual(
            mock_link.call_args_list,
            [mock.call(compose, "x86_64", compose.variants["Server"], False)],
        )


class TestSymlinkIso(PungiTestCase):

    def setUp(self):
        super(TestSymlinkIso, self).setUp()
        self.compose = BuildInstallCompose(self.topdir, {})
        os_tree = self.compose.paths.compose.os_tree('x86_64', self.compose.variants['Server'])
        self.boot_iso_path = os.path.join(os_tree, "images", "boot.iso")
        touch(self.boot_iso_path)

    @mock.patch('pungi.phases.buildinstall.Image')
    @mock.patch('pungi.phases.buildinstall.get_mtime')
    @mock.patch('pungi.phases.buildinstall.get_file_size')
    @mock.patch('pungi.phases.buildinstall.iso')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_hardlink(self, run, iso, get_file_size, get_mtime, ImageCls):
        self.compose.conf = {'buildinstall_symlink': False, 'disc_types': {}}
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        link_boot_iso(self.compose, 'x86_64', self.compose.variants['Server'], False)

        tgt = self.topdir + '/compose/Server/x86_64/iso/image-name'
        self.assertTrue(os.path.isfile(tgt))
        self.assertEqual(os.stat(tgt).st_ino,
                         os.stat(self.topdir + '/compose/Server/x86_64/os/images/boot.iso').st_ino)

        self.assertItemsEqual(
            self.compose.get_image_name.mock_calls,
            [mock.call('x86_64', self.compose.variants['Server'],
                       disc_type='boot', disc_num=None, suffix='.iso')])
        self.assertItemsEqual(iso.get_implanted_md5.mock_calls,
                              [mock.call(tgt)])
        self.assertItemsEqual(iso.get_manifest_cmd.mock_calls,
                              [mock.call('image-name')])
        self.assertItemsEqual(iso.get_volume_id.mock_calls,
                              [mock.call(tgt)])
        self.assertItemsEqual(run.mock_calls,
                              [mock.call(iso.get_manifest_cmd.return_value,
                                         workdir=self.topdir + '/compose/Server/x86_64/iso')])

        image = ImageCls.return_value
        self.assertEqual(image.path, 'Server/x86_64/iso/image-name')
        self.assertEqual(image.mtime, 13579)
        self.assertEqual(image.size, 1024)
        self.assertEqual(image.arch, 'x86_64')
        self.assertEqual(image.type, "boot")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.disc_number, 1)
        self.assertEqual(image.disc_count, 1)
        self.assertEqual(image.bootable, True)
        self.assertEqual(image.implant_md5, iso.get_implanted_md5.return_value)
        self.assertEqual(image.can_fail, False)
        self.assertEqual(self.compose.im.add.mock_calls,
                         [mock.call('Server', 'x86_64', image)])

    @mock.patch('pungi.phases.buildinstall.Image')
    @mock.patch('pungi.phases.buildinstall.get_mtime')
    @mock.patch('pungi.phases.buildinstall.get_file_size')
    @mock.patch('pungi.phases.buildinstall.iso')
    @mock.patch('pungi.phases.buildinstall.run')
    def test_hardlink_with_custom_type(self, run, iso, get_file_size, get_mtime, ImageCls):
        self.compose.conf = {
            'buildinstall_symlink': False,
            'disc_types': {'boot': 'netinst'},
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        link_boot_iso(self.compose, 'x86_64', self.compose.variants['Server'], True)

        tgt = self.topdir + '/compose/Server/x86_64/iso/image-name'
        self.assertTrue(os.path.isfile(tgt))
        self.assertEqual(os.stat(tgt).st_ino,
                         os.stat(self.topdir + '/compose/Server/x86_64/os/images/boot.iso').st_ino)

        self.assertItemsEqual(
            self.compose.get_image_name.mock_calls,
            [mock.call('x86_64', self.compose.variants['Server'],
                       disc_type='netinst', disc_num=None, suffix='.iso')])
        self.assertItemsEqual(iso.get_implanted_md5.mock_calls,
                              [mock.call(tgt)])
        self.assertItemsEqual(iso.get_manifest_cmd.mock_calls,
                              [mock.call('image-name')])
        self.assertItemsEqual(iso.get_volume_id.mock_calls,
                              [mock.call(tgt)])
        self.assertItemsEqual(run.mock_calls,
                              [mock.call(iso.get_manifest_cmd.return_value,
                                         workdir=self.topdir + '/compose/Server/x86_64/iso')])

        image = ImageCls.return_value
        self.assertEqual(image.path, 'Server/x86_64/iso/image-name')
        self.assertEqual(image.mtime, 13579)
        self.assertEqual(image.size, 1024)
        self.assertEqual(image.arch, 'x86_64')
        self.assertEqual(image.type, "boot")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.disc_number, 1)
        self.assertEqual(image.disc_count, 1)
        self.assertEqual(image.bootable, True)
        self.assertEqual(image.implant_md5, iso.get_implanted_md5.return_value)
        self.assertEqual(image.can_fail, True)
        self.assertEqual(self.compose.im.add.mock_calls,
                         [mock.call('Server', 'x86_64', image)])


class TestTweakConfigs(PungiTestCase):

    def test_tweak_configs(self):
        configs = []
        for cfg in BOOT_CONFIGS:
            if 'yaboot' not in cfg:
                configs.append(os.path.join(self.topdir, cfg))
                touch(configs[-1], ':LABEL=baz')
        tweak_configs(self.topdir, 'new volid', os.path.join(self.topdir, 'ks.cfg'))
        for cfg in configs:
            with open(cfg) as f:
                self.assertEqual(
                    f.read().strip(),
                    ':LABEL=new\\x20volid ks=hd:LABEL=new\\x20volid:/ks.cfg')

    def test_tweak_configs_yaboot(self):
        configs = []
        for cfg in BOOT_CONFIGS:
            if 'yaboot' in cfg:
                configs.append(os.path.join(self.topdir, cfg))
                touch(configs[-1], ':LABEL=baz')
        tweak_configs(self.topdir, 'new volid', os.path.join(self.topdir, 'ks.cfg'))
        for cfg in configs:
            with open(os.path.join(self.topdir, cfg)) as f:
                self.assertEqual(
                    f.read().strip(),
                    ':LABEL=new\\\\x20volid ks=hd:LABEL=new\\\\x20volid:/ks.cfg')


if __name__ == "__main__":
    unittest.main()
