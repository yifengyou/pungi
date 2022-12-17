# -*- coding: utf-8 -*-

import mock

import os

import koji as orig_koji

from tests import helpers
from pungi.phases import osbuild


class OSBuildPhaseTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_run(self, ThreadPool):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "version": "1",
            "target": "image-target",
            "arches": ["x86_64"],
            "failable": ["x86_64"],
            "image_types": ["qcow2"],
        }
        compose = helpers.DummyCompose(
            self.topdir, {"osbuild": {"^Everything$": [cfg]}}
        )

        self.assertValidConfig(compose.conf)

        pool = ThreadPool.return_value

        phase = osbuild.OSBuildPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        compose.variants["Everything"],
                        cfg,
                        ["x86_64"],
                        "1",
                        None,
                        "image-target",
                        [self.topdir + "/compose/Everything/$arch/os"],
                        ["x86_64"],
                    ),
                ),
            ],
        )

    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_run_with_global_options(self, ThreadPool):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["qcow2"],
        }
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "osbuild": {"^Everything$": [cfg]},
                "osbuild_target": "image-target",
                "osbuild_version": "1",
                "osbuild_release": "2",
            },
        )

        self.assertValidConfig(compose.conf)

        pool = ThreadPool.return_value

        phase = osbuild.OSBuildPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        compose.variants["Everything"],
                        cfg,
                        sorted(compose.variants["Everything"].arches),
                        "1",
                        "2",
                        "image-target",
                        [self.topdir + "/compose/Everything/$arch/os"],
                        [],
                    ),
                ),
            ],
        )

    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = osbuild.OSBuildPhase(compose)
        self.assertTrue(phase.skip())


class RunOSBuildThreadTest(helpers.PungiTestCase):
    def setUp(self):
        super(RunOSBuildThreadTest, self).setUp()
        self.pool = mock.Mock()
        self.t = osbuild.RunOSBuildThread(self.pool)
        self.compose = helpers.DummyCompose(
            self.topdir,
            {
                "koji_profile": "koji",
                "translate_paths": [(self.topdir, "http://root")],
            },
        )

    def make_fake_watch(self, retval):
        def inner(task_id, log_file):
            with open(log_file, "w") as f:
                f.write("Creating compose: test-image-1-1 1234\n")
            return retval

        return inner

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process(self, KojiWrapper, Linker):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "disk.aarch64.qcow2",
                "type_name": "qcow2",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "disk.x86_64.qcow2",
                "type_name": "qcow2",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",  # version
                "15",  # release
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["qcow2"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={
                        "release": "15",
                        "repo": [self.topdir + "/compose/Everything/$arch/os"],
                    },
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/disk.%(arch)s.qcow2" % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("qcow2", image.format)
            self.assertEqual("qcow2", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process_ostree(self, KojiWrapper, Linker):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["edge-raw-disk"],
            "ostree_url": "http://edge.example.com/repo",
            "ostree_ref": "test/iot",
            "ostree_parent": "test/iot-parent",
        }
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "image.aarch64.raw.xz",
                "type_name": "raw-xz",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "image.x86_64.raw.xz",
                "type_name": "raw-xz",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",  # version
                "15",  # release
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["edge-raw-disk"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={
                        "release": "15",
                        "repo": [self.topdir + "/compose/Everything/$arch/os"],
                        "ostree": {
                            "url": "http://edge.example.com/repo",
                            "ref": "test/iot",
                            "parent": "test/iot-parent",
                        },
                    },
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/image.%(arch)s.raw.xz"
                % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("raw.xz", image.format)
            self.assertEqual("raw-xz", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/image.%(arch)s.raw.xz"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/image.%(arch)s.raw.xz"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process_without_release(self, KojiWrapper, Linker):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "disk.aarch64.qcow2",
                "type_name": "qcow2",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "disk.x86_64.qcow2",
                "type_name": "qcow2",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",
                None,
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["qcow2"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={"repo": [self.topdir + "/compose/Everything/$arch/os"]},
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/disk.%(arch)s.qcow2" % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("qcow2", image.format)
            self.assertEqual("qcow2", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_task_fails(self, KojiWrapper):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(1)
        koji.koji_proxy.osbuildImage.return_value = 1234

        with self.assertRaises(RuntimeError):
            self.t.process(
                (
                    self.compose,
                    self.compose.variants["Everything"],
                    cfg,
                    ["aarch64", "x86_64"],
                    "1",
                    None,
                    "image-target",
                    [self.topdir + "/compose/Everything/$arch/os"],
                    False,
                ),
                1,
            )

    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_task_fails_but_is_failable(self, KojiWrapper):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["qcow2"],
            "failable": ["x86_65"],
        }
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(1)
        koji.koji_proxy.osbuildImage.return_value = 1234

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",
                None,
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                True,
            ),
            1,
        )

        self.assertFalse(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertFalse(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )
        self.assertEqual(len(self.compose.im.add.call_args_list), 0)
