# -*- coding: utf-8 -*-


import mock

import six

from pungi.phases.live_images import LiveImagesPhase, CreateLiveImageThread
from tests.helpers import DummyCompose, PungiTestCase, boom


class TestLiveImagesPhase(PungiTestCase):
    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_live_image_build(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": [
                                    "http://example.com/repo/",
                                    "Everything",
                                    "Server-optional",
                                ],
                                "release": None,
                                "target": "f27",
                            }
                        },
                    )
                ],
            },
        )
        compose.setup_optional()

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                                self.topdir + "/compose/Server-optional/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "ksurl": None,
                            "target": "f27",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )
        six.assertCountEqual(
            self,
            compose.get_image_name.mock_calls,
            [
                mock.call(
                    "amd64",
                    compose.variants["Client"],
                    disc_num=None,
                    disc_type="live",
                    format="%(compose_id)s-%(variant)s-%(arch)s-%(disc_type)s%(disc_num)s%(suffix)s",  # noqa: E501
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_live_image_build_single_repo_from(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": ["http://example.com/repo/", "Everything"],
                                "release": None,
                                "target": "f27",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "ksurl": None,
                            "target": "f27",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_live_image_build_without_rename(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images_no_rename": True,
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": ["http://example.com/repo/", "Everything"],
                                "release": None,
                                "target": "f27",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": None,
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "ksurl": None,
                            "target": "f27",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_live_image_build_two_images(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": [
                                {
                                    "kickstart": "test.ks",
                                    "repo": ["http://example.com/repo/", "Everything"],
                                    "target": "f27",
                                },
                                {
                                    "kickstart": "another.ks",
                                    "repo": ["http://example.com/repo/", "Everything"],
                                    "target": "f27",
                                },
                            ]
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": None,
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": None,
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                ),
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "another.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": None,
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": None,
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                ),
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_spin_appliance(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",  # noqa: E501
                                "repo": ["http://example.com/repo/", "Everything"],
                                "type": "appliance",
                                "target": "f27",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/images",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "appliance",
                            "release": None,
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_spin_appliance_phase_global_settings(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "live_images_ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
                "live_images_release": None,
                "live_images_version": "Rawhide",
                "live_images_target": "f27",
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": ["http://example.com/repo/", "Everything"],
                                "type": "appliance",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/images",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "Rawhide",
                            "specfile": None,
                            "sign": False,
                            "type": "appliance",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_spin_appliance_global_settings(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "global_ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
                "global_release": None,
                "global_version": "Rawhide",
                "global_target": "f27",
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": ["http://example.com/repo/", "Everything"],
                                "type": "appliance",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/images",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "Rawhide",
                            "specfile": None,
                            "sign": False,
                            "type": "appliance",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )

    @mock.patch("pungi.phases.live_images.ThreadPool")
    def test_live_image_build_custom_type(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "disc_types": {"live": "Live"},
                "live_images": [
                    (
                        "^Client$",
                        {
                            "amd64": {
                                "kickstart": "test.ks",
                                "repo": ["http://example.com/repo/", "Everything"],
                                "release": None,
                                "target": "f27",
                            }
                        },
                    )
                ],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = LiveImagesPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call(
                    (
                        compose,
                        {
                            "ks_file": "test.ks",
                            "build_arch": "amd64",
                            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
                            "scratch": False,
                            "repos": [
                                self.topdir + "/compose/Client/amd64/os",
                                "http://example.com/repo/",
                                self.topdir + "/compose/Everything/amd64/os",
                            ],
                            "label": "",
                            "name": None,
                            "filename": "image-name",
                            "version": "25",
                            "specfile": None,
                            "sign": False,
                            "type": "live",
                            "release": "20151203.t.0",
                            "subvariant": "Client",
                            "failable_arches": [],
                            "target": "f27",
                            "ksurl": None,
                        },
                        compose.variants["Client"],
                        "amd64",
                    )
                )
            ],
        )
        six.assertCountEqual(
            self,
            compose.get_image_name.mock_calls,
            [
                mock.call(
                    "amd64",
                    compose.variants["Client"],
                    disc_num=None,
                    disc_type="Live",
                    format="%(compose_id)s-%(variant)s-%(arch)s-%(disc_type)s%(disc_num)s%(suffix)s",  # noqa: E501
                )
            ],
        )


class TestCreateLiveImageThread(PungiTestCase):
    @mock.patch("pungi.phases.live_images.Image")
    @mock.patch("shutil.copy2")
    @mock.patch("pungi.phases.live_images.run")
    @mock.patch("pungi.phases.live_images.KojiWrapper")
    def test_process(self, KojiWrapper, run, copy2, Image):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "ks_file": "/path/to/ks_file",
            "build_arch": "amd64",
            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
            "scratch": False,
            "repos": [
                "/repo/amd64/Client",
                "http://example.com/repo/",
                "/repo/amd64/Everything",
            ],
            "label": "",
            "name": None,
            "filename": "image-name",
            "version": None,
            "specfile": None,
            "type": "live",
            "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
            "release": None,
            "subvariant": "Something",
            "target": "f27",
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.get_create_image_cmd.return_value = "koji spin-livecd ..."
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 0,
            "output": "some output",
            "task_id": 123,
        }
        koji_wrapper.get_image_path.return_value = ["/path/to/image.iso"]

        t = CreateLiveImageThread(pool)
        with mock.patch("pungi.phases.live_images.get_file_size") as get_file_size:
            get_file_size.return_value = 1024
            with mock.patch("pungi.phases.live_images.get_mtime") as get_mtime:
                get_mtime.return_value = 13579
                with mock.patch("time.sleep"):
                    t.process((compose, cmd, compose.variants["Client"], "amd64"), 1)

        self.assertEqual(
            koji_wrapper.run_blocking_cmd.mock_calls,
            [
                mock.call(
                    "koji spin-livecd ...",
                    log_file=self.topdir
                    + "/logs/amd64/liveimage-None-None-None.amd64.log",
                )
            ],
        )
        self.assertEqual(koji_wrapper.get_image_path.mock_calls, [mock.call(123)])
        self.assertEqual(
            copy2.mock_calls,
            [
                mock.call(
                    "/path/to/image.iso",
                    self.topdir + "/compose/Client/amd64/iso/image-name",
                )
            ],
        )

        write_manifest_cmd = " && ".join(
            [
                "cd " + self.topdir + "/compose/Client/amd64/iso",
                "isoinfo -R -f -i image-name | grep -v '/TRANS.TBL$' | sort >> image-name.manifest",  # noqa: E501
            ]
        )
        self.assertEqual(run.mock_calls, [mock.call(write_manifest_cmd)])
        self.assertEqual(
            koji_wrapper.get_create_image_cmd.mock_calls,
            [
                mock.call(
                    "test-Something-Live-amd64",
                    "20151203.0.t",
                    "f27",
                    "amd64",
                    "/path/to/ks_file",
                    [
                        "/repo/amd64/Client",
                        "http://example.com/repo/",
                        "/repo/amd64/Everything",
                    ],
                    image_type="live",
                    archive=False,
                    specfile=None,
                    wait=True,
                    release=None,
                    ksurl="https://git.example.com/kickstarts.git?#CAFEBABE",
                )
            ],
        )
        self.assertEqual(Image.return_value.type, "live")
        self.assertEqual(Image.return_value.format, "iso")
        self.assertEqual(Image.return_value.path, "Client/amd64/iso/image-name")
        self.assertEqual(Image.return_value.size, 1024)
        self.assertEqual(Image.return_value.mtime, 13579)
        self.assertEqual(Image.return_value.arch, "amd64")
        self.assertEqual(Image.return_value.disc_number, 1)
        self.assertEqual(Image.return_value.disc_count, 1)
        self.assertTrue(Image.return_value.bootable)
        self.assertEqual(
            compose.im.add.mock_calls,
            [mock.call(variant="Client", arch="amd64", image=Image.return_value)],
        )

    @mock.patch("pungi.phases.live_images.Image")
    @mock.patch("shutil.copy2")
    @mock.patch("pungi.phases.live_images.run")
    @mock.patch("pungi.phases.live_images.KojiWrapper")
    def test_process_no_rename(self, KojiWrapper, run, copy2, Image):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "ks_file": "/path/to/ks_file",
            "build_arch": "amd64",
            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
            "scratch": False,
            "repos": [
                "/repo/amd64/Client",
                "http://example.com/repo/",
                "/repo/amd64/Everything",
            ],
            "label": "",
            "name": None,
            "filename": None,
            "version": None,
            "specfile": None,
            "type": "live",
            "ksurl": "https://git.example.com/kickstarts.git?#CAFEBABE",
            "release": None,
            "subvariant": "Client",
            "target": "f27",
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.get_create_image_cmd.return_value = "koji spin-livecd ..."
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 0,
            "output": "some output",
            "task_id": 123,
        }
        koji_wrapper.get_image_path.return_value = ["/path/to/image.iso"]

        t = CreateLiveImageThread(pool)
        with mock.patch("pungi.phases.live_images.get_file_size") as get_file_size:
            get_file_size.return_value = 1024
            with mock.patch("pungi.phases.live_images.get_mtime") as get_mtime:
                get_mtime.return_value = 13579
                with mock.patch("time.sleep"):
                    t.process((compose, cmd, compose.variants["Client"], "amd64"), 1)

        self.assertEqual(
            koji_wrapper.run_blocking_cmd.mock_calls,
            [
                mock.call(
                    "koji spin-livecd ...",
                    log_file=self.topdir
                    + "/logs/amd64/liveimage-None-None-None.amd64.log",
                )
            ],
        )
        self.assertEqual(koji_wrapper.get_image_path.mock_calls, [mock.call(123)])
        self.assertEqual(
            copy2.mock_calls,
            [
                mock.call(
                    "/path/to/image.iso",
                    self.topdir + "/compose/Client/amd64/iso/image.iso",
                )
            ],
        )

        write_manifest_cmd = " && ".join(
            [
                "cd " + self.topdir + "/compose/Client/amd64/iso",
                "isoinfo -R -f -i image.iso | grep -v '/TRANS.TBL$' | sort >> image.iso.manifest",  # noqa: E501
            ]
        )
        self.assertEqual(run.mock_calls, [mock.call(write_manifest_cmd)])
        self.assertEqual(
            koji_wrapper.get_create_image_cmd.mock_calls,
            [
                mock.call(
                    "test-Client-Live-amd64",
                    "20151203.0.t",
                    "f27",
                    "amd64",
                    "/path/to/ks_file",
                    [
                        "/repo/amd64/Client",
                        "http://example.com/repo/",
                        "/repo/amd64/Everything",
                    ],
                    image_type="live",
                    archive=False,
                    specfile=None,
                    wait=True,
                    release=None,
                    ksurl="https://git.example.com/kickstarts.git?#CAFEBABE",
                )
            ],
        )

        self.assertEqual(Image.return_value.type, "live")
        self.assertEqual(Image.return_value.format, "iso")
        self.assertEqual(Image.return_value.path, "Client/amd64/iso/image.iso")
        self.assertEqual(Image.return_value.size, 1024)
        self.assertEqual(Image.return_value.mtime, 13579)
        self.assertEqual(Image.return_value.arch, "amd64")
        self.assertEqual(Image.return_value.disc_number, 1)
        self.assertEqual(Image.return_value.disc_count, 1)
        self.assertTrue(Image.return_value.bootable)
        self.assertEqual(
            compose.im.add.mock_calls,
            [mock.call(variant="Client", arch="amd64", image=Image.return_value)],
        )

    @mock.patch("pungi.phases.live_images.Image")
    @mock.patch("shutil.copy2")
    @mock.patch("pungi.phases.live_images.run")
    @mock.patch("pungi.phases.live_images.KojiWrapper")
    def test_process_applicance(self, KojiWrapper, run, copy2, Image):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "ks_file": "/path/to/ks_file",
            "build_arch": "amd64",
            "dest_dir": self.topdir + "/compose/Client/amd64/iso",
            "scratch": False,
            "repos": [
                "/repo/amd64/Client",
                "http://example.com/repo/",
                "/repo/amd64/Everything",
            ],
            "label": "",
            "name": None,
            "filename": "image-name",
            "version": None,
            "specfile": None,
            "type": "appliance",
            "ksurl": None,
            "release": None,
            "subvariant": "Client",
            "target": "f27",
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.get_create_image_cmd.return_value = "koji spin-livecd ..."
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 0,
            "output": "some output",
            "task_id": 123,
        }
        koji_wrapper.get_image_path.return_value = ["/path/to/image-a.b-sda.raw.xz"]

        t = CreateLiveImageThread(pool)
        with mock.patch("pungi.phases.live_images.get_file_size") as get_file_size:
            get_file_size.return_value = 1024
            with mock.patch("pungi.phases.live_images.get_mtime") as get_mtime:
                get_mtime.return_value = 13579
                with mock.patch("time.sleep"):
                    t.process((compose, cmd, compose.variants["Client"], "amd64"), 1)

        self.assertEqual(
            koji_wrapper.run_blocking_cmd.mock_calls,
            [
                mock.call(
                    "koji spin-livecd ...",
                    log_file=self.topdir
                    + "/logs/amd64/liveimage-None-None-None.amd64.log",
                )
            ],
        )
        self.assertEqual(koji_wrapper.get_image_path.mock_calls, [mock.call(123)])
        self.assertEqual(
            copy2.mock_calls,
            [
                mock.call(
                    "/path/to/image-a.b-sda.raw.xz",
                    self.topdir + "/compose/Client/amd64/iso/image-name",
                )
            ],
        )

        self.assertEqual(run.mock_calls, [])
        self.assertEqual(
            koji_wrapper.get_create_image_cmd.mock_calls,
            [
                mock.call(
                    "test-Client-Disk-amd64",
                    "20151203.0.t",
                    "f27",
                    "amd64",
                    "/path/to/ks_file",
                    [
                        "/repo/amd64/Client",
                        "http://example.com/repo/",
                        "/repo/amd64/Everything",
                    ],
                    image_type="appliance",
                    archive=False,
                    specfile=None,
                    wait=True,
                    release=None,
                    ksurl=None,
                )
            ],
        )

        self.assertEqual(Image.return_value.type, "raw-xz")
        self.assertEqual(Image.return_value.format, "raw.xz")
        self.assertEqual(Image.return_value.path, "Client/amd64/iso/image-name")
        self.assertEqual(Image.return_value.size, 1024)
        self.assertEqual(Image.return_value.mtime, 13579)
        self.assertEqual(Image.return_value.arch, "amd64")
        self.assertEqual(Image.return_value.disc_number, 1)
        self.assertEqual(Image.return_value.disc_count, 1)
        self.assertTrue(Image.return_value.bootable)
        self.assertEqual(
            compose.im.add.mock_calls,
            [mock.call(variant="Client", arch="amd64", image=Image.return_value)],
        )

    @mock.patch("shutil.copy2")
    @mock.patch("pungi.phases.live_images.run")
    @mock.patch("pungi.phases.live_images.KojiWrapper")
    def test_process_handles_fail(self, KojiWrapper, run, copy2):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "ks_file": "/path/to/ks_file",
            "build_arch": "amd64",
            "dest_dir": "/top/iso_dir/amd64/Client",
            "scratch": False,
            "repos": [
                "/repo/amd64/Client",
                "http://example.com/repo/",
                "/repo/amd64/Everything",
            ],
            "label": "",
            "name": None,
            "filename": "image-name",
            "version": None,
            "specfile": None,
            "ksurl": None,
            "subvariant": "Client",
            "release": "xyz",
            "type": "live",
            "failable_arches": ["*"],
            "target": "f27",
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.get_create_image_cmd.return_value = "koji spin-livecd ..."
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 1,
            "output": "some output",
            "task_id": 123,
        }

        t = CreateLiveImageThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Client"], "amd64"), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Live (variant Client, arch amd64, subvariant Client) failed, but going on anyway."  # noqa: E501
                ),
                mock.call(
                    "LiveImage task failed: 123. See %s/logs/amd64/liveimage-None-None-xyz.amd64.log for more details."  # noqa: E501
                    % self.topdir
                ),
            ]
        )

    @mock.patch("shutil.copy2")
    @mock.patch("pungi.phases.live_images.run")
    @mock.patch("pungi.phases.live_images.KojiWrapper")
    def test_process_handles_exception(self, KojiWrapper, run, copy2):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "ks_file": "/path/to/ks_file",
            "build_arch": "amd64",
            "dest_dir": "/top/iso_dir/amd64/Client",
            "scratch": False,
            "repos": [
                "/repo/amd64/Client",
                "http://example.com/repo/",
                "/repo/amd64/Everything",
            ],
            "label": "",
            "name": None,
            "filename": "image-name",
            "version": None,
            "specfile": None,
            "ksurl": None,
            "subvariant": "Client",
            "release": "xyz",
            "type": "live",
            "failable_arches": ["*"],
            "target": "f27",
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.get_create_image_cmd.side_effect = boom

        t = CreateLiveImageThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Client"], "amd64"), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Live (variant Client, arch amd64, subvariant Client) failed, but going on anyway."  # noqa: E501
                ),
                mock.call("BOOM"),
            ]
        )
