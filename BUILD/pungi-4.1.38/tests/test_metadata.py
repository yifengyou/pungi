#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import json
import mock
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests import helpers

from pungi import metadata
from pungi.compose_metadata import discinfo


class DiscInfoTestCase(helpers.PungiTestCase):

    def setUp(self):
        super(DiscInfoTestCase, self).setUp()
        os.environ['SOURCE_DATE_EPOCH'] = '101010101'
        self.path = os.path.join(self.topdir, 'compose/Server/x86_64/os/.discinfo')

    def test_write_discinfo_variant(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
        })

        metadata.write_discinfo(compose, 'x86_64', compose.variants['Server'])

        with open(self.path) as f:
            self.assertEqual(f.read().strip().split('\n'),
                             ['101010101',
                              'Test 1.0',
                              'x86_64',
                              'ALL'])

        self.assertEqual(discinfo.read_discinfo(self.path),
                         {'timestamp': '101010101',
                          'description': 'Test 1.0',
                          'disc_numbers': ['ALL'],
                          'arch': 'x86_64'})

    def test_write_discinfo_custom_description(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
            'release_discinfo_description': 'Fuzzy %(variant_name)s.%(arch)s',
        })
        compose.variants['Server'].name = 'Server'

        metadata.write_discinfo(compose, 'x86_64', compose.variants['Server'])

        with open(self.path) as f:
            self.assertEqual(f.read().strip().split('\n'),
                             ['101010101',
                              'Fuzzy Server.x86_64',
                              'x86_64',
                              'ALL'])

    def test_write_discinfo_layered_product(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
            'base_product_name': 'Base',
            'base_product_version': 42,
        })

        metadata.write_discinfo(compose, 'x86_64', compose.variants['Server'])

        with open(self.path) as f:
            self.assertEqual(f.read().strip().split('\n'),
                             ['101010101',
                              'Test 1.0 for Base 42',
                              'x86_64',
                              'ALL'])

    def test_write_discinfo_integrated_layered_product(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
        })
        compose.variants['ILP'] = mock.Mock(uid='Server', arches=['x86_64'],
                                            type='layered-product', is_empty=False,
                                            release_name='Integrated',
                                            release_version='2.1',
                                            parent=compose.variants['Server'])

        metadata.write_discinfo(compose, 'x86_64', compose.variants['ILP'])

        with open(self.path) as f:
            self.assertEqual(f.read().strip().split('\n'),
                             ['101010101',
                              'Integrated 2.1 for Test 1',
                              'x86_64',
                              'ALL'])

    def test_addons_dont_have_discinfo(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
        })
        compose.variants['ILP'] = mock.Mock(uid='Server', arches=['x86_64'],
                                            type='addon', is_empty=False,
                                            parent=compose.variants['Server'])

        metadata.write_discinfo(compose, 'x86_64', compose.variants['ILP'])

        self.assertFalse(os.path.isfile(self.path))


class MediaRepoTestCase(helpers.PungiTestCase):

    def setUp(self):
        super(MediaRepoTestCase, self).setUp()
        self.path = os.path.join(self.topdir, 'compose/Server/x86_64/os/media.repo')

    def test_write_media_repo(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
        })

        metadata.write_media_repo(compose, 'x86_64', compose.variants['Server'],
                                  timestamp=123456)

        with open(self.path) as f:
            lines = f.read().strip().split('\n')
            self.assertEqual(lines[0], '[InstallMedia]')
            self.assertItemsEqual(lines[1:],
                                  ['name=Test 1.0',
                                   'mediaid=123456',
                                   'metadata_expire=-1',
                                   'gpgcheck=0',
                                   'cost=500'])

    def test_addons_dont_have_media_repo(self):
        compose = helpers.DummyCompose(self.topdir, {
            'release_name': 'Test',
            'release_version': '1.0',
        })
        compose.variants['ILP'] = mock.Mock(uid='Server', arches=['x86_64'],
                                            type='addon', is_empty=False,
                                            parent=compose.variants['Server'])

        metadata.write_discinfo(compose, 'x86_64', compose.variants['ILP'])

        self.assertFalse(os.path.isfile(self.path))


class TestWriteExtraFiles(helpers.PungiTestCase):

    def setUp(self):
        super(TestWriteExtraFiles, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

    def test_write_extra_files(self):
        """Assert metadata is written to the proper location with valid data"""
        mock_logger = mock.Mock()
        files = ['file1', 'file2', 'subdir/file3']
        expected_metadata = {
            u'header': {u'version': u'1.0'},
            u'data': [
                {
                    u'file': u'file1',
                    u'checksums': {u'sha256': u'ecdc5536f73bdae8816f0ea40726ef5e9b810d914493075903bb90623d97b1d8'},
                    u'size': 6,
                },
                {
                    u'file': u'file2',
                    u'checksums': {u'sha256': u'67ee5478eaadb034ba59944eb977797b49ca6aa8d3574587f36ebcbeeb65f70e'},
                    u'size': 6,
                },
                {
                    u'file': u'subdir/file3',
                    u'checksums': {u'sha256': u'52f9f0e467e33da811330cad085fdb4eaa7abcb9ebfe6001e0f5910da678be51'},
                    u'size': 13,
                },
            ]
        }
        tree_dir = os.path.join(self.topdir, 'compose', 'Server', 'x86_64', 'os')
        for f in files:
            helpers.touch(os.path.join(tree_dir, f), f + '\n')

        metadata_file = metadata.write_extra_files(tree_dir, files, logger=mock_logger)
        with open(metadata_file) as metadata_fd:
            actual_metadata = json.load(metadata_fd)

        self.assertEqual(expected_metadata['header'], actual_metadata['header'])
        self.assertEqual(expected_metadata['data'], actual_metadata['data'])

    def test_write_extra_files_multiple_checksums(self):
        """Assert metadata is written to the proper location with valid data"""
        self.maxDiff = None
        mock_logger = mock.Mock()
        files = ['file1', 'file2', 'subdir/file3']
        expected_metadata = {
            u'header': {u'version': u'1.0'},
            u'data': [
                {
                    u'file': u'file1',
                    u'checksums': {
                        u'md5': u'5149d403009a139c7e085405ef762e1a',
                        u'sha256': u'ecdc5536f73bdae8816f0ea40726ef5e9b810d914493075903bb90623d97b1d8'
                    },
                    u'size': 6,
                },
                {
                    u'file': u'file2',
                    u'checksums': {
                        u'md5': u'3d709e89c8ce201e3c928eb917989aef',
                        u'sha256': u'67ee5478eaadb034ba59944eb977797b49ca6aa8d3574587f36ebcbeeb65f70e'
                    },
                    u'size': 6,
                },
                {
                    u'file': u'subdir/file3',
                    u'checksums': {
                        u'md5': u'1ed02b5cf7fd8626f854e9ef3fee8694',
                        u'sha256': u'52f9f0e467e33da811330cad085fdb4eaa7abcb9ebfe6001e0f5910da678be51'
                    },
                    u'size': 13,
                },
            ]
        }
        tree_dir = os.path.join(self.topdir, 'compose', 'Server', 'x86_64', 'os')
        for f in files:
            helpers.touch(os.path.join(tree_dir, f), f + '\n')

        metadata_file = metadata.write_extra_files(tree_dir, files,
                                                   checksum_type=['md5', 'sha256'],
                                                   logger=mock_logger)
        with open(metadata_file) as metadata_fd:
            actual_metadata = json.load(metadata_fd)

        self.assertEqual(expected_metadata['header'], actual_metadata['header'])
        self.assertEqual(expected_metadata['data'], actual_metadata['data'])

    def test_write_extra_files_missing_file(self):
        """Assert metadata is written to the proper location with valid data"""
        mock_logger = mock.Mock()
        files = ['file1', 'file2', 'subdir/file3']
        tree_dir = os.path.join(self.topdir, 'compose', 'Server', 'x86_64', 'os')
        for f in files:
            helpers.touch(os.path.join(tree_dir, f), f + '\n')
        files.append('missing_file')

        self.assertRaises(RuntimeError, metadata.write_extra_files, tree_dir, files, 'sha256', mock_logger)


if __name__ == "__main__":
    unittest.main()
