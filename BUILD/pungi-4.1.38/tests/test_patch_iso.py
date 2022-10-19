# -*- coding: utf-8 -*-

import mock
import os
import sys
try:
    import unittest2 as unittest
except ImportError:
    import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.helpers import boom, touch, copy_fixture
from pungi_utils import patch_iso


class TestUnifiedIsos(unittest.TestCase):
    pass


class TestGetLoraxDir(unittest.TestCase):
    @mock.patch('kobo.shortcuts.run')
    def test_success(self, mock_run):
        mock_run.return_value = (0, 'hello')
        self.assertEqual(patch_iso.get_lorax_dir(None), 'hello')
        self.assertEqual(1, len(mock_run.call_args_list))

    @mock.patch('kobo.shortcuts.run')
    def test_crash(self, mock_run):
        mock_run.side_effect = boom
        self.assertEqual(patch_iso.get_lorax_dir('hello'), 'hello')
        self.assertEqual(1, len(mock_run.call_args_list))


class TestSh(unittest.TestCase):
    @mock.patch('kobo.shortcuts.run')
    def test_cmd(self, mock_run):
        mock_run.return_value = (0, 'ok')
        log = mock.Mock()
        patch_iso.sh(log, ['ls'], foo='bar')
        self.assertEqual(mock_run.call_args_list,
                         [mock.call(['ls'], foo='bar', universal_newlines=True)])
        self.assertEqual(log.info.call_args_list,
                         [mock.call('Running: %s', 'ls')])
        self.assertEqual(log.debug.call_args_list,
                         [mock.call('%s', 'ok')])


class TestAsBool(unittest.TestCase):
    def test_true(self):
        self.assertTrue(patch_iso.as_bool('true'))

    def test_false(self):
        self.assertFalse(patch_iso.as_bool('false'))

    def test_anything_else(self):
        obj = mock.Mock()
        self.assertIs(patch_iso.as_bool(obj), obj)


class EqualsAny(object):
    def __eq__(self, another):
        return True

    def __repr__(self):
        return u'ANYTHING'


ANYTHING = EqualsAny()


class TestPatchingIso(unittest.TestCase):

    @mock.patch('pungi_utils.patch_iso.util.copy_all')
    @mock.patch('pungi_utils.patch_iso.iso')
    @mock.patch('pungi_utils.patch_iso.sh')
    def test_whole(self, sh, iso, copy_all):
        iso.mount.return_value.__enter__.return_value = 'mounted-iso-dir'

        def _create_files(src, dest):
            touch(os.path.join(dest, 'dir', 'file.txt'), 'Hello')

        copy_all.side_effect = _create_files

        log = mock.Mock(name='logger')
        opts = mock.Mock(
            target='test.iso',
            source='source.iso',
            force_arch=None,
            volume_id='FOOBAR',
            dirs=[]
        )
        patch_iso.run(log, opts)

        self.assertEqual(iso.get_mkisofs_cmd.call_args_list,
                         [mock.call(os.path.abspath(opts.target), None,
                                    boot_args=None,
                                    exclude=['./lost+found'],
                                    graft_points=ANYTHING,
                                    input_charset=None,
                                    volid='FOOBAR')])
        self.assertEqual(iso.mount.call_args_list,
                         [mock.call('source.iso')])
        self.assertEqual(copy_all.mock_calls,
                         [mock.call('mounted-iso-dir', ANYTHING)])
        self.assertEqual(
            sh.call_args_list,
            [mock.call(log, iso.get_mkisofs_cmd.return_value, workdir=ANYTHING),
             mock.call(log, iso.get_implantisomd5_cmd.return_value)])

    @mock.patch('pungi_utils.patch_iso.util.copy_all')
    @mock.patch('pungi_utils.patch_iso.iso')
    @mock.patch('pungi_utils.patch_iso.sh')
    def test_detect_arch_discinfo(self, sh, iso, copy_all):
        iso.mount.return_value.__enter__.return_value = 'mounted-iso-dir'

        def _create_files(src, dest):
            touch(os.path.join(dest, 'dir', 'file.txt'), 'Hello')
            touch(os.path.join(dest, '.discinfo'),
                  '1487578537.111417\nDummy Product 1.0\nppc64\n1')

        copy_all.side_effect = _create_files

        log = mock.Mock(name='logger')
        opts = mock.Mock(
            target='test.iso',
            source='source.iso',
            force_arch=None,
            volume_id=None,
            dirs=[]
        )
        patch_iso.run(log, opts)

        self.assertEqual(iso.mount.call_args_list,
                         [mock.call('source.iso')])
        self.assertEqual(iso.get_mkisofs_cmd.call_args_list,
                         [mock.call(os.path.abspath(opts.target), None,
                                    boot_args=iso.get_boot_options.return_value,
                                    exclude=['./lost+found'],
                                    graft_points=ANYTHING,
                                    input_charset=None,
                                    volid=iso.get_volume_id.return_value)])
        self.assertEqual(copy_all.mock_calls,
                         [mock.call('mounted-iso-dir', ANYTHING)])
        self.assertEqual(
            sh.call_args_list,
            [mock.call(log, iso.get_mkisofs_cmd.return_value, workdir=ANYTHING),
             mock.call(log, iso.get_implantisomd5_cmd.return_value)])

    @mock.patch('pungi_utils.patch_iso.util.copy_all')
    @mock.patch('pungi_utils.patch_iso.iso')
    @mock.patch('pungi_utils.patch_iso.sh')
    def test_run_isohybrid(self, sh, iso, copy_all):
        iso.mount.return_value.__enter__.return_value = 'mounted-iso-dir'

        def _create_files(src, dest):
            touch(os.path.join(dest, 'dir', 'file.txt'), 'Hello')
            copy_fixture(
                'DP-1.0-20161013.t.4/compose/Server/x86_64/os/.treeinfo',
                os.path.join(dest, '.treeinfo')
            )

        copy_all.side_effect = _create_files

        log = mock.Mock(name='logger')
        opts = mock.Mock(
            target='test.iso',
            source='source.iso',
            force_arch=None,
            volume_id=None,
            dirs=[]
        )
        patch_iso.run(log, opts)

        self.assertEqual(iso.mount.call_args_list,
                         [mock.call('source.iso')])
        self.assertEqual(iso.get_mkisofs_cmd.call_args_list,
                         [mock.call(os.path.abspath(opts.target), None,
                                    boot_args=iso.get_boot_options.return_value,
                                    exclude=['./lost+found'],
                                    graft_points=ANYTHING,
                                    input_charset='utf-8',
                                    volid=iso.get_volume_id.return_value)])
        self.assertEqual(copy_all.mock_calls,
                         [mock.call('mounted-iso-dir', ANYTHING)])
        self.assertEqual(
            sh.call_args_list,
            [mock.call(log, iso.get_mkisofs_cmd.return_value, workdir=ANYTHING),
             mock.call(log, iso.get_isohybrid_cmd.return_value),
             mock.call(log, iso.get_implantisomd5_cmd.return_value)])

    @mock.patch('pungi_utils.patch_iso.tweak_configs')
    @mock.patch('pungi_utils.patch_iso.util.copy_all')
    @mock.patch('pungi_utils.patch_iso.iso')
    @mock.patch('pungi_utils.patch_iso.sh')
    def test_add_ks_cfg(self, sh, iso, copy_all, tweak_configs):
        iso.mount.return_value.__enter__.return_value = 'mounted-iso-dir'
        iso.get_graft_points.return_value = {
            'ks.cfg': 'path/to/ks.cfg',
        }

        def _create_files(src, dest):
            touch(os.path.join(dest, 'dir', 'file.txt'), 'Hello')

        copy_all.side_effect = _create_files

        log = mock.Mock(name='logger')
        opts = mock.Mock(
            target='test.iso',
            source='source.iso',
            force_arch='s390',
            volume_id='foobar',
            dirs=[],
        )
        patch_iso.run(log, opts)

        self.assertEqual(iso.mount.call_args_list,
                         [mock.call('source.iso')])
        self.assertEqual(iso.get_mkisofs_cmd.call_args_list,
                         [mock.call(os.path.abspath(opts.target), None,
                                    boot_args=iso.get_boot_options.return_value,
                                    exclude=['./lost+found'],
                                    graft_points=ANYTHING,
                                    input_charset='utf-8',
                                    volid='foobar')])
        self.assertEqual(tweak_configs.call_args_list,
                         [mock.call(ANYTHING, 'foobar', 'path/to/ks.cfg')])
        self.assertEqual(copy_all.mock_calls,
                         [mock.call('mounted-iso-dir', ANYTHING)])
        self.assertEqual(
            sh.call_args_list,
            [mock.call(log, iso.get_mkisofs_cmd.return_value, workdir=ANYTHING),
             mock.call(log, iso.get_implantisomd5_cmd.return_value)])
