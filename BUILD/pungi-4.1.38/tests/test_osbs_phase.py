#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import mock
import json

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests import helpers
from pungi import checks
from pungi.phases import osbs


class OSBSPhaseTest(helpers.PungiTestCase):

    @mock.patch('pungi.phases.osbs.ThreadPool')
    def test_run(self, ThreadPool):
        cfg = helpers.IterableMock()
        compose = helpers.DummyCompose(self.topdir, {
            'osbs': {'^Everything$': cfg}
        })

        pool = ThreadPool.return_value

        phase = osbs.OSBSPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(pool.queue_put.call_args_list,
                         [mock.call((compose, compose.variants['Everything'], cfg))])

    @mock.patch('pungi.phases.osbs.ThreadPool')
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = osbs.OSBSPhase(compose)
        self.assertTrue(phase.skip())

    @mock.patch('pungi.phases.osbs.ThreadPool')
    def test_dump_metadata(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {
            'osbs': {'^Everything$': {}}
        })
        compose.just_phases = None
        compose.skip_phases = []
        compose.notifier = mock.Mock()
        phase = osbs.OSBSPhase(compose)
        phase.start()
        phase.stop()
        phase.pool.metadata = METADATA
        phase.dump_metadata()

        with open(self.topdir + '/compose/metadata/osbs.json') as f:
            data = json.load(f)
            self.assertEqual(data, METADATA)

    @mock.patch('pungi.phases.osbs.ThreadPool')
    def test_dump_metadata_after_skip(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = osbs.OSBSPhase(compose)
        phase.start()
        phase.stop()
        phase.dump_metadata()

        self.assertFalse(os.path.isfile(self.topdir + '/compose/metadata/osbs.json'))

    @mock.patch("pungi.phases.osbs.ThreadPool")
    def test_request_push(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {
            "osbs": {"^Everything$": {}}
        })
        compose.just_phases = None
        compose.skip_phases = []
        compose.notifier = mock.Mock()
        phase = osbs.OSBSPhase(compose)
        phase.start()
        phase.stop()
        phase.pool.registries = {"foo": "bar"}
        phase.request_push()

        with open(os.path.join(self.topdir, "logs/global/osbs-registries.json")) as f:
            data = json.load(f)
            self.assertEqual(data, phase.pool.registries)

        self.assertEqual(
            compose.notifier.call_args_list,
            [],
        )


TASK_RESULT = {
    'koji_builds': ['54321'],
    'repositories': [
        'registry.example.com:8888/rcm/buildroot:f24-docker-candidate-20160617141632',
    ]
}

BUILD_INFO = {
    'completion_time': '2016-06-17 18:25:30',
    'completion_ts': 1466187930.0,
    'creation_event_id': 13227702,
    'creation_time': '2016-06-17 18:25:57.611172',
    'creation_ts': 1466187957.61117,
    'epoch': None,
    'extra': {'container_koji_task_id': '12345', 'image': {}},
    'id': 54321,
    'name': 'my-name',
    'nvr': 'my-name-1.0-1',
    'owner_id': 3436,
    'owner_name': 'osbs',
    'package_id': 50072,
    'package_name': 'my-name',
    'release': '1',
    'source': 'git://example.com/repo?#BEEFCAFE',
    'start_time': '2016-06-17 18:16:37',
    'start_ts': 1466187397.0,
    'state': 1,
    'task_id': None,
    'version': '1.0',
    'volume_id': 0,
    'volume_name': 'DEFAULT'
}

ARCHIVES = [
    {'build_id': 54321,
     'buildroot_id': 2955357,
     'checksum': 'a2922842dc80873ac782da048c54f6cc',
     'checksum_type': 0,
     'extra': {
         'docker': {
             'id': '408c4cd37a87a807bec65dd13b049a32fe090d2fa1a8e891f65e3e3e683996d7',
             'parent_id': '6c3a84d798dc449313787502060b6d5b4694d7527d64a7c99ba199e3b2df834e',
             'repositories': ['registry.example.com:8888/rcm/buildroot:1.0-1']},
         'image': {'arch': 'x86_64'}},
     'filename': 'docker-image-408c4cd37a87a807bec65dd13b049a32fe090d2fa1a8e891f65e3e3e683996d7.x86_64.tar.gz',
     'id': 1436049,
     'metadata_only': False,
     'size': 174038795,
     'type_description': 'Tar file',
     'type_extensions': 'tar tar.gz tar.bz2 tar.xz',
     'type_id': 4,
     'type_name': 'tar'}
]

METADATA = {
    'Server': {'x86_64': [{
        'name': 'my-name',
        'version': '1.0',
        'release': '1',
        'nvr': 'my-name-1.0-1',
        'creation_time': BUILD_INFO['creation_time'],
        'filename': ARCHIVES[0]['filename'],
        'size': ARCHIVES[0]['size'],
        'docker': {
            'id': '408c4cd37a87a807bec65dd13b049a32fe090d2fa1a8e891f65e3e3e683996d7',
            'parent_id': '6c3a84d798dc449313787502060b6d5b4694d7527d64a7c99ba199e3b2df834e',
            'repositories': ['registry.example.com:8888/rcm/buildroot:1.0-1']},
        'image': {'arch': 'x86_64'},
        'checksum': ARCHIVES[0]['checksum'],
    }]}
}

SCRATCH_TASK_RESULT = {
    'koji_builds': [],
    'repositories': [
        'registry.example.com:8888/rcm/buildroot:f24-docker-candidate-20160617141632',
    ]
}

SCRATCH_METADATA = {
    "Server": {'scratch': [{
        "koji_task": 12345,
        "repositories": [
            'registry.example.com:8888/rcm/buildroot:f24-docker-candidate-20160617141632',
        ]
    }]}
}


class OSBSThreadTest(helpers.PungiTestCase):

    def setUp(self):
        super(OSBSThreadTest, self).setUp()
        self.pool = mock.Mock(metadata={}, registries={})
        self.t = osbs.OSBSThread(self.pool)
        self.compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'translate_paths': [
                (self.topdir, 'http://root'),
            ]
        })

    def _setupMock(self, KojiWrapper, scratch=False):
        self.wrapper = KojiWrapper.return_value
        self.wrapper.koji_proxy.buildContainer.return_value = 12345
        if scratch:
            self.wrapper.koji_proxy.getTaskResult.return_value = SCRATCH_TASK_RESULT
        else:
            self.wrapper.koji_proxy.getTaskResult.return_value = TASK_RESULT
            self.wrapper.koji_proxy.getBuild.return_value = BUILD_INFO
            self.wrapper.koji_proxy.listArchives.return_value = ARCHIVES
        self.wrapper.koji_proxy.getLatestBuilds.return_value = [mock.Mock(), mock.Mock()]
        self.wrapper.koji_proxy.getNextRelease.return_value = 3
        self.wrapper.watch_task.return_value = 0

    def _assertCorrectMetadata(self, scratch=False):
        self.maxDiff = None
        if scratch:
            metadata = copy.deepcopy(SCRATCH_METADATA)
            metadata['Server']['scratch'][0]['compose_id'] = self.compose.compose_id
            metadata['Server']['scratch'][0]['koji_task'] = 12345
        else:
            metadata = copy.deepcopy(METADATA)
            metadata['Server']['x86_64'][0]['compose_id'] = self.compose.compose_id
            metadata['Server']['x86_64'][0]['koji_task'] = 12345
        self.assertEqual(self.pool.metadata, metadata)

    def _assertCorrectCalls(self, opts, setupCalls=None, scratch=False):
        setupCalls = setupCalls or []
        options = {'yum_repourls': ['http://root/work/global/tmp-Server/compose-rpms-Server-1.repo']}
        if scratch:
            options['scratch'] = True
        options.update(opts)
        expect_calls = [mock.call.login()] + setupCalls
        expect_calls.extend([
            mock.call.koji_proxy.buildContainer(
                'git://example.com/repo?#BEEFCAFE',
                'f24-docker-candidate',
                options,
                priority=None),
            mock.call.watch_task(
                12345, self.topdir + '/logs/global/osbs/Server-1-watch-task.log'),
            mock.call.koji_proxy.getTaskResult(12345)])

        if not scratch:
            expect_calls.extend([mock.call.koji_proxy.getBuild(54321),
                                 mock.call.koji_proxy.listArchives(54321)])
        self.assertEqual(self.wrapper.mock_calls, expect_calls)

    def _assertRepoFile(self, variants=None, gpgkey=None):
        variants = variants or ['Server']
        for variant in variants:
            with open(self.topdir + '/work/global/tmp-%s/compose-rpms-%s-1.repo' % (variant, variant)) as f:
                lines = f.read().split('\n')
                self.assertIn('baseurl=http://root/compose/%s/$basearch/os' % variant, lines)
                if gpgkey:
                    self.assertIn('gpgcheck=1', lines)
                    self.assertIn('gpgkey=%s' % gpgkey, lines)

    def _assertConfigCorrect(self, cfg):
        config = copy.deepcopy(self.compose.conf)
        config['osbs'] = {
            '^Server$': cfg
        }
        self.assertEqual(([], []), checks.validate(config, offline=True))

    def _assertConfigMissing(self, cfg, key):
        config = copy.deepcopy(self.compose.conf)
        config['osbs'] = {
            '^Server$': cfg
        }
        errors, warnings = checks.validate(config, offline=True)
        self.assertIn(
            "Failed validation in osbs.^Server$: %r is not valid under any of the given schemas" % cfg,
            errors,
        )
        self.assertIn("    Possible reason: %r is a required property" % key, errors)
        self.assertEqual([], warnings)

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_minimal_run(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
        }
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self._assertCorrectCalls({'git_branch': 'f24-docker'})
        self._assertCorrectMetadata()
        self._assertRepoFile()

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_failable(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'failable': ['*']
        }
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self._assertCorrectCalls({'git_branch': 'f24-docker'})
        self._assertCorrectMetadata()
        self._assertRepoFile()

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_with_more_args(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
            'version': '1.0',
        }
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self._assertCorrectCalls({'name': 'my-name', 'version': '1.0', 'git_branch': 'f24-docker'})
        self._assertCorrectMetadata()
        self._assertRepoFile()

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_with_extra_repos(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
            'version': '1.0',
            "repo": ["Everything", "http://pkgs.example.com/my.repo", "/extra/repo"],
        }
        self.compose.conf["translate_paths"].append(("/extra", "http://example.com"))
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        options = {
            'name': 'my-name',
            'version': '1.0',
            'git_branch': 'f24-docker',
            'yum_repourls': [
                'http://root/work/global/tmp-Server/compose-rpms-Server-1.repo',
                'http://root/work/global/tmp-Everything/compose-rpms-Everything-1.repo',
                'http://pkgs.example.com/my.repo',
                "http://root/work/global/tmp/compose-rpms-local-1.repo",
            ]
        }
        self._assertCorrectCalls(options)
        self._assertCorrectMetadata()
        self._assertRepoFile(['Server', 'Everything'])

        with open(os.path.join(self.topdir, "work/global/tmp/compose-rpms-local-1.repo")) as f:
            self.assertIn("baseurl=http://example.com/repo\n", f)

    @mock.patch("pungi.phases.osbs.kojiwrapper.KojiWrapper")
    def test_run_with_deprecated_registry(self, KojiWrapper):
        cfg = {
            "url": "git://example.com/repo?#BEEFCAFE",
            "target": "f24-docker-candidate",
            "git_branch": "f24-docker",
            "name": "my-name",
            "version": "1.0",
            "repo": ["Everything", "http://pkgs.example.com/my.repo"],
            "registry": {"foo": "bar"},
        }
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants["Server"], cfg), 1)

        options = {
            "name": "my-name",
            "version": "1.0",
            "git_branch": "f24-docker",
            "yum_repourls": [
                "http://root/work/global/tmp-Server/compose-rpms-Server-1.repo",
                "http://root/work/global/tmp-Everything/compose-rpms-Everything-1.repo",
                "http://pkgs.example.com/my.repo",
            ]
        }
        self._assertCorrectCalls(options)
        self._assertCorrectMetadata()
        self._assertRepoFile(["Server", "Everything"])
        self.assertEqual(self.t.pool.registries, {"my-name-1.0-1": {"foo": "bar"}})

    @mock.patch("pungi.phases.osbs.kojiwrapper.KojiWrapper")
    def test_run_with_registry(self, KojiWrapper):
        cfg = {
            "url": "git://example.com/repo?#BEEFCAFE",
            "target": "f24-docker-candidate",
            "git_branch": "f24-docker",
            "name": "my-name",
            "version": "1.0",
            "repo": ["Everything", "http://pkgs.example.com/my.repo"],
        }
        self.compose.conf["osbs_registries"] = {"my-name-1.0-*": [{"foo": "bar"}]}
        self._setupMock(KojiWrapper)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants["Server"], cfg), 1)

        options = {
            "name": "my-name",
            "version": "1.0",
            "git_branch": "f24-docker",
            "yum_repourls": [
                "http://root/work/global/tmp-Server/compose-rpms-Server-1.repo",
                "http://root/work/global/tmp-Everything/compose-rpms-Everything-1.repo",
                "http://pkgs.example.com/my.repo",
            ]
        }
        self._assertCorrectCalls(options)
        self._assertCorrectMetadata()
        self._assertRepoFile(["Server", "Everything"])
        self.assertEqual(self.t.pool.registries, {"my-name-1.0-1": [{"foo": "bar"}]})

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_with_extra_repos_in_list(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
            'version': '1.0',
            'repo': ['Everything', 'Client', 'http://pkgs.example.com/my.repo'],
        }
        self._assertConfigCorrect(cfg)
        self._setupMock(KojiWrapper)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        options = {
            'name': 'my-name',
            'version': '1.0',
            'git_branch': 'f24-docker',
            'yum_repourls': [
                'http://root/work/global/tmp-Server/compose-rpms-Server-1.repo',
                'http://root/work/global/tmp-Everything/compose-rpms-Everything-1.repo',
                'http://root/work/global/tmp-Client/compose-rpms-Client-1.repo',
                'http://pkgs.example.com/my.repo',
            ]
        }
        self._assertCorrectCalls(options)
        self._assertCorrectMetadata()
        self._assertRepoFile(['Server', 'Everything', 'Client'])

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_with_gpgkey_enabled(self, KojiWrapper):
        gpgkey = 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release'
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
            'version': '1.0',
            'repo': ['Everything', 'Client', 'http://pkgs.example.com/my.repo'],
            'gpgkey': gpgkey,
        }
        self._assertConfigCorrect(cfg)
        self._setupMock(KojiWrapper)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self._assertRepoFile(['Server', 'Everything', 'Client'], gpgkey=gpgkey)

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_run_with_extra_repos_missing_variant(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
            'version': '1.0',
            'repo': 'Gold',
        }
        self._assertConfigCorrect(cfg)
        self._setupMock(KojiWrapper)

        with self.assertRaises(RuntimeError) as ctx:
            self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self.assertIn('no variant Gold', str(ctx.exception))

    def test_run_with_missing_url(self):
        cfg = {
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'name': 'my-name',
        }
        self._assertConfigMissing(cfg, 'url')

    def test_run_with_missing_target(self):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'git_branch': 'f24-docker',
            'name': 'my-name',
        }
        self._assertConfigMissing(cfg, 'target')

    def test_run_with_missing_git_branch(self):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
        }
        self._assertConfigMissing(cfg, 'git_branch')

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_failing_task(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'fedora-24-docker-candidate',
            'git_branch': 'f24-docker',
        }
        self._assertConfigCorrect(cfg)
        self._setupMock(KojiWrapper)
        self.wrapper.watch_task.return_value = 1

        with self.assertRaises(RuntimeError) as ctx:
            self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self.assertRegexpMatches(str(ctx.exception), r"task 12345 failed: see .+ for details")

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_failing_task_with_failable(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'fedora-24-docker-candidate',
            'git_branch': 'f24-docker',
            'failable': ['*']
        }
        self._assertConfigCorrect(cfg)
        self._setupMock(KojiWrapper)
        self.wrapper.watch_task.return_value = 1

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

    @mock.patch('pungi.phases.osbs.kojiwrapper.KojiWrapper')
    def test_scratch_metadata(self, KojiWrapper):
        cfg = {
            'url': 'git://example.com/repo?#BEEFCAFE',
            'target': 'f24-docker-candidate',
            'git_branch': 'f24-docker',
            'scratch': True,
        }
        self._setupMock(KojiWrapper, scratch=True)
        self._assertConfigCorrect(cfg)

        self.t.process((self.compose, self.compose.variants['Server'], cfg), 1)

        self._assertCorrectCalls({'git_branch': 'f24-docker'}, scratch=True)
        self._assertCorrectMetadata(scratch=True)
        self._assertRepoFile()


if __name__ == '__main__':
    unittest.main()
