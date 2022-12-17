# -*- coding: utf-8 -*-

import mock

import os

from tests import helpers
from pungi import checks
from pungi.phases import image_container


class ImageContainerPhaseTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.image_container.ThreadPool")
    def test_run(self, ThreadPool):
        cfg = helpers.IterableMock()
        compose = helpers.DummyCompose(
            self.topdir, {"image_container": {"^Everything$": cfg}}
        )

        pool = ThreadPool.return_value

        phase = image_container.ImageContainerPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [mock.call((compose, compose.variants["Everything"], cfg))],
        )

    @mock.patch("pungi.phases.image_container.ThreadPool")
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = image_container.ImageContainerPhase(compose)
        self.assertTrue(phase.skip())


class ImageContainerConfigTest(helpers.PungiTestCase):
    def assertConfigMissing(self, cfg, key):
        conf = helpers.load_config(
            helpers.PKGSET_REPOS, **{"image_container": {"^Server$": cfg}}
        )
        errors, warnings = checks.validate(conf, offline=True)
        self.assertIn(
            "Failed validation in image_container.^Server$: %r is not valid under any of the given schemas"  # noqa: E501
            % cfg,
            errors,
        )
        self.assertIn("    Possible reason: %r is a required property" % key, errors)
        self.assertEqual([], warnings)

    def test_correct(self):
        conf = helpers.load_config(
            helpers.PKGSET_REPOS,
            **{
                "image_container": {
                    "^Server$": [
                        {
                            "url": "http://example.com/repo.git#HEAD",
                            "target": "container-candidate",
                            "git_branch": "main",
                            "image_spec": {"type": "qcow2"},
                        }
                    ]
                }
            }
        )
        errors, warnings = checks.validate(conf, offline=True)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_missing_url(self):
        self.assertConfigMissing(
            {
                "target": "container-candidate",
                "git_branch": "main",
                "image_spec": {"type": "qcow2"},
            },
            "url",
        )

    def test_missing_target(self):
        self.assertConfigMissing(
            {
                "url": "http://example.com/repo.git#HEAD",
                "git_branch": "main",
                "image_spec": {"type": "qcow2"},
            },
            "target",
        )

    def test_missing_git_branch(self):
        self.assertConfigMissing(
            {
                "url": "http://example.com/repo.git#HEAD",
                "target": "container-candidate",
                "image_spec": {"type": "qcow2"},
            },
            "git_branch",
        )

    def test_missing_image_spec(self):
        self.assertConfigMissing(
            {
                "url": "http://example.com/repo.git#HEAD",
                "target": "container-candidate",
                "git_branch": "main",
            },
            "image_spec",
        )


class ImageContainerThreadTest(helpers.PungiTestCase):
    def setUp(self):
        super(ImageContainerThreadTest, self).setUp()
        self.pool = mock.Mock()
        self.repofile_path = "work/global/tmp-Server/image-container-Server-1.repo"
        self.t = image_container.ImageContainerThread(self.pool)
        self.compose = helpers.DummyCompose(
            self.topdir,
            {
                "koji_profile": "koji",
                "translate_paths": [(self.topdir, "http://root")],
            },
        )
        self.cfg = {
            "url": "git://example.com/repo?#BEEFCAFE",
            "target": "f24-docker-candidate",
            "git_branch": "f24-docker",
            "image_spec": {"type": "qcow2"},
        }
        self.compose.im.images["Server"] = {
            "x86_64": [
                mock.Mock(path="Server/x86_64/iso/image.iso", type="iso"),
                mock.Mock(path="Server/x86_64/images/image.qcow2", type="qcow2"),
            ]
        }

    def _setupMock(self, KojiWrapper):
        self.wrapper = KojiWrapper.return_value
        self.wrapper.koji_proxy.buildContainer.return_value = 12345
        self.wrapper.watch_task.return_value = 0

    def assertRepoFile(self):
        repofile = os.path.join(self.topdir, self.repofile_path)
        with open(repofile) as f:
            repo_content = list(f)
        self.assertIn("[image-to-include]\n", repo_content)
        self.assertIn(
            "baseurl=http://root/compose/Server/$basearch/images/image.qcow2\n",
            repo_content,
        )
        self.assertIn("enabled=0\n", repo_content)

    def assertKojiCalls(self, cfg, scratch=False):
        opts = {
            "git_branch": cfg["git_branch"],
            "yum_repourls": ["http://root/" + self.repofile_path],
        }
        if scratch:
            opts["scratch"] = True
        self.assertEqual(
            self.wrapper.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.buildContainer(
                    cfg["url"],
                    cfg["target"],
                    opts,
                    priority=None,
                ),
                mock.call.save_task_id(12345),
                mock.call.watch_task(
                    12345,
                    os.path.join(
                        self.topdir,
                        "logs/global/image_container/Server-1-watch-task.log",
                    ),
                ),
            ],
        )

    @mock.patch("pungi.phases.image_container.add_metadata")
    @mock.patch("pungi.phases.image_container.kojiwrapper.KojiWrapper")
    def test_success(self, KojiWrapper, add_metadata):
        self._setupMock(KojiWrapper)

        self.t.process(
            (self.compose, self.compose.variants["Server"], self.cfg.copy()), 1
        )

        self.assertRepoFile()
        self.assertKojiCalls(self.cfg)
        self.assertEqual(
            add_metadata.call_args_list,
            [mock.call(self.compose.variants["Server"], 12345, self.compose, False)],
        )

    @mock.patch("pungi.phases.image_container.add_metadata")
    @mock.patch("pungi.phases.image_container.kojiwrapper.KojiWrapper")
    def test_scratch_build(self, KojiWrapper, add_metadata):
        self.cfg["scratch"] = True
        self._setupMock(KojiWrapper)

        self.t.process(
            (self.compose, self.compose.variants["Server"], self.cfg.copy()), 1
        )

        self.assertRepoFile()
        self.assertKojiCalls(self.cfg, scratch=True)
        self.assertEqual(
            add_metadata.call_args_list,
            [mock.call(self.compose.variants["Server"], 12345, self.compose, True)],
        )

    @mock.patch("pungi.phases.image_container.add_metadata")
    @mock.patch("pungi.phases.image_container.kojiwrapper.KojiWrapper")
    def test_task_fail(self, KojiWrapper, add_metadata):
        self._setupMock(KojiWrapper)
        self.wrapper.watch_task.return_value = 1

        with self.assertRaises(RuntimeError) as ctx:
            self.t.process(
                (self.compose, self.compose.variants["Server"], self.cfg.copy()), 1
            )

        self.assertRegex(str(ctx.exception), r"task 12345 failed: see .+ for details")
        self.assertRepoFile()
        self.assertKojiCalls(self.cfg)
        self.assertEqual(add_metadata.call_args_list, [])

    @mock.patch("pungi.phases.image_container.add_metadata")
    @mock.patch("pungi.phases.image_container.kojiwrapper.KojiWrapper")
    def test_task_fail_failable(self, KojiWrapper, add_metadata):
        self.cfg["failable"] = "*"
        self._setupMock(KojiWrapper)
        self.wrapper.watch_task.return_value = 1

        self.t.process(
            (self.compose, self.compose.variants["Server"], self.cfg.copy()), 1
        )

        self.assertRepoFile()
        self.assertKojiCalls(self.cfg)
        self.assertEqual(add_metadata.call_args_list, [])

    @mock.patch("pungi.phases.image_container.add_metadata")
    @mock.patch("pungi.phases.image_container.kojiwrapper.KojiWrapper")
    def test_non_unique_spec(self, KojiWrapper, add_metadata):
        self.cfg["image_spec"] = {"path": ".*/image\\..*"}
        self._setupMock(KojiWrapper)

        with self.assertRaises(RuntimeError) as ctx:
            self.t.process(
                (self.compose, self.compose.variants["Server"], self.cfg.copy()), 1
            )

        self.assertRegex(
            str(ctx.exception), "2 images matched specification. Only one was expected."
        )
        self.assertEqual(self.wrapper.mock_calls, [])
        self.assertEqual(add_metadata.call_args_list, [])
