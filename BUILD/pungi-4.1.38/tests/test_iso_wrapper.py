# -*- coding: utf-8 -*-

import itertools
import mock
import os
import sys
try:
    import unittest2 as unittest
except ImportError:
    import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.wrappers import iso

CORRECT_OUTPUT = '''dummy.iso:   31ff3e405e26ad01c63b62f6b11d30f6
Fragment sums: 6eb92e7bda221d7fe5f19b4d21468c9bf261d84c96d145d96c76444b9cbc
Fragment count: 20
Supported ISO: no
'''

INCORRECT_OUTPUT = '''This should never happen: File not found'''


class TestIsoUtils(unittest.TestCase):

    @mock.patch('pungi.wrappers.iso.run')
    def test_get_implanted_md5_correct(self, mock_run):
        mock_run.return_value = (0, CORRECT_OUTPUT)
        logger = mock.Mock()
        self.assertEqual(iso.get_implanted_md5('dummy.iso', logger=logger),
                         '31ff3e405e26ad01c63b62f6b11d30f6')
        self.assertEqual(mock_run.call_args_list,
                         [mock.call(['/usr/bin/checkisomd5', '--md5sumonly', 'dummy.iso'],
                                    universal_newlines=True)])
        self.assertEqual(logger.mock_calls, [])

    @mock.patch('pungi.wrappers.iso.run')
    def test_get_implanted_md5_incorrect(self, mock_run):
        mock_run.return_value = (0, INCORRECT_OUTPUT)
        logger = mock.Mock()
        self.assertEqual(iso.get_implanted_md5('dummy.iso', logger=logger), None)
        self.assertEqual(mock_run.call_args_list,
                         [mock.call(['/usr/bin/checkisomd5', '--md5sumonly', 'dummy.iso'],
                                    universal_newlines=True)])
        self.assertTrue(len(logger.mock_calls) > 0)

    @mock.patch('pungi.util.run_unmount_cmd')
    @mock.patch('pungi.wrappers.iso.run')
    def test_mount_iso(self, mock_run, mock_unmount):
        # first tuple is return value for command 'which guestmount'
        # value determines type of the mount/unmount command ('1' - guestmount is not available)
        # for approach as a root, pair commands mount-umount are used
        mock_run.side_effect = [(1, ''), (0, '')]
        with iso.mount('dummy') as temp_dir:
            self.assertTrue(os.path.isdir(temp_dir))
        self.assertEqual(len(mock_run.call_args_list), 2)
        mount_call_str = str(mock_run.call_args_list[1])
        self.assertTrue(mount_call_str.startswith("call(['mount'"))
        self.assertEqual(len(mock_unmount.call_args_list), 1)
        unmount_call_str = str(mock_unmount.call_args_list[0])
        self.assertTrue(unmount_call_str.startswith("call(['umount'"))
        self.assertFalse(os.path.isdir(temp_dir))

    @mock.patch('pungi.util.run_unmount_cmd')
    @mock.patch('pungi.wrappers.iso.run')
    def test_guestmount(self, mock_run, mock_unmount):
        # first tuple is return value for command 'which guestmount'
        # value determines type of the mount/unmount command ('0' - guestmount is available)
        # for approach as a non-root, pair commands guestmount-fusermount are used
        mock_run.side_effect = [(0, ''), (0, '')]
        with iso.mount('dummy') as temp_dir:
            self.assertTrue(os.path.isdir(temp_dir))
        self.assertEqual(len(mock_run.call_args_list), 2)
        mount_call_str = str(mock_run.call_args_list[1])
        self.assertTrue(mount_call_str.startswith("call(['guestmount'"))
        self.assertEqual(len(mock_unmount.call_args_list), 1)
        unmount_call_str = str(mock_unmount.call_args_list[0])
        self.assertTrue(unmount_call_str.startswith("call(['fusermount'"))
        self.assertFalse(os.path.isdir(temp_dir))

    @mock.patch('pungi.util.run_unmount_cmd')
    @mock.patch('pungi.wrappers.iso.run')
    def test_mount_iso_always_unmounts(self, mock_run, mock_unmount):
        mock_run.side_effect = [(1, ''), (0, '')]
        try:
            with iso.mount('dummy') as temp_dir:
                self.assertTrue(os.path.isdir(temp_dir))
                raise RuntimeError()
        except RuntimeError:
            pass
        self.assertEqual(len(mock_run.call_args_list), 2)
        self.assertEqual(len(mock_unmount.call_args_list), 1)
        self.assertFalse(os.path.isdir(temp_dir))

    @mock.patch('pungi.util.run_unmount_cmd')
    @mock.patch('pungi.wrappers.iso.run')
    def test_mount_iso_raises_on_error(self, mock_run, mock_unmount):
        log = mock.Mock()
        mock_run.side_effect = [(1, ''), (1, 'Boom')]
        with self.assertRaises(RuntimeError):
            with iso.mount('dummy', logger=log) as temp_dir:
                self.assertTrue(os.path.isdir(temp_dir))
        self.assertEqual(len(mock_run.call_args_list), 2)
        self.assertEqual(len(mock_unmount.call_args_list), 0)
        self.assertEqual(len(log.mock_calls), 1)


class TestCmpGraftPoints(unittest.TestCase):
    def assertSorted(self, *args):
        """Tests that all permutations of arguments yield the same sorted results."""
        for perm in itertools.permutations(args):
            self.assertEqual(sorted(perm, key=iso.graft_point_sort_key),
                             list(args))

    def test_eq(self):
        self.assertSorted('pkgs/foo.rpm', 'pkgs/foo.rpm')

    def test_rpms_sorted_alphabetically(self):
        self.assertSorted('pkgs/bar.rpm', 'pkgs/foo.rpm')

    def test_images_sorted_alphabetically(self):
        self.assertSorted('aaa.img', 'images/foo', 'isolinux/foo')

    def test_other_files_sorted_alphabetically(self):
        self.assertSorted('bar.txt', 'foo.txt')

    def test_rpms_after_images(self):
        self.assertSorted('foo.ins', 'bar.rpm')

    def test_other_after_images(self):
        self.assertSorted('EFI/anything', 'zzz.txt')

    def test_rpm_after_other(self):
        self.assertSorted('bbb.txt', 'aaa.rpm')

    def test_all_kinds(self):
        self.assertSorted('etc/file', 'ppc/file', 'c.txt', 'd.txt', 'a.rpm', 'b.rpm')
