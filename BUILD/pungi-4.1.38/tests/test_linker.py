#!/usr/bin/env python
# -*- coding: utf-8 -*-


import mock
import errno
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import os
import stat
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi import linker
from tests import helpers


class TestLinkerBase(helpers.PungiTestCase):
    def setUp(self):
        super(TestLinkerBase, self).setUp()
        self.logger = mock.Mock()
        self.linker = linker.Linker(logger=self.logger)
        self.path_src = self.touch("file", "asdf")

    def touch(self, path, contents=None):
        path = os.path.join(self.topdir, path)
        helpers.touch(path, contents)
        return path

    def mkdir(self, path):
        path = os.path.join(self.topdir, path.lstrip("/"))
        try:
            os.makedirs(path)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise
        return path

    def same_inode(self, path1, path2):
        st1 = os.stat(path1)
        st2 = os.stat(path2)
        return (st1.st_dev, st1.st_ino) == (st2.st_dev, st2.st_ino)

    def same_content(self, path1, path2):
        if self.same_inode(path1, path2):
            return True
        data1 = open(path1, "r").read()
        data2 = open(path2, "r").read()
        return data1 == data2

    def same_stat(self, path1, path2):
        st1 = os.stat(path1)
        st2 = os.stat(path2)

        if not stat.S_ISDIR(st1.st_mode) and int(st1.st_mtime) != int(st2.st_mtime):
            return False
        if st1.st_size != st2.st_size:
            return False
        if st1.st_mode != st2.st_mode:
            return False
        return True

    def assertSameStat(self, a, b):
        self.assertTrue(self.same_stat(a, b))

    def assertSameFile(self, a, b):
        self.assertTrue(os.path.samefile(a, b))

    def assertDifferentFile(self, a, b):
        self.assertFalse(os.path.samefile(a, b))


class TestLinkerSymlink(TestLinkerBase):

    def test_symlink(self):
        path_dst = os.path.join(self.topdir, "symlink")

        # symlink 'symlink' -> 'file'
        self.linker.symlink(self.path_src, path_dst)
        self.assertTrue(os.path.islink(path_dst))
        self.assertEqual(os.readlink(path_dst), "file")
        self.assertSameFile(self.path_src, path_dst)

        # linking existing file must pass
        self.linker.symlink(self.path_src, path_dst)

        # linking existing file with different target must fail
        self.assertRaises(OSError, self.linker.symlink, self.path_src, path_dst, relative=False)

    def test_symlink_different_type(self):
        # try to symlink 'symlink' -> 'another-file' ('symlink' already exists
        # and points to 'file')
        path_dst = os.path.join(self.topdir, "symlink")
        os.symlink(self.path_src, path_dst)
        path_src = self.touch("another-file")
        self.assertRaises(OSError, self.linker.symlink, path_src, path_dst)

    def test_relative_symlink(self):
        # symlink bar -> ../a
        dir_dst = os.path.join(self.topdir, "foo")
        os.makedirs(dir_dst)
        path_dst = os.path.join(dir_dst, "bar")
        self.linker.symlink(self.path_src, path_dst)
        self.assertTrue(os.path.islink(path_dst))
        self.assertEqual(os.readlink(path_dst), "../file")
        self.assertSameFile(self.path_src, path_dst)

    def test_symlink_to_symlink(self):
        path_dst = os.path.join(self.topdir, "symlink")
        path_dst2 = os.path.join(self.topdir, "symlink-to-symlink")

        # symlink 'symlink' -> 'file'
        self.linker.symlink(self.path_src, path_dst, relative=True)
        self.linker.symlink(path_dst, path_dst2)


class TestLinkerHardlink(TestLinkerBase):

    def test_hardlink(self):
        path_dst = os.path.join(self.topdir, "hardlink")

        # hardlink 'file' to 'hardlink'
        self.linker.hardlink(self.path_src, path_dst)
        self.assertTrue(os.path.isfile(path_dst))
        self.assertSameFile(self.path_src, path_dst)

        # hardlink 'file' to 'foo/hardlink'
        dir_dst = os.path.join(self.topdir, "foo")
        os.makedirs(dir_dst)
        path_dst = os.path.join(dir_dst, "hardlink")
        self.linker.hardlink(self.path_src, path_dst)
        self.assertTrue(os.path.isfile(path_dst))
        self.assertSameFile(self.path_src, path_dst)

    def test_hardlink_different_type(self):
        # try to hardlink a file to existing dst with incompatible type
        path_dst = os.path.join(self.topdir, "symlink")
        os.symlink(self.path_src, path_dst)
        self.assertRaises(OSError, self.linker.hardlink, self.path_src, path_dst)


class TestLinkerCopy(TestLinkerBase):
    def test_copy(self):
        path_dst = os.path.join(self.topdir, "b")

        # copy 'file' to 'b'
        self.linker.copy(self.path_src, path_dst)
        self.assertTrue(os.path.isfile(path_dst))
        self.assertDifferentFile(self.path_src, path_dst)

    def test_copy_to_existing_file_with_different_content(self):
        path_dst = os.path.join(self.topdir, "b")
        helpers.touch(path_dst, 'xxx')
        self.assertRaises(Exception, self.linker.copy, self.path_src, path_dst)

    def test_copy_to_directory(self):
        dir_dst = os.path.join(self.topdir, "foo")
        os.makedirs(dir_dst)
        path_dst = os.path.join(dir_dst, "bar")
        self.linker.copy(self.path_src, path_dst)
        self.assertTrue(os.path.isfile(path_dst))
        self.assertDifferentFile(self.path_src, path_dst)

    def test_copy_different_type(self):
        # try to copy a file to existing dst with incompatible type
        path_dst = os.path.join(self.topdir, "symlink")
        os.symlink(self.path_src, path_dst)
        self.assertRaises(OSError, self.linker.copy, self.path_src, path_dst)


class TestLinkerLink(TestLinkerBase):
    def setUp(self):
        # This will create following structure as a source.
        #
        # + src/
        #   + file1
        #   + file2
        #   + symlink2      (-> 'subdir')
        #   + symlink3      (-> 'does-not-exist')
        #   + hardlink1     (same file as 'file1')
        #   + subdir/
        #     + file3
        #     + symlink1    (-> '../file1')
        #
        # The destination paths are are similar, but in dst/ top-level dir.
        super(TestLinkerLink, self).setUp()
        self.src_dir = self.mkdir("src")
        self.file1 = self.touch("src/file1", "file1")
        self.file2 = self.touch("src/file2", "file2")
        os.utime(self.file2, (-1, 2))
        self.file3 = self.touch("src/subdir/file3", "file3")
        os.utime(self.file3, (-1, 3))
        os.utime(os.path.dirname(self.file3), (-1, 31))
        self.symlink1 = os.path.join(self.topdir, "src/subdir/symlink1")
        os.symlink("../file1", self.symlink1)
        self.symlink2 = os.path.join(self.topdir, "src/symlink2")
        os.symlink("subdir", self.symlink2)
        self.symlink3 = os.path.join(self.topdir, "src/symlink3")
        os.symlink("does-not-exist", self.symlink3)
        self.hardlink1 = os.path.join(self.topdir, "src/hardlink1")
        os.link(self.file1, self.hardlink1)

        self.dst_dir = os.path.join(self.topdir, "dst")
        self.dst_file1 = os.path.join(self.dst_dir, "file1")
        self.dst_file2 = os.path.join(self.dst_dir, "file2")
        self.dst_file3 = os.path.join(self.dst_dir, "subdir", "file3")
        self.dst_symlink1 = os.path.join(self.dst_dir, "subdir", "symlink1")
        self.dst_symlink2 = os.path.join(self.dst_dir, "symlink2")
        self.dst_symlink3 = os.path.join(self.dst_dir, "symlink3")
        self.dst_hardlink1 = os.path.join(self.dst_dir, "hardlink1")

    def test_link_file(self):
        dst = os.path.join(self.topdir, "hardlink")
        self.linker.link(self.path_src, dst, link_type="hardlink")
        self.assertTrue(self.same_inode(self.path_src, dst))
        self.assertFalse(os.path.islink(dst))

    def test_symlink_file(self):
        dst = os.path.join(self.topdir, "symlink")
        self.linker.link(self.path_src, dst, link_type="symlink")
        self.assertEqual(os.readlink(dst), "file")
        self.assertTrue(os.path.islink(dst))

    def test_copy_file(self):
        dst = os.path.join(self.topdir, "copy")
        self.linker.link(self.path_src, dst, link_type="copy")
        self.assertFalse(os.path.islink(dst))
        self.assertFalse(self.same_inode(self.path_src, dst))
        self.assertTrue(self.same_content(self.path_src, dst))

    def test_hardlink_or_copy_file(self):
        dst = os.path.join(self.topdir, "hardlink-or-copy")
        self.linker.link(self.path_src, dst, link_type="hardlink-or-copy")
        self.assertTrue(self.same_inode(self.path_src, dst))
        self.assertFalse(os.path.islink(dst))

    def test_link_file_test_mode(self):
        self.linker = linker.Linker(logger=self.logger, test=True)

        dst = os.path.join(self.topdir, "hardlink")
        self.linker.link(self.path_src, dst, link_type="hardlink")
        self.assertFalse(os.path.isdir(self.dst_dir))
        self.assertEqual(len(self.logger.mock_calls), 1)

    def test_symlink_file_test_mode(self):
        self.linker = linker.Linker(logger=self.logger, test=True)
        dst = os.path.join(self.topdir, "symlink")
        self.linker.link(self.path_src, dst, link_type="symlink")
        self.assertFalse(os.path.isdir(self.dst_dir))
        self.assertEqual(len(self.logger.mock_calls), 1)

    def test_copy_file_test_mode(self):
        self.linker = linker.Linker(logger=self.logger, test=True)
        dst = os.path.join(self.topdir, "copy")
        self.linker.link(self.path_src, dst, link_type="copy")
        self.assertFalse(os.path.isdir(self.dst_dir))
        self.assertEqual(len(self.logger.mock_calls), 1)

    def test_hardlink_or_copy_file_test_mode(self):
        self.linker = linker.Linker(logger=self.logger, test=True)
        dst = os.path.join(self.topdir, "hardlink-or-copy")
        self.linker.link(self.path_src, dst, link_type="hardlink-or-copy")
        self.assertFalse(os.path.isdir(self.dst_dir))
        self.assertEqual(len(self.logger.mock_calls), 1)

    def test_link_file_to_existing_destination(self):
        self.assertRaises(OSError, self.linker.link,
                          self.file1, self.file2, link_type="hardlink")

    def test_symlink_file_to_existing_destination(self):
        self.assertRaises(OSError, self.linker.link,
                          self.file1, self.file2, link_type="symlink")

    def test_copy_file_to_existing_destination(self):
        self.assertRaises(OSError, self.linker.link,
                          self.file1, self.file2, link_type="copy")

    def test_hardlink_or_copy_file_to_existing_destination(self):
        self.assertRaises(OSError, self.linker.link,
                          self.file1, self.file2, link_type="hardlink-or-copy")

    def test_link_dir_hardlink(self):
        self.linker.link(self.src_dir, self.dst_dir, link_type="hardlink")
        self.assertTrue(os.path.isfile(self.dst_file1))
        self.assertTrue(self.same_inode(self.file1, self.dst_file1))
        self.assertTrue(self.same_inode(self.file3, self.dst_file3))
        self.assertSameStat(os.path.dirname(self.file3), os.path.dirname(self.dst_file3))

        # always preserve symlinks
        self.assertEqual(os.readlink(self.dst_symlink1), "../file1")
        self.assertEqual(os.readlink(self.dst_symlink2), "subdir")
        self.assertEqual(os.readlink(self.dst_symlink3), "does-not-exist")

    def test_link_dir_copy(self):
        self.linker.link(self.src_dir, self.dst_dir, link_type="copy")
        self.assertTrue(os.path.isfile(self.dst_file1))
        self.assertFalse(self.same_inode(self.file1, self.dst_file1))
        self.assertFalse(self.same_inode(self.file3, self.dst_file3))
        self.assertSameStat(os.path.dirname(self.file3), os.path.dirname(self.dst_file3))

        # always preserve symlinks
        self.assertEqual(os.readlink(self.dst_symlink1), "../file1")
        self.assertEqual(os.readlink(self.dst_symlink2), "subdir")
        self.assertEqual(os.readlink(self.dst_symlink3), "does-not-exist")

    def test_link_dir_copy_test_mode(self):
        # turn test mode on
        self.linker = linker.Linker(logger=self.logger, test=True)
        self.linker.link(self.src_dir, self.dst_dir, link_type="copy")

        # dst_dir should not even exist
        self.assertFalse(os.path.isdir(self.dst_dir))

    def test_link_dir_symlink(self):
        self.linker.link(self.src_dir, self.dst_dir, link_type="symlink")
        self.assertTrue(os.path.isfile(self.dst_file1))
        self.assertTrue(os.path.islink(self.dst_file1))
        self.assertTrue(os.path.isdir(os.path.dirname(self.file3)))

        # always preserve symlinks
        self.assertEqual(os.readlink(self.dst_symlink1), "../file1")
        self.assertEqual(os.readlink(self.dst_symlink2), "subdir")
        self.assertEqual(os.readlink(self.dst_symlink3), "does-not-exist")

    def test_link_dir_abspath_symlink(self):
        self.linker.link(self.src_dir, self.dst_dir, link_type="abspath-symlink")
        self.assertTrue(os.path.isfile(self.dst_file1))
        self.assertTrue(os.path.islink(self.dst_file1))
        self.assertEqual(os.readlink(self.dst_file1), self.file1)
        self.assertSameStat(os.path.dirname(self.file3), os.path.dirname(self.dst_file3))
        self.assertTrue(os.path.isdir(os.path.dirname(self.file3)))

        # always preserve symlinks
        self.assertEqual(os.readlink(self.dst_symlink1), "../file1")
        self.assertEqual(os.readlink(self.dst_symlink2), "subdir")
        self.assertEqual(os.readlink(self.dst_symlink3), "does-not-exist")

    def test_copy_preserve_hardlinks(self):
        self.assertTrue(self.same_inode(self.file1, self.hardlink1))
        self.linker.link(self.src_dir, self.dst_dir, link_type="copy")
        self.assertTrue(self.same_inode(self.dst_file1, self.dst_hardlink1))


if __name__ == "__main__":
    unittest.main()
