# -*- coding: utf-8 -*-

import os

import mock
import six

from pungi.module_util import Modulemd
from pungi.phases.pkgset import common
from tests import helpers


class MockCreateRepo(object):
    def __init__(self, createrepo_c):
        self.createrepo_c = createrepo_c

    def get_createrepo_cmd(self, path_prefix, outputdir, pkglist, **kwargs):
        return (path_prefix, outputdir, pkglist)


@mock.patch("pungi.phases.init.run_in_threads", new=helpers.fake_run_in_threads)
@mock.patch("pungi.phases.pkgset.common.CreaterepoWrapper", new=MockCreateRepo)
@mock.patch("pungi.phases.pkgset.common.run")
class TestMaterializedPkgsetCreate(helpers.PungiTestCase):
    def setUp(self):
        super(TestMaterializedPkgsetCreate, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.prefix = "/prefix"
        self.pkgset = self._make_pkgset("foo")
        self.subsets = {}

    def _mk_call(self, arch, name):
        pkglist = "%s.%s.conf" % (arch, name)
        logfile = "arch_repo.%s.%s.log" % (name, arch)
        return mock.call(
            (
                self.prefix,
                os.path.join(self.topdir, "work", arch, "repo", name),
                os.path.join(self.topdir, "work", arch, "package_list", pkglist),
            ),
            logfile=os.path.join(self.topdir, "logs", arch, logfile),
            show_cmd=True,
        )

    def _make_pkgset(self, name):
        pkgset = mock.Mock()
        pkgset.name = name
        pkgset.reuse = None

        def mock_subset(primary, arch_list, exclusive_noarch):
            self.subsets[primary] = mock.Mock()
            return self.subsets[primary]

        pkgset.subset.side_effect = mock_subset
        return pkgset

    def _mk_paths(self, name, arches):
        paths = {"global": os.path.join(self.topdir, "work/global/repo", name)}
        for arch in arches:
            paths[arch] = os.path.join(self.topdir, "work", arch, "repo", name)
        return paths

    def test_run(self, mock_run):
        result = common.MaterializedPackageSet.create(
            self.compose, self.pkgset, self.prefix
        )

        six.assertCountEqual(
            self, result.package_sets.keys(), ["global", "amd64", "x86_64"]
        )
        self.assertEqual(result["global"], self.pkgset)
        self.assertEqual(result["x86_64"], self.subsets["x86_64"])
        self.assertEqual(result["amd64"], self.subsets["amd64"])

        self.pkgset.subset.assert_any_call(
            "x86_64", ["x86_64", "noarch", "src"], exclusive_noarch=True
        )
        self.pkgset.subset.assert_any_call(
            "amd64", ["amd64", "x86_64", "noarch", "src"], exclusive_noarch=True
        )

        for arch, pkgset in result.package_sets.items():
            pkgset.save_file_list.assed_any_call(
                os.path.join(
                    self.topdir, "work", arch, "package_list", arch + ".foo.conf"
                ),
                remove_path_prefix=self.prefix,
            )

        self.assertEqual(result.paths, self._mk_paths("foo", ["amd64", "x86_64"]))

        mock_run.assert_has_calls(
            [self._mk_call(arch, "foo") for arch in ["global", "amd64", "x86_64"]],
            any_order=True,
        )

    @helpers.unittest.skipUnless(Modulemd, "Skipping tests, no module support")
    @mock.patch("pungi.phases.pkgset.common.collect_module_defaults")
    @mock.patch("pungi.phases.pkgset.common.collect_module_obsoletes")
    @mock.patch("pungi.phases.pkgset.common.add_modular_metadata")
    def test_run_with_modulemd(self, amm, cmo, cmd, mock_run):
        # Test Index for cmo
        mod_index = Modulemd.ModuleIndex.new()
        mmdobs = Modulemd.Obsoletes.new(
            1, 10993435, "mod_name", "mod_stream", "testmsg"
        )
        mmdobs.set_obsoleted_by("mod_name", "mod_name_2")
        mod_index.add_obsoletes(mmdobs)
        cmo.return_value = mod_index

        mmd = {
            "x86_64": [
                Modulemd.ModuleStream.new(
                    Modulemd.ModuleStreamVersionEnum.TWO, "mod_name", "stream_name"
                )
            ]
        }
        common.MaterializedPackageSet.create(
            self.compose, self.pkgset, self.prefix, mmd=mmd
        )
        cmd.assert_called_once_with(
            os.path.join(self.topdir, "work/global/module_defaults"),
            {"mod_name"},
            overrides_dir=None,
        )

        cmo.assert_called_once()
        cmd.assert_called_once()
        amm.assert_called_once()

        self.assertEqual(
            amm.mock_calls[0].args[1], os.path.join(self.topdir, "work/x86_64/repo/foo")
        )
        self.assertIsInstance(amm.mock_calls[0].args[2], Modulemd.ModuleIndex)
        self.assertIsNotNone(amm.mock_calls[0].args[2].get_module("mod_name"))
        # Check if proper Index is used by add_modular_metadata
        self.assertIsNotNone(
            amm.mock_calls[0].args[2].get_module("mod_name").get_obsoletes()
        )
        self.assertEqual(
            amm.mock_calls[0].args[3],
            os.path.join(self.topdir, "logs/x86_64/arch_repo_modulemd.foo.x86_64.log"),
        )


class TestCreateArchRepos(helpers.PungiTestCase):
    def setUp(self):
        super(TestCreateArchRepos, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.prefix = "/prefix"
        self.paths = {}
        self.pkgset = mock.Mock()
        self.pkgset.reuse = None
        self.pkgset.name = "foo"

    @mock.patch("pungi.phases.pkgset.common._create_arch_repo")
    def test_call_create_arch_repo(self, mock_create):
        common.create_arch_repos(
            self.compose, self.prefix, self.paths, self.pkgset, None
        )
        mock_create.assert_has_calls(
            [
                mock.call(
                    mock.ANY,
                    (self.compose, "amd64", self.prefix, self.paths, self.pkgset, None),
                    1,
                ),
                mock.call(
                    mock.ANY,
                    (
                        self.compose,
                        "x86_64",
                        self.prefix,
                        self.paths,
                        self.pkgset,
                        None,
                    ),
                    2,
                ),
            ]
        )

    @mock.patch("pungi.phases.pkgset.common.os.path.isdir", return_value=True)
    @mock.patch("pungi.phases.pkgset.common.copy_all")
    def test_reuse_arch_repo(self, mock_copy_all, mock_isdir):
        self.pkgset.reuse = "/path/to/old/global/repo"
        old_repo = "/path/to/old/repo"
        self.compose.paths.old_compose_path = mock.Mock(return_value=old_repo)
        common.create_arch_repos(
            self.compose, self.prefix, self.paths, self.pkgset, None
        )
        mock_copy_all.assert_has_calls(
            [
                mock.call(
                    old_repo, os.path.join(self.compose.topdir, "work/amd64/repo/foo")
                ),
                mock.call(
                    old_repo, os.path.join(self.compose.topdir, "work/x86_64/repo/foo")
                ),
            ],
            any_order=True,
        )
        self.compose.log_info.assert_has_calls(
            [
                mock.call("[BEGIN] %s", "Copying repodata for reuse: %s" % old_repo),
                mock.call("[DONE ] %s", "Copying repodata for reuse: %s" % old_repo),
            ]
        )
