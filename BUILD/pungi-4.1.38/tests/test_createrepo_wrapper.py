#!/usr/bin/env python2
# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.wrappers.createrepo import CreaterepoWrapper


class CreateRepoWrapperTest(unittest.TestCase):

    def test_get_createrepo_c_cmd_minimal(self):
        repo = CreaterepoWrapper()
        cmd = repo.get_createrepo_cmd('/test/dir')

        self.assertEqual(cmd[:2], ['createrepo_c', '/test/dir'])
        self.assertItemsEqual(cmd[2:], ['--update', '--database', '--unique-md-filenames'])

    def test_get_createrepo_c_cmd_full(self):
        repo = CreaterepoWrapper()
        cmd = repo.get_createrepo_cmd(
            '/test/dir', baseurl='http://base.example.com', excludes=['abc', 'xyz'],
            pkglist='/test/pkglist', groupfile='/test/comps', cachedir='/test/cache',
            update=False, update_md_path='/test/md_path', skip_stat=True, checkts=True,
            split=True, pretty=False, database=False, checksum='sha256', unique_md_filenames=False,
            distro='Fedora', content=['c1', 'c2'], repo=['r1', 'r2'], revision='rev', deltas=True,
            oldpackagedirs='/test/old', num_deltas=2, workers=3, outputdir='/test/output',
            use_xz=True,
            extra_args=["--zck", "--zck-primary-dict=/foo/bar"],
        )
        self.maxDiff = None

        self.assertEqual(cmd[:2], ['createrepo_c', '/test/dir'])
        self.assertItemsEqual(cmd[2:],
                              ['--baseurl=http://base.example.com', '--excludes=abc', '--excludes=xyz',
                               '--pkglist=/test/pkglist', '--groupfile=/test/comps', '--cachedir=/test/cache',
                               '--skip-stat', '--update-md-path=/test/md_path', '--split', '--checkts',
                               '--checksum=sha256', '--distro=Fedora', '--simple-md-filenames', '--no-database',
                               '--content=c1', '--content=c2', '--repo=r1', '--repo=r2', '--revision=rev',
                               '--deltas', '--oldpackagedirs=/test/old', '--num-deltas=2', '--workers=3',
                               '--outputdir=/test/output', '--xz', "--zck", "--zck-primary-dict=/foo/bar"])

    def test_get_createrepo_cmd_minimal(self):
        repo = CreaterepoWrapper(False)
        cmd = repo.get_createrepo_cmd('/test/dir')

        self.assertEqual(cmd[:2], ['createrepo', '/test/dir'])
        self.assertItemsEqual(cmd[2:], ['--update', '--database', '--unique-md-filenames',
                                        '--pretty'])

    def test_get_createrepo_cmd_full(self):
        repo = CreaterepoWrapper(False)
        cmd = repo.get_createrepo_cmd(
            '/test/dir', baseurl='http://base.example.com', excludes=['abc', 'xyz'],
            pkglist='/test/pkglist', groupfile='/test/comps', cachedir='/test/cache',
            update=False, update_md_path='/test/md_path', skip_stat=True, checkts=True,
            split=True, pretty=False, database=False, checksum='sha256', unique_md_filenames=False,
            distro='Fedora', content=['c1', 'c2'], repo=['r1', 'r2'], revision='rev', deltas=True,
            oldpackagedirs='/test/old', num_deltas=2, workers=3, outputdir='/test/output'
        )
        self.maxDiff = None

        self.assertEqual(cmd[:2], ['createrepo', '/test/dir'])
        self.assertItemsEqual(cmd[2:],
                              ['--baseurl=http://base.example.com', '--excludes=abc', '--excludes=xyz',
                               '--pkglist=/test/pkglist', '--groupfile=/test/comps', '--cachedir=/test/cache',
                               '--skip-stat', '--update-md-path=/test/md_path', '--split', '--checkts',
                               '--checksum=sha256', '--distro=Fedora', '--simple-md-filenames', '--no-database',
                               '--content=c1', '--content=c2', '--repo=r1', '--repo=r2', '--revision=rev',
                               '--deltas', '--oldpackagedirs=/test/old', '--num-deltas=2', '--workers=3',
                               '--outputdir=/test/output'])
