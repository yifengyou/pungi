# -*- coding: utf-8 -*-


import logging
import mock
import six

import os

from tests import helpers
from pungi.createiso import CreateIsoOpts
from pungi.phases import createiso


class CreateisoPhaseTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_skip_all(self, ThreadPool):
        compose = helpers.DummyCompose(
            self.topdir, {"createiso_skip": [("^.*$", {"*": True, "src": True})]}
        )

        pool = ThreadPool.return_value

        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = mock.Mock()
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 0)
        self.assertEqual(pool.queue_put.call_args_list, [])

    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_nothing_happens_without_rpms(self, ThreadPool):
        compose = helpers.DummyCompose(
            self.topdir,
            {"release_short": "test", "release_version": "1.0", "createiso_skip": []},
        )

        pool = ThreadPool.return_value

        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = mock.Mock()
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 0)
        self.assertEqual(pool.queue_put.call_args_list, [])
        six.assertCountEqual(
            self,
            phase.logger.warning.call_args_list,
            [
                mock.call("No RPMs found for Everything.x86_64, skipping ISO"),
                mock.call("No RPMs found for Everything.amd64, skipping ISO"),
                mock.call("No RPMs found for Everything.src, skipping ISO"),
                mock.call("No RPMs found for Client.amd64, skipping ISO"),
                mock.call("No RPMs found for Client.src, skipping ISO"),
                mock.call("No RPMs found for Server.x86_64, skipping ISO"),
                mock.call("No RPMs found for Server.amd64, skipping ISO"),
                mock.call("No RPMs found for Server.src, skipping ISO"),
            ],
        )

    @mock.patch("pungi.createiso.write_script")
    @mock.patch("pungi.phases.createiso.prepare_iso")
    @mock.patch("pungi.phases.createiso.split_iso")
    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_start_one_worker(self, ThreadPool, split_iso, prepare_iso, write_script):
        compose = helpers.DummyCompose(
            self.topdir,
            {"release_short": "test", "release_version": "1.0", "createiso_skip": []},
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        disc_data = mock.Mock()
        split_iso.return_value = [disc_data]
        prepare_iso.return_value = "dummy-graft-points"

        pool = ThreadPool.return_value

        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = mock.Mock()
        phase.run()

        self.assertEqual(
            prepare_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    disc_count=1,
                    disc_num=1,
                    split_iso_data=disc_data,
                )
            ],
        )
        self.assertEqual(
            split_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    no_split=False,
                    logger=phase.logger,
                )
            ],
        )
        self.assertEqual(len(pool.add.call_args_list), 1)
        self.maxDiff = None
        self.assertEqual(
            [x[0][0] for x in write_script.call_args_list],
            [
                CreateIsoOpts(
                    output_dir="%s/compose/Server/x86_64/iso" % self.topdir,
                    iso_name="image-name",
                    volid="test-1.0 Server.x86_64",
                    graft_points="dummy-graft-points",
                    arch="x86_64",
                    supported=True,
                    jigdo_dir=None,
                    os_tree=None,
                    hfs_compat=True,
                    use_xorrisofs=False,
                    script_dir="%s/work/x86_64/tmp-Server" % self.topdir,
                )
            ],
        )
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        {
                            "iso_path": "%s/compose/Server/x86_64/iso/image-name"
                            % self.topdir,
                            "bootable": False,
                            "cmd": [
                                "bash",
                                self.topdir
                                + "/work/x86_64/tmp-Server/createiso-image-name.sh",
                            ],
                            "label": "",
                            "disc_num": 1,
                            "disc_count": 1,
                        },
                        compose.variants["Server"],
                        "x86_64",
                    )
                )
            ],
        )

    @mock.patch("pungi.createiso.write_script")
    @mock.patch("pungi.phases.createiso.prepare_iso")
    @mock.patch("pungi.phases.createiso.split_iso")
    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_bootable(self, ThreadPool, split_iso, prepare_iso, write_script):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "buildinstall_method": "lorax",
                "bootable": True,
                "createiso_skip": [],
            },
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("src", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        disc_data = mock.Mock()
        split_iso.return_value = [disc_data]
        prepare_iso.return_value = "dummy-graft-points"

        pool = ThreadPool.return_value

        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = mock.Mock()
        phase.run()

        six.assertCountEqual(
            self,
            prepare_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    disc_count=1,
                    disc_num=1,
                    split_iso_data=disc_data,
                ),
                mock.call(
                    compose,
                    "src",
                    compose.variants["Server"],
                    disc_count=1,
                    disc_num=1,
                    split_iso_data=disc_data,
                ),
            ],
        )
        six.assertCountEqual(
            self,
            split_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    no_split=True,
                    logger=phase.logger,
                ),
                mock.call(
                    compose,
                    "src",
                    compose.variants["Server"],
                    no_split=False,
                    logger=phase.logger,
                ),
            ],
        )
        self.assertEqual(len(pool.add.call_args_list), 2)
        self.maxDiff = None
        six.assertCountEqual(
            self,
            [x[0][0] for x in write_script.call_args_list],
            [
                CreateIsoOpts(
                    output_dir="%s/compose/Server/x86_64/iso" % self.topdir,
                    boot_iso=(
                        "%s/compose/Server/x86_64/os/images/boot.iso" % self.topdir
                    ),
                    iso_name="image-name",
                    volid="test-1.0 Server.x86_64",
                    graft_points="dummy-graft-points",
                    arch="x86_64",
                    buildinstall_method="lorax",
                    supported=True,
                    jigdo_dir=None,
                    os_tree=None,
                    hfs_compat=True,
                    use_xorrisofs=False,
                    script_dir="%s/work/x86_64/tmp-Server" % self.topdir,
                ),
                CreateIsoOpts(
                    output_dir="%s/compose/Server/source/iso" % self.topdir,
                    iso_name="image-name",
                    volid="test-1.0 Server.src",
                    graft_points="dummy-graft-points",
                    arch="src",
                    supported=True,
                    jigdo_dir=None,
                    os_tree=None,
                    hfs_compat=True,
                    use_xorrisofs=False,
                    script_dir="%s/work/src/tmp-Server" % self.topdir,
                ),
            ],
        )
        six.assertCountEqual(
            self,
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        {
                            "iso_path": "%s/compose/Server/x86_64/iso/image-name"
                            % self.topdir,
                            "bootable": True,
                            "cmd": [
                                "bash",
                                self.topdir
                                + "/work/x86_64/tmp-Server/createiso-image-name.sh",
                            ],
                            "label": "",
                            "disc_num": 1,
                            "disc_count": 1,
                        },
                        compose.variants["Server"],
                        "x86_64",
                    )
                ),
                mock.call(
                    (
                        compose,
                        {
                            "iso_path": "%s/compose/Server/source/iso/image-name"
                            % self.topdir,
                            "bootable": False,
                            "cmd": [
                                "bash",
                                self.topdir
                                + "/work/src/tmp-Server/createiso-image-name.sh",
                            ],
                            "label": "",
                            "disc_num": 1,
                            "disc_count": 1,
                        },
                        compose.variants["Server"],
                        "src",
                    )
                ),
            ],
        )

    @mock.patch("pungi.createiso.write_script")
    @mock.patch("pungi.phases.createiso.prepare_iso")
    @mock.patch("pungi.phases.createiso.split_iso")
    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_bootable_but_failed(
        self, ThreadPool, split_iso, prepare_iso, write_script
    ):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "buildinstall_method": "lorax",
                "bootable": True,
                "createiso_skip": [],
            },
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("src", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        disc_data = mock.Mock()
        split_iso.return_value = [disc_data]
        prepare_iso.return_value = "dummy-graft-points"

        pool = ThreadPool.return_value

        mock_bi = mock.Mock(succeeded=lambda v, a: False)

        phase = createiso.CreateisoPhase(compose, mock_bi)
        phase.logger = mock.Mock()
        phase.run()

        self.assertEqual(
            prepare_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "src",
                    compose.variants["Server"],
                    disc_count=1,
                    disc_num=1,
                    split_iso_data=disc_data,
                )
            ],
        )
        self.assertEqual(
            split_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "src",
                    compose.variants["Server"],
                    no_split=False,
                    logger=phase.logger,
                )
            ],
        )
        self.assertEqual(len(pool.add.call_args_list), 1)
        self.maxDiff = None
        self.assertEqual(
            [x[0][0] for x in write_script.call_args_list],
            [
                CreateIsoOpts(
                    output_dir="%s/compose/Server/source/iso" % self.topdir,
                    iso_name="image-name",
                    volid="test-1.0 Server.src",
                    graft_points="dummy-graft-points",
                    arch="src",
                    supported=True,
                    jigdo_dir=None,
                    os_tree=None,
                    hfs_compat=True,
                    use_xorrisofs=False,
                    script_dir="%s/work/src/tmp-Server" % self.topdir,
                )
            ],
        )
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        {
                            "iso_path": "%s/compose/Server/source/iso/image-name"
                            % self.topdir,
                            "bootable": False,
                            "cmd": [
                                "bash",
                                self.topdir
                                + "/work/src/tmp-Server/createiso-image-name.sh",
                            ],
                            "label": "",
                            "disc_num": 1,
                            "disc_count": 1,
                        },
                        compose.variants["Server"],
                        "src",
                    )
                )
            ],
        )

    @mock.patch("pungi.createiso.write_script")
    @mock.patch("pungi.phases.createiso.prepare_iso")
    @mock.patch("pungi.phases.createiso.split_iso")
    @mock.patch("pungi.phases.createiso.ThreadPool")
    def test_bootable_product_but_not_variant(
        self, ThreadPool, split_iso, prepare_iso, write_script
    ):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "buildinstall_method": "lorax",
                "bootable": True,
                "createiso_skip": [],
                "buildinstall_skip": [("Server", {"*": True})],
                "iso_hfs_ppc64le_compatible": False,
            },
        )
        helpers.touch(
            os.path.join(
                compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
                "dummy.rpm",
            )
        )
        disc_data = mock.Mock()
        split_iso.return_value = [disc_data]
        prepare_iso.return_value = "dummy-graft-points"

        pool = ThreadPool.return_value

        mock_bi = mock.Mock(succeeded=lambda v, a: False)

        phase = createiso.CreateisoPhase(compose, mock_bi)
        phase.logger = mock.Mock()
        phase.run()

        self.maxDiff = None
        self.assertEqual(
            prepare_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    disc_count=1,
                    disc_num=1,
                    split_iso_data=disc_data,
                )
            ],
        )
        self.assertEqual(
            split_iso.call_args_list,
            [
                mock.call(
                    compose,
                    "x86_64",
                    compose.variants["Server"],
                    no_split=False,
                    logger=phase.logger,
                )
            ],
        )
        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            [x[0][0] for x in write_script.call_args_list],
            [
                CreateIsoOpts(
                    output_dir="%s/compose/Server/x86_64/iso" % self.topdir,
                    iso_name="image-name",
                    volid="test-1.0 Server.x86_64",
                    graft_points="dummy-graft-points",
                    arch="x86_64",
                    supported=True,
                    jigdo_dir=None,
                    os_tree=None,
                    hfs_compat=False,
                    use_xorrisofs=False,
                    script_dir="%s/work/x86_64/tmp-Server" % self.topdir,
                )
            ],
        )
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        {
                            "iso_path": "%s/compose/Server/x86_64/iso/image-name"
                            % self.topdir,
                            "bootable": False,
                            "cmd": [
                                "bash",
                                self.topdir
                                + "/work/x86_64/tmp-Server/createiso-image-name.sh",
                            ],
                            "label": "",
                            "disc_num": 1,
                            "disc_count": 1,
                        },
                        compose.variants["Server"],
                        "x86_64",
                    )
                )
            ],
        )


class CreateisoThreadTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_in_runroot(self, KojiWrapper, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = {"arches": "x86_64"}
        get_runroot_cmd = KojiWrapper.return_value.get_runroot_cmd
        run_runroot = KojiWrapper.return_value.run_runroot_cmd
        run_runroot.return_value = {
            "retcode": 0,
            "output": "whatever",
            "task_id": 1234,
        }

        t = createiso.CreateIsoThread(mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        self.assertEqual(getTag.call_args_list, [mock.call("f25-build")])
        self.assertEqual(
            get_runroot_cmd.call_args_list,
            [
                mock.call(
                    "f25-build",
                    "x86_64",
                    cmd["cmd"],
                    channel=None,
                    mounts=[self.topdir],
                    packages=["coreutils", "genisoimage", "isomd5sum"],
                    use_shell=True,
                    weight=None,
                )
            ],
        )
        self.assertEqual(
            run_runroot.call_args_list,
            [
                mock.call(
                    get_runroot_cmd.return_value,
                    log_file="%s/logs/x86_64/createiso-image-name.x86_64.log"
                    % self.topdir,
                )
            ],
        )
        self.assertEqual(
            iso.get_implanted_md5.call_args_list,
            [mock.call(cmd["iso_path"], logger=compose._logger)],
        )
        self.assertEqual(iso.get_volume_id.call_args_list, [mock.call(cmd["iso_path"])])

        self.assertEqual(len(compose.im.add.call_args_list), 1)
        args, _ = compose.im.add.call_args_list[0]
        self.assertEqual(args[0], "Server")
        self.assertEqual(args[1], "x86_64")
        image = args[2]
        self.assertEqual(image.arch, "x86_64")
        self.assertEqual(image.path, "Server/x86_64/iso/image-name")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.type, "dvd")
        self.assertEqual(image.subvariant, "Server")

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_source_iso(self, KojiWrapper, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
                "create_jigdo": False,
                "runroot_weights": {"createiso": 123},
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = {"arches": "x86_64"}
        get_runroot_cmd = KojiWrapper.return_value.get_runroot_cmd
        run_runroot = KojiWrapper.return_value.run_runroot_cmd
        run_runroot.return_value = {
            "retcode": 0,
            "output": "whatever",
            "task_id": 1234,
        }

        t = createiso.CreateIsoThread(mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "src"), 1)

        self.assertEqual(getTag.call_args_list, [mock.call("f25-build")])
        self.assertEqual(
            get_runroot_cmd.call_args_list,
            [
                mock.call(
                    "f25-build",
                    "x86_64",
                    cmd["cmd"],
                    channel=None,
                    mounts=[self.topdir],
                    packages=["coreutils", "genisoimage", "isomd5sum"],
                    use_shell=True,
                    weight=123,
                )
            ],
        )
        self.assertEqual(
            run_runroot.call_args_list,
            [
                mock.call(
                    get_runroot_cmd.return_value,
                    log_file="%s/logs/src/createiso-image-name.src.log" % self.topdir,
                )
            ],
        )
        self.assertEqual(
            iso.get_implanted_md5.call_args_list,
            [mock.call(cmd["iso_path"], logger=compose._logger)],
        )
        self.assertEqual(iso.get_volume_id.call_args_list, [mock.call(cmd["iso_path"])])

        self.assertEqual(len(compose.im.add.call_args_list), 2)
        for args, _ in compose.im.add.call_args_list:
            self.assertEqual(args[0], "Server")
            self.assertIn(args[1], ["x86_64", "amd64"])
            image = args[2]
            self.assertEqual(image.arch, "src")
            self.assertEqual(image.path, "Server/x86_64/iso/image-name")
            self.assertEqual(image.format, "iso")
            self.assertEqual(image.type, "dvd")
            self.assertEqual(image.subvariant, "Server")

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_bootable(self, KojiWrapper, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "bootable": True,
                "buildinstall_method": "lorax",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": True,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = {"arches": "x86_64"}
        get_runroot_cmd = KojiWrapper.return_value.get_runroot_cmd
        run_runroot = KojiWrapper.return_value.run_runroot_cmd
        run_runroot.return_value = {
            "retcode": 0,
            "output": "whatever",
            "task_id": 1234,
        }

        t = createiso.CreateIsoThread(mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        # There is no need to call getTag if `bootable` is True.
        self.assertEqual(getTag.call_args_list, [])
        self.assertEqual(
            get_runroot_cmd.call_args_list,
            [
                mock.call(
                    "f25-build",
                    "x86_64",
                    cmd["cmd"],
                    channel=None,
                    mounts=[self.topdir],
                    packages=[
                        "coreutils",
                        "genisoimage",
                        "isomd5sum",
                        "lorax",
                        "which",
                    ],
                    use_shell=True,
                    weight=None,
                )
            ],
        )
        self.assertEqual(
            run_runroot.call_args_list,
            [
                mock.call(
                    get_runroot_cmd.return_value,
                    log_file="%s/logs/x86_64/createiso-image-name.x86_64.log"
                    % self.topdir,
                )
            ],
        )
        self.assertEqual(
            iso.get_implanted_md5.call_args_list,
            [mock.call(cmd["iso_path"], logger=compose._logger)],
        )
        self.assertEqual(iso.get_volume_id.call_args_list, [mock.call(cmd["iso_path"])])

        self.assertEqual(len(compose.im.add.call_args_list), 1)
        args, _ = compose.im.add.call_args_list[0]
        self.assertEqual(args[0], "Server")
        self.assertEqual(args[1], "x86_64")
        image = args[2]
        self.assertEqual(image.arch, "x86_64")
        self.assertEqual(image.path, "Server/x86_64/iso/image-name")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.type, "dvd")
        self.assertEqual(image.subvariant, "Server")

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_in_runroot_non_existing_tag(
        self, KojiWrapper, get_file_size, get_mtime, iso
    ):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = None

        t = createiso.CreateIsoThread(mock.Mock())
        with self.assertRaises(RuntimeError) as ctx:
            with mock.patch("time.sleep"):
                t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        self.assertEqual('Tag "f25-build" does not exist.', str(ctx.exception))

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_in_runroot_crash(self, KojiWrapper, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
                "failable_deliverables": [("^.*$", {"*": "iso"})],
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = {"arches": "x86_64"}
        run_runroot = KojiWrapper.return_value.run_runroot_cmd
        run_runroot.side_effect = helpers.boom

        pool = mock.Mock()
        t = createiso.CreateIsoThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Iso (variant Server, arch x86_64) failed, but going on anyway."  # noqa: E501
                ),
                mock.call("BOOM"),
            ]
        )

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_in_runroot_fail(self, KojiWrapper, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "runroot_tag": "f25-build",
                "koji_profile": "koji",
                "failable_deliverables": [("^.*$", {"*": "iso"})],
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        getTag = KojiWrapper.return_value.koji_proxy.getTag
        getTag.return_value = {"arches": "x86_64"}
        run_runroot = KojiWrapper.return_value.run_runroot_cmd
        run_runroot.return_value = {
            "retcode": 1,
            "output": "Nope",
            "task_id": "1234",
        }

        pool = mock.Mock()
        t = createiso.CreateIsoThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Iso (variant Server, arch x86_64) failed, but going on anyway."  # noqa: E501
                ),
                mock.call(
                    "Runroot task failed: 1234. See %s for more details."
                    % (self.topdir + "/logs/x86_64/createiso-image-name.x86_64.log")
                ),
            ]
        )

    @mock.patch("pungi.phases.createiso.iso")
    @mock.patch("pungi.phases.createiso.get_mtime")
    @mock.patch("pungi.phases.createiso.get_file_size")
    @mock.patch("pungi.runroot.run")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_locally(self, KojiWrapper, run, get_file_size, get_mtime, iso):
        compose = helpers.DummyCompose(
            self.topdir, {"release_short": "test", "release_version": "1.0"}
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        t = createiso.CreateIsoThread(mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        self.assertEqual(KojiWrapper.return_value.mock_calls, [])
        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    cmd["cmd"],
                    show_cmd=True,
                    logfile="%s/logs/x86_64/createiso-image-name.x86_64.log"
                    % self.topdir,
                )
            ],
        )
        self.assertEqual(
            iso.get_implanted_md5.call_args_list,
            [mock.call(cmd["iso_path"], logger=compose._logger)],
        )
        self.assertEqual(iso.get_volume_id.call_args_list, [mock.call(cmd["iso_path"])])

        self.assertEqual(len(compose.im.add.call_args_list), 1)
        args, _ = compose.im.add.call_args_list[0]
        self.assertEqual(args[0], "Server")
        self.assertEqual(args[1], "x86_64")
        image = args[2]
        self.assertEqual(image.arch, "x86_64")
        self.assertEqual(image.path, "Server/x86_64/iso/image-name")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.type, "dvd")
        self.assertEqual(image.subvariant, "Server")

    @mock.patch("pungi.runroot.run")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_process_locally_crash(self, KojiWrapper, run):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_short": "test",
                "release_version": "1.0",
                "failable_deliverables": [("^.*$", {"*": "iso"})],
            },
        )
        cmd = {
            "iso_path": "%s/compose/Server/x86_64/iso/image-name" % self.topdir,
            "bootable": False,
            "cmd": mock.Mock(),
            "label": "",
            "disc_num": 1,
            "disc_count": 1,
        }
        run.side_effect = helpers.boom

        pool = mock.Mock()
        t = createiso.CreateIsoThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, compose.variants["Server"], "x86_64"), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Iso (variant Server, arch x86_64) failed, but going on anyway."  # noqa: E501
                ),
                mock.call("BOOM"),
            ]
        )


TREEINFO = """
[header]
version = 1.0

[release]
name = Dummy Product
short = DP
version = 1.0

[tree]
arch = x86_64
platforms = x86_64
build_timestamp = 1464715102
variants = Server

[variant-Server]
id = Server
uid = Server
name = Server
type = variant
"""


class DummySize(object):
    """
    This is intended as a replacement for os.path.getsize that returns
    predefined sizes. The argument to __init__ should be a mapping from
    substring of filepath to size.
    """

    def __init__(self, sizes):
        self.sizes = sizes

    def __call__(self, path):
        for fragment, size in self.sizes.items():
            if fragment in path:
                return size
        return 0


class SplitIsoTest(helpers.PungiTestCase):
    def test_split_fits_on_single_disc(self):
        compose = helpers.DummyCompose(self.topdir, {})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(os.path.join(self.topdir, "work/x86_64/Server/extra-files/GPL"))
        helpers.touch(os.path.join(self.topdir, "compose/Server/x86_64/os/GPL"))
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/repodata/repomd.xml")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/b/bash.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/n/media.repo")
        )

        with mock.patch(
            "os.path.getsize",
            DummySize(
                {
                    "GPL": 20 * 2048,
                    "bash": 150 * 2048,
                    "media": 100 * 2048,
                    "treeinfo": 10 * 2048,
                }
            ),
        ):
            data = createiso.split_iso(compose, "x86_64", compose.variants["Server"])

        base_path = os.path.join(self.topdir, "compose/Server/x86_64/os")
        # GPL is sticky file, it should be first at all times. Files are
        # searched top-down, so nested ones are after top level ones.
        self.assertEqual(
            data,
            [
                {
                    "files": [
                        os.path.join(base_path, "GPL"),
                        os.path.join(base_path, ".treeinfo"),
                        os.path.join(base_path, "n/media.repo"),
                        os.path.join(base_path, "Packages/b/bash.rpm"),
                    ],
                    "size": 573440,
                }
            ],
        )

    def test_split_needs_two_discs(self):
        compose = helpers.DummyCompose(self.topdir, {})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(os.path.join(self.topdir, "work/x86_64/Server/extra-files/GPL"))
        helpers.touch(os.path.join(self.topdir, "compose/Server/x86_64/os/GPL"))
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/repodata/repomd.xml")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/b/bash.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/n/media.repo")
        )

        M = 1024**2
        G = 1024**3

        with mock.patch(
            "os.path.getsize",
            DummySize(
                {"GPL": 20 * M, "bash": 3 * G, "media": 2 * G, "treeinfo": 10 * M}
            ),
        ):
            data = createiso.split_iso(compose, "x86_64", compose.variants["Server"])

        base_path = os.path.join(self.topdir, "compose/Server/x86_64/os")
        # GPL is the only sticky file, it should be first at all times.
        # Files are searched top-down, so nested ones are after top level ones.
        self.assertEqual(
            data,
            [
                {
                    "files": [
                        os.path.join(base_path, "GPL"),
                        os.path.join(base_path, ".treeinfo"),
                        os.path.join(base_path, "n/media.repo"),
                    ],
                    "size": 2178940928,
                },
                {
                    "files": [
                        os.path.join(base_path, "GPL"),
                        os.path.join(base_path, "Packages/b/bash.rpm"),
                    ],
                    "size": 3242196992,
                },
            ],
        )

    def test_no_split_when_requested(self):
        compose = helpers.DummyCompose(self.topdir, {})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(os.path.join(self.topdir, "work/x86_64/Server/extra-files/GPL"))
        helpers.touch(os.path.join(self.topdir, "compose/Server/x86_64/os/GPL"))
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/repodata/repomd.xml")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/b/bash.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/n/media.repo")
        )

        M = 1024**2
        G = 1024**3

        with mock.patch(
            "os.path.getsize",
            DummySize(
                {"GPL": 20 * M, "bash": 3 * G, "media": 2 * G, "treeinfo": 10 * M}
            ),
        ):
            data = createiso.split_iso(
                compose, "x86_64", compose.variants["Server"], no_split=True
            )

        base_path = os.path.join(self.topdir, "compose/Server/x86_64/os")
        # GPL is the only sticky file, it should be first at all times.
        # Files are searched top-down, so nested ones are after top level ones.
        self.assertEqual(
            data,
            [
                {
                    "files": [
                        os.path.join(base_path, "GPL"),
                        os.path.join(base_path, ".treeinfo"),
                        os.path.join(base_path, "n/media.repo"),
                        os.path.join(base_path, "Packages/b/bash.rpm"),
                    ],
                    "size": 5400166400,
                }
            ],
        )
        self.assertEqual(
            compose._logger.warning.call_args_list,
            [
                mock.call(
                    "ISO for Server.x86_64 does not fit on single media! "
                    "It is 710652160 bytes too big. (Total size: 5400166400 B)"
                )
            ],
        )

    def test_keeps_reserve(self):
        compose = helpers.DummyCompose(self.topdir, {})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/spacer.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/x/pad.rpm")
        )

        M = 1024**2

        # treeinfo has size 0, spacer leaves 11M of free space, so with 10M
        # reserve the padding package should be on second disk

        with mock.patch(
            "os.path.getsize", DummySize({"spacer": 4688465664, "pad": 5 * M})
        ):
            data = createiso.split_iso(compose, "x86_64", compose.variants["Server"])

        base_path = os.path.join(self.topdir, "compose/Server/x86_64/os")
        self.assertEqual(len(data), 2)
        self.assertEqual(
            data[0]["files"],
            [
                os.path.join(base_path, ".treeinfo"),
                os.path.join(base_path, "Packages/spacer.rpm"),
            ],
        )
        self.assertEqual(
            data[1]["files"], [os.path.join(base_path, "Packages/x/pad.rpm")]
        )

    def test_can_customize_reserve(self):
        compose = helpers.DummyCompose(self.topdir, {"split_iso_reserve": 1024**2})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/spacer.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/x/pad.rpm")
        )

        M = 1024**2

        with mock.patch(
            "os.path.getsize", DummySize({"spacer": 4688465664, "pad": 5 * M})
        ):
            data = createiso.split_iso(compose, "x86_64", compose.variants["Server"])

        self.assertEqual(len(data), 1)

    def test_can_change_iso_size(self):
        compose = helpers.DummyCompose(self.topdir, {"iso_size": "8G"})
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"), TREEINFO
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/spacer.rpm")
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/Packages/x/pad.rpm")
        )

        M = 1024**2

        with mock.patch(
            "os.path.getsize", DummySize({"spacer": 4688465664, "pad": 5 * M})
        ):
            data = createiso.split_iso(compose, "x86_64", compose.variants["Server"])

        self.assertEqual(len(data), 1)


class BreakHardlinksTest(helpers.PungiTestCase):
    def setUp(self):
        super(BreakHardlinksTest, self).setUp()
        self.src = os.path.join(self.topdir, "src")
        self.stage = os.path.join(self.topdir, "stage")

    def test_not_modify_dir(self):
        p = os.path.join(self.src, "dir")
        os.makedirs(p)

        d = {"dir": p}
        createiso.break_hardlinks(d, self.stage)

        self.assertEqual(d, {"dir": p})

    def test_not_copy_file_with_one(self):
        f = os.path.join(self.src, "file")
        helpers.touch(f)

        d = {"f": f}
        createiso.break_hardlinks(d, self.stage)

        self.assertEqual(d, {"f": f})

    def test_copy(self):
        f = os.path.join(self.src, "file")
        helpers.touch(f)
        os.link(f, os.path.join(self.topdir, "file"))

        d = {"f": f}
        createiso.break_hardlinks(d, self.stage)

        expected = self.stage + f
        self.assertEqual(d, {"f": expected})
        self.assertTrue(os.path.exists(expected))


class TweakTreeinfo(helpers.PungiTestCase):
    def test_tweaking(self):
        input = os.path.join(helpers.FIXTURE_DIR, "original-treeinfo")
        expected = os.path.join(helpers.FIXTURE_DIR, "expected-treeinfo")
        output = os.path.join(self.topdir, "output")

        ti = createiso.load_and_tweak_treeinfo(input)
        ti.dump(output)

        self.assertFilesEqual(output, expected)


class CreateisoTryReusePhaseTest(helpers.PungiTestCase):
    def setUp(self):
        super(CreateisoTryReusePhaseTest, self).setUp()
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler(os.devnull))

    def test_disabled(self):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": False})
        phase = createiso.CreateisoPhase(compose, mock.Mock())

        self.assertFalse(phase.try_reuse(mock.Mock(), "Server", "x86_64", mock.Mock()))

    def test_buildinstall_changed(self):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        phase.bi = mock.Mock()
        phase.bi.reused.return_value = False
        cmd = {"disc_num": 1, "disc_count": 1}
        opts = CreateIsoOpts(buildinstall_method="lorax")

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    def test_no_old_config(self):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        cmd = {"disc_num": 1, "disc_count": 1}
        opts = CreateIsoOpts()

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    def test_old_config_changed(self):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        old_config = compose.conf.copy()
        old_config["release_version"] = "2"
        compose.load_old_compose_config.return_value = old_config
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        cmd = {"disc_num": 1, "disc_count": 1}
        opts = CreateIsoOpts()

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    def test_no_old_metadata(self):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        cmd = {"disc_num": 1, "disc_count": 1}
        opts = CreateIsoOpts()

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    @mock.patch("pungi.phases.createiso.read_json_file")
    def test_volume_id_differs(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        cmd = {"disc_num": 1, "disc_count": 1}

        opts = CreateIsoOpts(volid="new-volid")

        read_json_file.return_value = {"opts": {"volid": "old-volid"}}

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    @mock.patch("pungi.phases.createiso.read_json_file")
    def test_packages_differ(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        cmd = {"disc_num": 1, "disc_count": 1}

        new_graft_points = os.path.join(self.topdir, "new_graft_points")
        helpers.touch(new_graft_points, "Packages/f/foo-1-1.x86_64.rpm\n")
        opts = CreateIsoOpts(graft_points=new_graft_points, volid="volid")

        old_graft_points = os.path.join(self.topdir, "old_graft_points")
        helpers.touch(old_graft_points, "Packages/f/foo-1-2.x86_64.rpm\n")
        read_json_file.return_value = {
            "opts": {"graft_points": old_graft_points, "volid": "volid"}
        }

        self.assertFalse(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )

    @mock.patch("pungi.phases.createiso.read_json_file")
    def test_runs_perform_reuse(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        phase.logger = self.logger
        phase.perform_reuse = mock.Mock()
        cmd = {"disc_num": 1, "disc_count": 1}

        new_graft_points = os.path.join(self.topdir, "new_graft_points")
        helpers.touch(new_graft_points)
        opts = CreateIsoOpts(graft_points=new_graft_points, volid="volid")

        old_graft_points = os.path.join(self.topdir, "old_graft_points")
        helpers.touch(old_graft_points)
        dummy_iso_path = "dummy-iso-path"
        read_json_file.return_value = {
            "opts": {
                "graft_points": old_graft_points,
                "volid": "volid",
            },
            "cmd": {"iso_path": dummy_iso_path},
        }

        self.assertTrue(
            phase.try_reuse(cmd, compose.variants["Server"], "x86_64", opts)
        )
        self.assertEqual(
            phase.perform_reuse.call_args_list,
            [
                mock.call(
                    cmd,
                    compose.variants["Server"],
                    "x86_64",
                    opts,
                    dummy_iso_path,
                )
            ],
        )


@mock.patch("pungi.phases.createiso.OldFileLinker")
@mock.patch("pungi.phases.createiso.add_iso_to_metadata")
class CreateisoPerformReusePhaseTest(helpers.PungiTestCase):
    def test_success(self, add_iso_to_metadata, OldFileLinker):
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        cmd = {
            "iso_path": "target/image.iso",
            "bootable": False,
            "disc_num": 1,
            "disc_count": 2,
        }
        opts = CreateIsoOpts()

        phase.perform_reuse(
            cmd,
            compose.variants["Server"],
            "x86_64",
            opts,
            "old/image.iso",
        )

        self.assertEqual(
            add_iso_to_metadata.call_args_list,
            [
                mock.call(
                    compose,
                    compose.variants["Server"],
                    "x86_64",
                    cmd["iso_path"],
                    bootable=False,
                    disc_count=2,
                    disc_num=1,
                ),
            ],
        )
        self.assertEqual(
            OldFileLinker.return_value.mock_calls,
            [
                mock.call.link("old/image.iso", "target/image.iso"),
                mock.call.link("old/image.iso.manifest", "target/image.iso.manifest"),
                # The old log file doesn't exist in the test scenario.
                mock.call.link(
                    None,
                    os.path.join(
                        self.topdir, "logs/x86_64/createiso-image.iso.x86_64.log"
                    ),
                ),
            ],
        )

    def test_failure(self, add_iso_to_metadata, OldFileLinker):
        OldFileLinker.return_value.link.side_effect = helpers.mk_boom()
        compose = helpers.DummyCompose(self.topdir, {"createiso_allow_reuse": True})
        phase = createiso.CreateisoPhase(compose, mock.Mock())
        cmd = {
            "iso_path": "target/image.iso",
            "bootable": False,
            "disc_num": 1,
            "disc_count": 2,
        }
        opts = CreateIsoOpts()

        with self.assertRaises(Exception):
            phase.perform_reuse(
                cmd,
                compose.variants["Server"],
                "x86_64",
                opts,
                "old/image.iso",
            )

        self.assertEqual(add_iso_to_metadata.call_args_list, [])
        self.assertEqual(
            OldFileLinker.return_value.mock_calls,
            [
                mock.call.link("old/image.iso", "target/image.iso"),
                mock.call.abort(),
            ],
        )


class ComposeConfGetIsoLevelTest(helpers.PungiTestCase):
    def test_global_config(self):
        compose = helpers.DummyCompose(self.topdir, {"iso_level": 3})

        self.assertEqual(
            createiso.get_iso_level_config(
                compose, compose.variants["Server"], "x86_64"
            ),
            3,
        )

    def test_src_only_config(self):
        compose = helpers.DummyCompose(
            self.topdir,
            {"iso_level": [(".*", {"src": 4})]},
        )

        self.assertEqual(
            createiso.get_iso_level_config(compose, compose.variants["Server"], "src"),
            4,
        )

    def test_no_match(self):
        compose = helpers.DummyCompose(
            self.topdir,
            {"iso_level": [("^Server$", {"*": 4})]},
        )

        self.assertIsNone(
            createiso.get_iso_level_config(
                compose, compose.variants["Client"], "x86_64"
            ),
        )
