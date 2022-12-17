# -*- coding: utf-8 -*-

import logging
import mock
import six

import os

from tests import helpers
from pungi.createiso import CreateIsoOpts
from pungi.phases import extra_isos


@mock.patch("pungi.phases.extra_isos.ThreadPool")
class ExtraIsosPhaseTest(helpers.PungiTestCase):
    def test_logs_extra_arches(self, ThreadPool):
        cfg = {
            "include_variants": ["Client"],
            "arches": ["x86_64", "ppc64le", "aarch64"],
        }
        compose = helpers.DummyCompose(self.topdir, {"extra_isos": {"^Server$": [cfg]}})

        phase = extra_isos.ExtraIsosPhase(compose, mock.Mock())
        phase.validate()

        self.assertEqual(len(compose.log_warning.call_args_list), 1)

    def test_one_task_for_each_arch(self, ThreadPool):
        cfg = {
            "include_variants": ["Client"],
        }
        compose = helpers.DummyCompose(self.topdir, {"extra_isos": {"^Server$": [cfg]}})

        phase = extra_isos.ExtraIsosPhase(compose, mock.Mock())
        phase.run()

        self.assertEqual(len(ThreadPool.return_value.add.call_args_list), 3)
        six.assertCountEqual(
            self,
            ThreadPool.return_value.queue_put.call_args_list,
            [
                mock.call((compose, cfg, compose.variants["Server"], "x86_64")),
                mock.call((compose, cfg, compose.variants["Server"], "amd64")),
                mock.call((compose, cfg, compose.variants["Server"], "src")),
            ],
        )

    def test_filter_arches(self, ThreadPool):
        cfg = {
            "include_variants": ["Client"],
            "arches": ["x86_64"],
        }
        compose = helpers.DummyCompose(self.topdir, {"extra_isos": {"^Server$": [cfg]}})

        phase = extra_isos.ExtraIsosPhase(compose, mock.Mock())
        phase.run()

        self.assertEqual(len(ThreadPool.return_value.add.call_args_list), 2)
        six.assertCountEqual(
            self,
            ThreadPool.return_value.queue_put.call_args_list,
            [
                mock.call((compose, cfg, compose.variants["Server"], "x86_64")),
                mock.call((compose, cfg, compose.variants["Server"], "src")),
            ],
        )

    def test_skip_source(self, ThreadPool):
        cfg = {
            "include_variants": ["Client"],
            "skip_src": True,
        }
        compose = helpers.DummyCompose(self.topdir, {"extra_isos": {"^Server$": [cfg]}})

        phase = extra_isos.ExtraIsosPhase(compose, mock.Mock())
        phase.run()

        self.assertEqual(len(ThreadPool.return_value.add.call_args_list), 2)
        six.assertCountEqual(
            self,
            ThreadPool.return_value.queue_put.call_args_list,
            [
                mock.call((compose, cfg, compose.variants["Server"], "x86_64")),
                mock.call((compose, cfg, compose.variants["Server"], "amd64")),
            ],
        )


@mock.patch("pungi.phases.extra_isos.prepare_media_metadata")
@mock.patch("pungi.phases.extra_isos.get_volume_id")
@mock.patch("pungi.phases.extra_isos.get_filename")
@mock.patch("pungi.phases.extra_isos.get_iso_contents")
@mock.patch("pungi.phases.extra_isos.get_extra_files")
@mock.patch("pungi.phases.extra_isos.run_createiso_command")
@mock.patch("pungi.phases.extra_isos.add_iso_to_metadata")
class ExtraIsosThreadTest(helpers.PungiTestCase):
    def test_binary_bootable_image(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(
            self.topdir, {"bootable": True, "buildinstall_method": "lorax"}
        )
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(
            gfn.call_args_list, [mock.call(compose, server, "x86_64", None)]
        )
        self.assertEqual(gvi.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(gef.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(
            gic.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    ["Client"],
                    "my.iso",
                    bootable=True,
                    inherit_extra_files=False,
                ),
            ],
        )
        self.assertEqual(
            rcc.call_args_list,
            [
                mock.call(
                    1,
                    compose,
                    True,
                    "x86_64",
                    [
                        "bash",
                        os.path.join(
                            self.topdir, "work/x86_64/tmp-Server/extraiso-my.iso.sh"
                        ),
                    ],
                    [self.topdir],
                    log_file=os.path.join(
                        self.topdir, "logs/x86_64/extraiso-my.iso.x86_64.log"
                    ),
                )
            ],
        )
        self.assertEqual(
            aitm.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    os.path.join(self.topdir, "compose/Server/x86_64/iso/my.iso"),
                    True,
                    additional_variants=["Client"],
                )
            ],
        )
        self.assertEqual(pmm.call_args_list, [mock.call(compose, server, "x86_64")])

    def test_binary_bootable_image_without_jigdo(
        self, aitm, rcc, gef, gic, gfn, gvi, pmm
    ):
        compose = helpers.DummyCompose(
            self.topdir,
            {"bootable": True, "buildinstall_method": "lorax", "create_jigdo": False},
        )
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(
            gfn.call_args_list, [mock.call(compose, server, "x86_64", None)]
        )
        self.assertEqual(gvi.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(gef.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(
            gic.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    ["Client"],
                    "my.iso",
                    bootable=True,
                    inherit_extra_files=False,
                ),
            ],
        )
        self.assertEqual(
            rcc.call_args_list,
            [
                mock.call(
                    1,
                    compose,
                    True,
                    "x86_64",
                    [
                        "bash",
                        os.path.join(
                            self.topdir, "work/x86_64/tmp-Server/extraiso-my.iso.sh"
                        ),
                    ],
                    [self.topdir],
                    log_file=os.path.join(
                        self.topdir, "logs/x86_64/extraiso-my.iso.x86_64.log"
                    ),
                )
            ],
        )
        self.assertEqual(
            aitm.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    os.path.join(self.topdir, "compose/Server/x86_64/iso/my.iso"),
                    True,
                    additional_variants=["Client"],
                )
            ],
        )
        self.assertEqual(pmm.call_args_list, [mock.call(compose, server, "x86_64")])

    def test_image_with_max_size(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(
            self.topdir, {"bootable": True, "buildinstall_method": "lorax"}
        )
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
            "max_size": 15,
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(
            gfn.call_args_list, [mock.call(compose, server, "x86_64", None)]
        )
        self.assertEqual(gvi.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(gef.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(
            gic.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    ["Client"],
                    "my.iso",
                    bootable=True,
                    inherit_extra_files=False,
                ),
            ],
        )
        self.assertEqual(
            rcc.call_args_list,
            [
                mock.call(
                    1,
                    compose,
                    True,
                    "x86_64",
                    [
                        "bash",
                        os.path.join(
                            self.topdir, "work/x86_64/tmp-Server/extraiso-my.iso.sh"
                        ),
                    ],
                    [self.topdir],
                    log_file=os.path.join(
                        self.topdir, "logs/x86_64/extraiso-my.iso.x86_64.log"
                    ),
                )
            ],
        )
        self.assertEqual(
            aitm.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    os.path.join(self.topdir, "compose/Server/x86_64/iso/my.iso"),
                    True,
                    additional_variants=["Client"],
                )
            ],
        )
        self.assertEqual(aitm.return_value._max_size, 15)
        self.assertEqual(pmm.call_args_list, [mock.call(compose, server, "x86_64")])

    def test_binary_image_custom_naming(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(self.topdir, {})
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
            "filename": "fn",
            "volid": ["v1", "v2"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(
            gfn.call_args_list, [mock.call(compose, server, "x86_64", "fn")]
        )
        self.assertEqual(
            gvi.call_args_list, [mock.call(compose, server, "x86_64", ["v1", "v2"])]
        )
        self.assertEqual(gef.call_args_list, [mock.call(compose, server, "x86_64", [])])
        self.assertEqual(
            gic.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    ["Client"],
                    "my.iso",
                    bootable=False,
                    inherit_extra_files=False,
                ),
            ],
        )
        self.assertEqual(
            rcc.call_args_list,
            [
                mock.call(
                    1,
                    compose,
                    False,
                    "x86_64",
                    [
                        "bash",
                        os.path.join(
                            self.topdir, "work/x86_64/tmp-Server/extraiso-my.iso.sh"
                        ),
                    ],
                    [self.topdir],
                    log_file=os.path.join(
                        self.topdir, "logs/x86_64/extraiso-my.iso.x86_64.log"
                    ),
                )
            ],
        )
        self.assertEqual(
            aitm.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "x86_64",
                    os.path.join(self.topdir, "compose/Server/x86_64/iso/my.iso"),
                    False,
                    additional_variants=["Client"],
                )
            ],
        )
        self.assertEqual(pmm.call_args_list, [mock.call(compose, server, "x86_64")])

    def test_source_is_not_bootable(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(
            self.topdir, {"bootable": True, "buildinstall_method": "lorax"}
        )
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "src"), 1)

        self.assertEqual(gfn.call_args_list, [mock.call(compose, server, "src", None)])
        self.assertEqual(gvi.call_args_list, [mock.call(compose, server, "src", [])])
        self.assertEqual(gef.call_args_list, [mock.call(compose, server, "src", [])])
        self.assertEqual(
            gic.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "src",
                    ["Client"],
                    "my.iso",
                    bootable=False,
                    inherit_extra_files=False,
                ),
            ],
        )
        self.assertEqual(
            rcc.call_args_list,
            [
                mock.call(
                    1,
                    compose,
                    False,
                    "src",
                    [
                        "bash",
                        os.path.join(
                            self.topdir, "work/src/tmp-Server/extraiso-my.iso.sh"
                        ),
                    ],
                    [self.topdir],
                    log_file=os.path.join(
                        self.topdir, "logs/src/extraiso-my.iso.src.log"
                    ),
                )
            ],
        )
        self.assertEqual(
            aitm.call_args_list,
            [
                mock.call(
                    compose,
                    server,
                    "src",
                    os.path.join(self.topdir, "compose/Server/source/iso/my.iso"),
                    False,
                    additional_variants=["Client"],
                )
            ],
        )
        self.assertEqual(pmm.call_args_list, [mock.call(compose, server, "src")])

    def test_failable_failed(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(self.topdir, {})
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
            "failable_arches": ["x86_64"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"
        rcc.side_effect = helpers.mk_boom()

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with mock.patch("time.sleep"):
            t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(aitm.call_args_list, [])

    def test_non_failable_failed(self, aitm, rcc, gef, gic, gfn, gvi, pmm):
        compose = helpers.DummyCompose(self.topdir, {})
        server = compose.variants["Server"]
        cfg = {
            "include_variants": ["Client"],
        }

        gfn.return_value = "my.iso"
        gvi.return_value = "my volume id"
        gic.return_value = "/tmp/iso-graft-points"
        rcc.side_effect = helpers.mk_boom(RuntimeError)

        t = extra_isos.ExtraIsosThread(mock.Mock(), mock.Mock())
        with self.assertRaises(RuntimeError):
            with mock.patch("time.sleep"):
                t.process((compose, cfg, server, "x86_64"), 1)

        self.assertEqual(aitm.call_args_list, [])


@mock.patch("pungi.metadata.populate_extra_files_metadata")
@mock.patch("pungi.phases.extra_isos.get_file_from_scm")
@mock.patch("pungi.phases.extra_isos.get_dir_from_scm")
class GetExtraFilesTest(helpers.PungiTestCase):
    def setUp(self):
        super(GetExtraFilesTest, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.variant = self.compose.variants["Server"]
        self.arch = "x86_64"
        self.dir = os.path.join(
            self.topdir, "work", self.arch, self.variant.uid, "extra-iso-extra-files"
        )

    def test_no_config(self, get_dir, get_file, populate_md):
        extra_isos.get_extra_files(self.compose, self.variant, self.arch, [])

        self.assertEqual(get_dir.call_args_list, [])
        self.assertEqual(get_file.call_args_list, [])
        self.assertEqual(populate_md.call_args_list, [])

    def test_get_file(self, get_dir, get_file, populate_md):
        get_file.return_value = ["GPL"]
        cfg = {
            "scm": "git",
            "repo": "https://pagure.io/pungi.git",
            "file": "GPL",
            "target": "legalese",
        }
        extra_isos.get_extra_files(self.compose, self.variant, self.arch, [cfg])

        self.assertEqual(get_dir.call_args_list, [])
        self.assertEqual(
            get_file.call_args_list,
            [mock.call(cfg, os.path.join(self.dir, "legalese"), compose=self.compose)],
        )
        self.assertEqual(
            populate_md.call_args_list,
            [
                mock.call(
                    mock.ANY,
                    self.variant,
                    self.arch,
                    self.dir,
                    ["legalese/GPL"],
                    self.compose.conf["media_checksums"],
                )
            ],
        )

    def test_get_dir(self, get_dir, get_file, populate_md):
        get_dir.return_value = ["a", "b"]
        cfg = {
            "scm": "git",
            "repo": "https://pagure.io/pungi.git",
            "dir": "docs",
            "target": "foo",
        }
        extra_isos.get_extra_files(self.compose, self.variant, self.arch, [cfg])

        self.assertEqual(get_file.call_args_list, [])
        self.assertEqual(
            get_dir.call_args_list,
            [mock.call(cfg, os.path.join(self.dir, "foo"), compose=self.compose)],
        )
        self.assertEqual(
            populate_md.call_args_list,
            [
                mock.call(
                    mock.ANY,
                    self.variant,
                    self.arch,
                    self.dir,
                    ["foo/a", "foo/b"],
                    self.compose.conf["media_checksums"],
                ),
            ],
        )

    def test_get_multiple_files(self, get_dir, get_file, populate_md):
        get_file.side_effect = [["GPL"], ["setup.py"]]
        cfg1 = {
            "scm": "git",
            "repo": "https://pagure.io/pungi.git",
            "file": "GPL",
            "target": "legalese",
        }
        cfg2 = {"scm": "git", "repo": "https://pagure.io/pungi.git", "file": "setup.py"}
        extra_isos.get_extra_files(self.compose, self.variant, self.arch, [cfg1, cfg2])

        self.assertEqual(get_dir.call_args_list, [])
        self.assertEqual(
            get_file.call_args_list,
            [
                mock.call(
                    cfg1,
                    os.path.join(self.dir, "legalese"),
                    compose=self.compose,
                ),
                mock.call(cfg2, self.dir, compose=self.compose),
            ],
        )
        self.assertEqual(
            populate_md.call_args_list,
            [
                mock.call(
                    mock.ANY,
                    self.variant,
                    self.arch,
                    self.dir,
                    ["legalese/GPL", "setup.py"],
                    self.compose.conf["media_checksums"],
                ),
            ],
        )


@mock.patch("pungi.phases.extra_isos.tweak_treeinfo")
@mock.patch("pungi.wrappers.iso.write_graft_points")
@mock.patch("pungi.wrappers.iso.get_graft_points")
class GetIsoContentsTest(helpers.PungiTestCase):
    def setUp(self):
        super(GetIsoContentsTest, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.variant = self.compose.variants["Server"]

    def test_non_bootable_binary(self, ggp, wgp, tt):
        gp = {
            "compose/Client/x86_64/os/Packages": {"f/foo.rpm": "/mnt/f/foo.rpm"},
            "compose/Client/x86_64/os/repodata": {
                "primary.xml": "/mnt/repodata/primary.xml"
            },
            "compose/Server/x86_64/os/Packages": {"b/bar.rpm": "/mnt/b/bar.rpm"},
            "compose/Server/x86_64/os/repodata": {
                "repomd.xml": "/mnt/repodata/repomd.xml"
            },
            "work/x86_64/Server/extra-iso-extra-files": {"EULA": "/mnt/EULA"},
        }

        ggp.side_effect = lambda compose, x: gp[x[0][len(self.topdir) + 1 :]]
        gp_file = os.path.join(self.topdir, "work/x86_64/iso/my.iso-graft-points")

        self.assertEqual(
            extra_isos.get_iso_contents(
                self.compose,
                self.variant,
                "x86_64",
                ["Client"],
                "my.iso",
                False,
                inherit_extra_files=False,
            ),
            gp_file,
        )

        expected = {
            "Client/Packages/f/foo.rpm": "/mnt/f/foo.rpm",
            "Client/repodata/primary.xml": "/mnt/repodata/primary.xml",
            "EULA": "/mnt/EULA",
            "Server/Packages/b/bar.rpm": "/mnt/b/bar.rpm",
            "Server/repodata/repomd.xml": "/mnt/repodata/repomd.xml",
        }

        six.assertCountEqual(
            self,
            ggp.call_args_list,
            [
                mock.call(
                    self.compose.paths.compose.topdir(), [os.path.join(self.topdir, x)]
                )
                for x in gp
            ],
        )
        self.assertEqual(len(wgp.call_args_list), 1)
        self.assertEqual(wgp.call_args_list[0][0][0], gp_file)
        self.assertDictEqual(dict(wgp.call_args_list[0][0][1]), expected)
        self.assertEqual(
            wgp.call_args_list[0][1], {"exclude": ["*/lost+found", "*/boot.iso"]}
        )

        # Check correct call to tweak_treeinfo
        self.assertEqual(
            tt.call_args_list,
            [
                mock.call(
                    self.compose,
                    ["Client"],
                    os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"),
                    os.path.join(
                        self.topdir,
                        "work/x86_64/Server/extra-iso-extra-files/.treeinfo",
                    ),
                ),
            ],
        )

    def test_inherit_extra_files(self, ggp, wgp, tt):
        gp = {
            "compose/Client/x86_64/os/Packages": {"f/foo.rpm": "/mnt/f/foo.rpm"},
            "compose/Client/x86_64/os/repodata": {
                "primary.xml": "/mnt/repodata/primary.xml"
            },
            "compose/Server/x86_64/os/Packages": {"b/bar.rpm": "/mnt/b/bar.rpm"},
            "compose/Server/x86_64/os/repodata": {
                "repomd.xml": "/mnt/repodata/repomd.xml"
            },
            "work/x86_64/Client/extra-files": {"GPL": "/mnt/GPL"},
            "work/x86_64/Server/extra-files": {"AUTHORS": "/mnt/AUTHORS"},
            "work/x86_64/Server/extra-iso-extra-files": {"EULA": "/mnt/EULA"},
        }

        ggp.side_effect = lambda compose, x: gp[x[0][len(self.topdir) + 1 :]]
        gp_file = os.path.join(self.topdir, "work/x86_64/iso/my.iso-graft-points")

        self.assertEqual(
            extra_isos.get_iso_contents(
                self.compose,
                self.variant,
                "x86_64",
                ["Client"],
                "my.iso",
                False,
                inherit_extra_files=True,
            ),
            gp_file,
        )

        expected = {
            "Client/GPL": "/mnt/GPL",
            "Client/Packages/f/foo.rpm": "/mnt/f/foo.rpm",
            "Client/repodata/primary.xml": "/mnt/repodata/primary.xml",
            "EULA": "/mnt/EULA",
            "Server/AUTHORS": "/mnt/AUTHORS",
            "Server/Packages/b/bar.rpm": "/mnt/b/bar.rpm",
            "Server/repodata/repomd.xml": "/mnt/repodata/repomd.xml",
        }

        six.assertCountEqual(
            self,
            ggp.call_args_list,
            [
                mock.call(
                    self.compose.paths.compose.topdir(), [os.path.join(self.topdir, x)]
                )
                for x in gp
            ],
        )
        self.assertEqual(len(wgp.call_args_list), 1)
        self.assertEqual(wgp.call_args_list[0][0][0], gp_file)
        self.assertDictEqual(dict(wgp.call_args_list[0][0][1]), expected)
        self.assertEqual(
            wgp.call_args_list[0][1], {"exclude": ["*/lost+found", "*/boot.iso"]}
        )

        # Check correct call to tweak_treeinfo
        self.assertEqual(
            tt.call_args_list,
            [
                mock.call(
                    self.compose,
                    ["Client"],
                    os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"),
                    os.path.join(
                        self.topdir,
                        "work/x86_64/Server/extra-iso-extra-files/.treeinfo",
                    ),
                ),
            ],
        )

    def test_source(self, ggp, wgp, tt):
        gp = {
            "compose/Client/source/tree/Packages": {"f/foo.rpm": "/mnt/f/foo.rpm"},
            "compose/Client/source/tree/repodata": {
                "primary.xml": "/mnt/repodata/primary.xml"
            },
            "compose/Server/source/tree/Packages": {"b/bar.rpm": "/mnt/b/bar.rpm"},
            "compose/Server/source/tree/repodata": {
                "repomd.xml": "/mnt/repodata/repomd.xml"
            },
            "work/src/Server/extra-iso-extra-files": {"EULA": "/mnt/EULA"},
        }

        ggp.side_effect = lambda compose, x: gp[x[0][len(self.topdir) + 1 :]]
        gp_file = os.path.join(self.topdir, "work/src/iso/my.iso-graft-points")

        self.assertEqual(
            extra_isos.get_iso_contents(
                self.compose,
                self.variant,
                "src",
                ["Client"],
                "my.iso",
                bootable=False,
                inherit_extra_files=False,
            ),
            gp_file,
        )

        expected = {
            "Client/Packages/f/foo.rpm": "/mnt/f/foo.rpm",
            "Client/repodata/primary.xml": "/mnt/repodata/primary.xml",
            "EULA": "/mnt/EULA",
            "Server/Packages/b/bar.rpm": "/mnt/b/bar.rpm",
            "Server/repodata/repomd.xml": "/mnt/repodata/repomd.xml",
        }

        six.assertCountEqual(
            self,
            ggp.call_args_list,
            [
                mock.call(
                    self.compose.paths.compose.topdir(), [os.path.join(self.topdir, x)]
                )
                for x in gp
            ],
        )
        self.assertEqual(len(wgp.call_args_list), 1)
        self.assertEqual(wgp.call_args_list[0][0][0], gp_file)
        self.assertDictEqual(dict(wgp.call_args_list[0][0][1]), expected)
        self.assertEqual(
            wgp.call_args_list[0][1], {"exclude": ["*/lost+found", "*/boot.iso"]}
        )

        # Check correct call to tweak_treeinfo
        self.assertEqual(
            tt.call_args_list,
            [
                mock.call(
                    self.compose,
                    ["Client"],
                    os.path.join(self.topdir, "compose/Server/source/tree/.treeinfo"),
                    os.path.join(
                        self.topdir,
                        "work/src/Server/extra-iso-extra-files/.treeinfo",
                    ),
                ),
            ],
        )

    def test_bootable(self, ggp, wgp, tt):
        self.compose.conf["buildinstall_method"] = "lorax"

        bi_dir = os.path.join(self.topdir, "work/x86_64/buildinstall/Server")
        iso_dir = os.path.join(self.topdir, "work/x86_64/iso/my.iso")
        helpers.touch(os.path.join(bi_dir, "isolinux/isolinux.bin"))
        helpers.touch(os.path.join(bi_dir, "images/boot.img"))
        helpers.touch(os.path.join(bi_dir, "images/efiboot.img"))

        gp = {
            "compose/Client/x86_64/os/Packages": {"f/foo.rpm": "/mnt/f/foo.rpm"},
            "compose/Client/x86_64/os/repodata": {
                "primary.xml": "/mnt/repodata/primary.xml"
            },
            "compose/Server/x86_64/os/Packages": {"b/bar.rpm": "/mnt/b/bar.rpm"},
            "compose/Server/x86_64/os/repodata": {
                "repomd.xml": "/mnt/repodata/repomd.xml"
            },
            "work/x86_64/Server/extra-iso-extra-files": {"EULA": "/mnt/EULA"},
        }
        bi_gp = {
            "isolinux/isolinux.bin": os.path.join(iso_dir, "isolinux/isolinux.bin"),
            "images/boot.img": os.path.join(iso_dir, "images/boot.img"),
            "images/efiboot.img": os.path.join(iso_dir, "images/efiboot.img"),
        }

        ggp.side_effect = (
            lambda compose, x: gp[x[0][len(self.topdir) + 1 :]]
            if len(x) == 1
            else bi_gp
        )
        gp_file = os.path.join(self.topdir, "work/x86_64/iso/my.iso-graft-points")

        self.assertEqual(
            extra_isos.get_iso_contents(
                self.compose,
                self.variant,
                "x86_64",
                ["Client"],
                "my.iso",
                bootable=True,
                inherit_extra_files=False,
            ),
            gp_file,
        )

        self.maxDiff = None

        expected = {
            "Client/Packages/f/foo.rpm": "/mnt/f/foo.rpm",
            "Client/repodata/primary.xml": "/mnt/repodata/primary.xml",
            "EULA": "/mnt/EULA",
            "Server/Packages/b/bar.rpm": "/mnt/b/bar.rpm",
            "Server/repodata/repomd.xml": "/mnt/repodata/repomd.xml",
            "isolinux/isolinux.bin": os.path.join(iso_dir, "isolinux/isolinux.bin"),
            "images/boot.img": os.path.join(iso_dir, "images/boot.img"),
            "images/efiboot.img": os.path.join(
                self.topdir,
                "compose",
                self.variant.uid,
                "x86_64/os/images/efiboot.img",
            ),
        }

        six.assertCountEqual(
            self,
            ggp.call_args_list,
            [
                mock.call(
                    self.compose.paths.compose.topdir(), [os.path.join(self.topdir, x)]
                )
                for x in gp
            ]
            + [mock.call(self.compose.paths.compose.topdir(), [bi_dir, iso_dir])],
        )
        self.assertEqual(len(wgp.call_args_list), 1)
        self.assertEqual(wgp.call_args_list[0][0][0], gp_file)
        self.assertDictEqual(dict(wgp.call_args_list[0][0][1]), expected)
        self.assertEqual(
            wgp.call_args_list[0][1], {"exclude": ["*/lost+found", "*/boot.iso"]}
        )

        # Check files were copied to temp directory
        self.assertTrue(os.path.exists(os.path.join(iso_dir, "isolinux/isolinux.bin")))
        self.assertTrue(os.path.exists(os.path.join(iso_dir, "images/boot.img")))

        # Check correct call to tweak_treeinfo
        self.assertEqual(
            tt.call_args_list,
            [
                mock.call(
                    self.compose,
                    ["Client"],
                    os.path.join(self.topdir, "compose/Server/x86_64/os/.treeinfo"),
                    os.path.join(
                        self.topdir,
                        "work/x86_64/Server/extra-iso-extra-files/.treeinfo",
                    ),
                ),
            ],
        )


class GetFilenameTest(helpers.PungiTestCase):
    def test_use_original_name(self):
        compose = helpers.DummyCompose(self.topdir, {})

        fn = extra_isos.get_filename(
            compose,
            compose.variants["Server"],
            "x86_64",
            "foo-{variant}-{arch}-{filename}",
        )

        self.assertEqual(fn, "foo-Server-x86_64-image-name")

    def test_use_default_without_format(self):
        compose = helpers.DummyCompose(self.topdir, {})

        fn = extra_isos.get_filename(
            compose, compose.variants["Server"], "x86_64", None
        )

        self.assertEqual(fn, "image-name")

    def test_reports_unknown_placeholder(self):
        compose = helpers.DummyCompose(self.topdir, {})

        with self.assertRaises(RuntimeError) as ctx:
            extra_isos.get_filename(
                compose, compose.variants["Server"], "x86_64", "foo-{boom}"
            )

        self.assertIn("boom", str(ctx.exception))


class GetVolumeIDTest(helpers.PungiTestCase):
    def test_use_original_volume_id(self):
        compose = helpers.DummyCompose(self.topdir, {})

        volid = extra_isos.get_volume_id(
            compose, compose.variants["Server"], "x86_64", "f-{volid}"
        )

        self.assertEqual(volid, "f-test-1.0 Server.x86_64")

    def test_falls_back_to_shorter(self):
        compose = helpers.DummyCompose(self.topdir, {})

        volid = extra_isos.get_volume_id(
            compose,
            compose.variants["Server"],
            "x86_64",
            ["long-foobar-{volid}", "f-{volid}"],
        )

        self.assertEqual(volid, "f-test-1.0 Server.x86_64")

    def test_reports_unknown_placeholder(self):
        compose = helpers.DummyCompose(self.topdir, {})

        with self.assertRaises(RuntimeError) as ctx:
            extra_isos.get_volume_id(
                compose, compose.variants["Server"], "x86_64", "f-{boom}"
            )

        self.assertIn("boom", str(ctx.exception))


class TweakTreeinfoTest(helpers.PungiTestCase):
    def test_tweak(self):
        compose = helpers.DummyCompose(self.topdir, {})
        input = os.path.join(helpers.FIXTURE_DIR, "extraiso.treeinfo")
        output = os.path.join(self.topdir, "actual-treeinfo")
        expected = os.path.join(helpers.FIXTURE_DIR, "extraiso-expected.treeinfo")
        extra_isos.tweak_treeinfo(compose, ["Client"], input, output)

        self.assertFilesEqual(output, expected)


class PrepareMetadataTest(helpers.PungiTestCase):
    @mock.patch("pungi.metadata.create_media_repo")
    @mock.patch("pungi.metadata.create_discinfo")
    @mock.patch("pungi.metadata.get_description")
    def test_write_files(self, get_description, create_discinfo, create_media_repo):
        compose = helpers.DummyCompose(self.topdir, {})
        variant = compose.variants["Server"]
        arch = "x86_64"

        extra_isos.prepare_media_metadata(compose, variant, arch)

        self.assertEqual(
            get_description.call_args_list, [mock.call(compose, variant, arch)]
        )
        self.assertEqual(
            create_discinfo.call_args_list,
            [
                mock.call(
                    os.path.join(
                        self.topdir,
                        "work/x86_64/Server/extra-iso-extra-files/.discinfo",
                    ),
                    get_description.return_value,
                    arch,
                )
            ],
        )
        self.assertEqual(
            create_media_repo.call_args_list,
            [
                mock.call(
                    os.path.join(
                        self.topdir,
                        "work/x86_64/Server/extra-iso-extra-files/media.repo",
                    ),
                    get_description.return_value,
                    timestamp=None,
                ),
            ],
        )


class ExtraisoTryReusePhaseTest(helpers.PungiTestCase):
    def setUp(self):
        super(ExtraisoTryReusePhaseTest, self).setUp()
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler(os.devnull))

    def test_disabled(self):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": False})
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        opts = CreateIsoOpts()

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    def test_buildinstall_changed(self):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger
        thread.bi = mock.Mock()
        thread.bi.reused.return_value = False
        opts = CreateIsoOpts(buildinstall_method="lorax")

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    def test_no_old_config(self):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger
        opts = CreateIsoOpts()

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    def test_old_config_changed(self):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        old_config = compose.conf.copy()
        old_config["release_version"] = "2"
        compose.load_old_compose_config.return_value = old_config
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger
        opts = CreateIsoOpts()

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    def test_no_old_metadata(self):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger
        opts = CreateIsoOpts()

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    @mock.patch("pungi.phases.extra_isos.read_json_file")
    def test_volume_id_differs(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger

        opts = CreateIsoOpts(volid="new-volid")

        read_json_file.return_value = {"opts": {"volid": "old-volid"}}

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    @mock.patch("pungi.phases.extra_isos.read_json_file")
    def test_packages_differ(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger

        new_graft_points = os.path.join(self.topdir, "new_graft_points")
        helpers.touch(new_graft_points, "Packages/f/foo-1-1.x86_64.rpm\n")
        opts = CreateIsoOpts(graft_points=new_graft_points, volid="volid")

        old_graft_points = os.path.join(self.topdir, "old_graft_points")
        helpers.touch(old_graft_points, "Packages/f/foo-1-2.x86_64.rpm\n")
        read_json_file.return_value = {
            "opts": {"graft_points": old_graft_points, "volid": "volid"}
        }

        self.assertFalse(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )

    @mock.patch("pungi.phases.extra_isos.read_json_file")
    def test_runs_perform_reuse(self, read_json_file):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        compose.load_old_compose_config.return_value = compose.conf.copy()
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        thread.logger = self.logger
        thread.perform_reuse = mock.Mock()

        new_graft_points = os.path.join(self.topdir, "new_graft_points")
        helpers.touch(new_graft_points)
        opts = CreateIsoOpts(graft_points=new_graft_points, volid="volid")

        old_graft_points = os.path.join(self.topdir, "old_graft_points")
        helpers.touch(old_graft_points)
        dummy_iso_path = "dummy-iso-path/dummy.iso"
        read_json_file.return_value = {
            "opts": {
                "graft_points": old_graft_points,
                "volid": "volid",
                "output_dir": os.path.dirname(dummy_iso_path),
                "iso_name": os.path.basename(dummy_iso_path),
            },
        }

        self.assertTrue(
            thread.try_reuse(
                compose, compose.variants["Server"], "x86_64", "abcdef", opts
            )
        )
        self.assertEqual(
            thread.perform_reuse.call_args_list,
            [
                mock.call(
                    compose,
                    compose.variants["Server"],
                    "x86_64",
                    opts,
                    "dummy-iso-path",
                    "dummy.iso",
                )
            ],
        )


@mock.patch("pungi.phases.extra_isos.OldFileLinker")
class ExtraIsoPerformReusePhaseTest(helpers.PungiTestCase):
    def test_success(self, OldFileLinker):
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        opts = CreateIsoOpts(output_dir="new/path", iso_name="new.iso")

        thread.perform_reuse(
            compose,
            compose.variants["Server"],
            "x86_64",
            opts,
            "old",
            "image.iso",
        )

        self.assertEqual(
            OldFileLinker.return_value.mock_calls,
            [
                mock.call.link("old/image.iso", "new/path/new.iso"),
                mock.call.link("old/image.iso.manifest", "new/path/new.iso.manifest"),
                # The old log file doesn't exist in the test scenario.
                mock.call.link(
                    None,
                    os.path.join(
                        self.topdir, "logs/x86_64/extraiso-new.iso.x86_64.log"
                    ),
                ),
            ],
        )

    def test_failure(self, OldFileLinker):
        OldFileLinker.return_value.link.side_effect = helpers.mk_boom()
        compose = helpers.DummyCompose(self.topdir, {"extraiso_allow_reuse": True})
        thread = extra_isos.ExtraIsosThread(compose, mock.Mock())
        opts = CreateIsoOpts(output_dir="new/path", iso_name="new.iso")

        with self.assertRaises(Exception):
            thread.perform_reuse(
                compose,
                compose.variants["Server"],
                "x86_64",
                opts,
                "old",
                "image.iso",
            )

        self.assertEqual(
            OldFileLinker.return_value.mock_calls,
            [
                mock.call.link("old/image.iso", "new/path/new.iso"),
                mock.call.abort(),
            ],
        )
