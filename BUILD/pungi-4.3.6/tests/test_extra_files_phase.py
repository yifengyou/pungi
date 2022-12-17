# -*- coding: utf-8 -*-

import mock
import os

from productmd.extra_files import ExtraFiles

import six

from pungi.phases import extra_files
from tests import helpers


class TestExtraFilePhase(helpers.PungiTestCase):
    @mock.patch("pungi.phases.extra_files.copy_extra_files")
    def test_skips_unless_has_config(self, copy_extra_files):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = extra_files.ExtraFilesPhase(compose, mock.Mock())
        self.assertTrue(phase.skip())

    @mock.patch("pungi.phases.extra_files.copy_extra_files")
    def test_runs_copy_files_for_each_variant(self, copy_extra_files):
        cfg = mock.Mock()
        pkgset_phase = mock.Mock()
        compose = helpers.DummyCompose(
            self.topdir, {"extra_files": [("^.+$", {"x86_64": [cfg]})]}
        )

        phase = extra_files.ExtraFilesPhase(compose, pkgset_phase)
        phase.run()

        six.assertCountEqual(
            self,
            copy_extra_files.call_args_list,
            [
                mock.call(
                    compose,
                    [cfg],
                    "x86_64",
                    compose.variants["Server"],
                    pkgset_phase.package_sets,
                    phase.metadata,
                ),
                mock.call(
                    compose,
                    [cfg],
                    "x86_64",
                    compose.variants["Everything"],
                    pkgset_phase.package_sets,
                    phase.metadata,
                ),
            ],
        )
        self.assertTrue(isinstance(phase.metadata, ExtraFiles))


class TestCopyFiles(helpers.PungiTestCase):
    def setUp(self):
        super(TestCopyFiles, self).setUp()
        self.metadata = ExtraFiles()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.variant = self.compose.variants["Server"]

    def test_copy_local_file(self):
        tgt = os.path.join(self.topdir, "file")
        helpers.touch(tgt)
        cfg = {"scm": "file", "file": tgt, "repo": None}

        extra_files.copy_extra_files(
            self.compose, [cfg], "x86_64", self.variant, mock.Mock(), self.metadata
        )

        self.assertTrue(
            os.path.isfile(
                os.path.join(self.topdir, "compose", "Server", "x86_64", "os", "file")
            )
        )

    def test_copy_multiple_sources(self):
        tgt1 = os.path.join(self.topdir, "file")
        tgt2 = os.path.join(self.topdir, "gpl")
        helpers.touch(tgt1)
        helpers.touch(tgt2)
        cfg1 = {"scm": "file", "file": tgt1, "repo": None}
        cfg2 = {"scm": "file", "file": tgt2, "repo": None, "target": "license"}

        extra_files.copy_extra_files(
            self.compose,
            [cfg1, cfg2],
            "x86_64",
            self.variant,
            mock.Mock(),
            self.metadata,
        )

        self.assertTrue(
            os.path.isfile(
                os.path.join(self.topdir, "compose", "Server", "x86_64", "os", "file")
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.topdir, "compose", "Server", "x86_64", "os", "license", "gpl"
                )
            )
        )

    def test_copy_local_dir(self):
        helpers.touch(os.path.join(self.topdir, "src", "file"))
        helpers.touch(os.path.join(self.topdir, "src", "another"))
        cfg = {
            "scm": "file",
            "dir": os.path.join(self.topdir, "src"),
            "repo": None,
            "target": "subdir",
        }
        extra_files.copy_extra_files(
            self.compose, [cfg], "x86_64", self.variant, mock.Mock(), self.metadata
        )

        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.topdir, "compose", "Server", "x86_64", "os", "subdir", "file"
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.topdir,
                    "compose",
                    "Server",
                    "x86_64",
                    "os",
                    "subdir",
                    "another",
                )
            )
        )

    @mock.patch("pungi.phases.extra_files.get_file_from_scm")
    @mock.patch("pungi.phases.extra_files.get_dir_from_scm")
    def test_copy_from_external_rpm(self, get_dir_from_scm, get_file_from_scm):
        cfg = {
            "scm": "rpm",
            "file": "file.txt",
            "repo": "http://example.com/package.rpm",
        }

        get_file_from_scm.side_effect = self.fake_get_file

        extra_files.copy_extra_files(
            self.compose, [cfg], "x86_64", self.variant, mock.Mock(), self.metadata
        )

        self.assertEqual(len(get_file_from_scm.call_args_list), 1)
        self.assertEqual(get_dir_from_scm.call_args_list, [])
        self.assertEqual(
            self.scm_dict,
            {
                "scm": "rpm",
                "file": "file.txt",
                "repo": "http://example.com/package.rpm",
            },
        )

        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.topdir, "compose", "Server", "x86_64", "os", "file.txt"
                )
            )
        )

    @mock.patch("pungi.phases.extra_files.get_file_from_scm")
    @mock.patch("pungi.phases.extra_files.get_dir_from_scm")
    def test_copy_from_rpm_in_compose(self, get_dir_from_scm, get_file_from_scm):
        cfg = {"scm": "rpm", "file": "file.txt", "repo": "%(variant_uid)s-data*"}
        server_po, client_po, src_po = mock.Mock(), mock.Mock(), mock.Mock()
        server_po.configure_mock(
            name="Server-data-1.1-1.fc24.x86_64.rpm",
            file_path="/server/location",
            arch="x86_64",
        )
        client_po.configure_mock(
            name="Client-data-1.1-1.fc24.x86_64.rpm",
            file_path="/client/location",
            arch="x86_64",
        )
        src_po.configure_mock(
            name="extra-data-1.1-1.fc24.src.rpm", file_path="/src/location", arch="src"
        )
        package_sets = [
            {
                "x86_64": {
                    server_po.name: server_po,
                    client_po.name: client_po,
                    src_po.name: src_po,
                },
            },
        ]

        get_file_from_scm.side_effect = self.fake_get_file

        extra_files.copy_extra_files(
            self.compose, [cfg], "x86_64", self.variant, package_sets, self.metadata
        )

        self.assertEqual(len(get_file_from_scm.call_args_list), 1)
        self.assertEqual(get_dir_from_scm.call_args_list, [])

        self.assertEqual(
            self.scm_dict,
            {"scm": "rpm", "file": "file.txt", "repo": ["/server/location"]},
        )

        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.topdir, "compose", "Server", "x86_64", "os", "file.txt"
                )
            )
        )

    def fake_get_file(self, scm_dict, dest, compose):
        self.scm_dict = scm_dict
        helpers.touch(os.path.join(dest, scm_dict["file"]))
        return [scm_dict["file"]]

    @mock.patch("pungi.phases.extra_files.get_file_from_scm")
    @mock.patch("pungi.phases.extra_files.get_dir_from_scm")
    def test_copy_from_non_existing_rpm_in_compose(
        self, get_dir_from_scm, get_file_from_scm
    ):
        cfg = {"scm": "rpm", "file": "file.txt", "repo": "bad-%(variant_uid_lower)s*"}
        package_sets = [{"x86_64": {}}]

        with self.assertRaises(RuntimeError) as ctx:
            extra_files.copy_extra_files(
                self.compose, [cfg], "x86_64", self.variant, package_sets, self.metadata
            )

        self.assertRegex(str(ctx.exception), r"No.*package.*matching bad-server\*.*")

        self.assertEqual(len(get_file_from_scm.call_args_list), 0)
        self.assertEqual(get_dir_from_scm.call_args_list, [])
