# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import glob
import os

import mock
import six

from pungi.module_util import Modulemd
from pungi.phases.createrepo import (
    CreaterepoPhase,
    ModulesMetadata,
    create_variant_repo,
    get_productids_from_scm,
)
from tests.helpers import DummyCompose, PungiTestCase, copy_fixture, touch


class TestCreaterepoPhase(PungiTestCase):
    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_validates_without_option(self, ThreadPoolCls):
        compose = DummyCompose(self.topdir, {"createrepo_checksum": "sha256"})

        phase = CreaterepoPhase(compose)
        try:
            phase.validate()
        except ValueError:
            self.fail("Missing delta config should not fail validation")

    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_fails_deltas_without_old_compose(self, ThreadPoolCls):
        compose = DummyCompose(
            self.topdir, {"createrepo_checksum": "sha256", "createrepo_deltas": True}
        )

        phase = CreaterepoPhase(compose)
        with self.assertRaises(ValueError) as ctx:
            phase.validate()

        self.assertIn("deltas", str(ctx.exception))

    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_fails_deltas_without_old_compose_granular_config(self, ThreadPoolCls):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": [("^Everything$", {"*": True})],
            },
        )

        phase = CreaterepoPhase(compose)
        with self.assertRaises(ValueError) as ctx:
            phase.validate()

        self.assertIn("deltas", str(ctx.exception))

    @mock.patch("pungi.checks.get_num_cpus")
    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_starts_jobs(self, ThreadPoolCls, get_num_cpus):
        get_num_cpus.return_value = 5
        compose = DummyCompose(self.topdir, {})

        pool = ThreadPoolCls.return_value

        phase = CreaterepoPhase(compose)
        phase.run()

        server = compose.variants["Server"]
        everything = compose.variants["Everything"]
        client = compose.variants["Client"]
        self.assertEqual(len(pool.add.mock_calls), 5)
        six.assertCountEqual(
            self,
            pool.queue_put.mock_calls,
            [
                mock.call((compose, "x86_64", server, "rpm")),
                mock.call((compose, "x86_64", server, "debuginfo")),
                mock.call((compose, "amd64", server, "rpm")),
                mock.call((compose, "amd64", server, "debuginfo")),
                mock.call((compose, None, server, "srpm")),
                mock.call((compose, "x86_64", everything, "rpm")),
                mock.call((compose, "x86_64", everything, "debuginfo")),
                mock.call((compose, "amd64", everything, "rpm")),
                mock.call((compose, "amd64", everything, "debuginfo")),
                mock.call((compose, None, everything, "srpm")),
                mock.call((compose, "amd64", client, "rpm")),
                mock.call((compose, "amd64", client, "debuginfo")),
                mock.call((compose, None, client, "srpm")),
            ],
        )

    @mock.patch("pungi.checks.get_num_cpus")
    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_skips_empty_variants(self, ThreadPoolCls, get_num_cpus):
        get_num_cpus.return_value = 5
        compose = DummyCompose(self.topdir, {})
        compose.variants["Client"].is_empty = True

        pool = ThreadPoolCls.return_value

        phase = CreaterepoPhase(compose)
        phase.run()
        self.maxDiff = None

        server = compose.variants["Server"]
        everything = compose.variants["Everything"]
        self.assertEqual(len(pool.add.mock_calls), 5)
        six.assertCountEqual(
            self,
            pool.queue_put.mock_calls,
            [
                mock.call((compose, "x86_64", server, "rpm")),
                mock.call((compose, "x86_64", server, "debuginfo")),
                mock.call((compose, "amd64", server, "rpm")),
                mock.call((compose, "amd64", server, "debuginfo")),
                mock.call((compose, None, server, "srpm")),
                mock.call((compose, "x86_64", everything, "rpm")),
                mock.call((compose, "x86_64", everything, "debuginfo")),
                mock.call((compose, "amd64", everything, "rpm")),
                mock.call((compose, "amd64", everything, "debuginfo")),
                mock.call((compose, None, everything, "srpm")),
            ],
        )

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    @mock.patch("pungi.phases.createrepo.ThreadPool")
    def test_clones_extra_modulemd(self, ThreadPoolCls, get_dir_from_scm):
        scm = mock.Mock()
        compose = DummyCompose(
            self.topdir, {"createrepo_extra_modulemd": {"Server": scm}}
        )

        phase = CreaterepoPhase(compose)
        phase.run()

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [
                mock.call(
                    scm,
                    os.path.join(compose.topdir, "work/global/tmp-Server"),
                    compose=compose,
                )
            ],
        )


def make_mocked_modifyrepo_cmd(tc, module_artifacts):
    def mocked_modifyrepo_cmd(repodir, mmd_path, **kwargs):
        mod_index = Modulemd.ModuleIndex.new()
        mod_index.update_from_file(mmd_path, strict=True)

        tc.assertEqual(len(mod_index.get_module_names()), 1)

        module = mod_index.get_module("test")
        module_streams = module.get_all_streams()
        tc.assertEqual(len(module_streams), len(module_artifacts))
        for ms in module_streams:
            tc.assertIn(ms.get_stream_name(), module_artifacts)
            six.assertCountEqual(
                tc,
                ms.get_rpm_artifacts(),
                module_artifacts[ms.get_stream_name()],
            )

    return mocked_modifyrepo_cmd


class TestCreateVariantRepo(PungiTestCase):
    def setUp(self):
        super(TestCreateVariantRepo, self).setUp()
        self.pkgset = mock.Mock(
            paths={"x86_64": "/repo/x86_64", "global": "/repo/global"}
        )

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {"createrepo_checksum": "sha256"},
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        with mock.patch("pungi.phases.createrepo.CACHE_TOPDIR", self.topdir):
            create_variant_repo(
                compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
            )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )

        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=os.path.join(
                        self.topdir,
                        "%s-%s" % (compose.conf["release_short"], os.getuid()),
                    ),
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_without_database(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {"createrepo_checksum": "sha256", "createrepo_enable_cache": False},
        )
        compose.should_create_yum_database = False
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=False,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_source(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {"createrepo_checksum": "sha256", "createrepo_enable_cache": False},
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, None, compose.variants["Server"], "srpm", self.pkgset
        )

        list_file = self.topdir + "/work/global/repo_package_list/Server.None.srpm.conf"
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/source/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/source/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/global",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.src.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_debug(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {"createrepo_checksum": "sha256", "createrepo_enable_cache": False},
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "debuginfo", self.pkgset
        )
        self.maxDiff = None

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.debuginfo.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/debug/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/debug/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(
            list_file, "Packages/b/bash-debuginfo-4.3.30-2.fc21.x86_64.rpm\n"
        )

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_no_createrepo_c(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_c": False,
                "createrepo_enable_cache": False,
                "createrepo_checksum": "sha256",
            },
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=False)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_is_idepotent(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "createrepo_num_workers": 10,
            },
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        # Running the same thing twice only creates repo once.
        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )
        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=10,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_xz(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "createrepo_use_xz": True,
            },
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=True,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": True,
                "createrepo_enable_cache": False,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        os.makedirs(
            self.topdir + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages"
        )

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path=None,
                    deltas=True,
                    oldpackagedirs=self.topdir
                    + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages",
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas_granular_config(
        self, CreaterepoWrapperCls, run
    ):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": [("^Server$", {"*": True})],
                "createrepo_enable_cache": False,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )
        os.makedirs(
            self.topdir + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages"
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path=None,
                    deltas=True,
                    oldpackagedirs=self.topdir
                    + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages",
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas_granular_config_no_match(
        self, CreaterepoWrapperCls, run
    ):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": [("^Everything$", {"x86_64": True})],
                "createrepo_enable_cache": False,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas_granular_config_no_match_on_arch(
        self, CreaterepoWrapperCls, run
    ):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": [("^Server$", {"s390x": True})],
                "createrepo_enable_cache": False,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas_hashed_dirs(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": True,
                "createrepo_enable_cache": False,
                "hashed_directories": True,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )
        self.maxDiff = None

        for f in ["a/a.rpm", "b/b.rpm", "foo"]:
            touch(
                self.topdir
                + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages/"
                + f
            )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path=None,
                    deltas=True,
                    oldpackagedirs=[
                        self.topdir
                        + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages/a",  # noqa: E501
                        self.topdir
                        + "/old/test-1.0-20151203.0/compose/Server/x86_64/os/Packages/b",  # noqa: E501
                    ],
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_deltas_hashed_dirs_but_old_doesnt_exist(
        self, CreaterepoWrapperCls, run
    ):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": True,
                "createrepo_enable_cache": False,
                "hashed_directories": True,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )
        self.maxDiff = None

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=True,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_source_with_deltas(self, CreaterepoWrapperCls, run):
        # This should not actually create deltas, only binary repos do.
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "createrepo_deltas": True,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, None, compose.variants["Server"], "srpm", self.pkgset
        )

        list_file = self.topdir + "/work/global/repo_package_list/Server.None.srpm.conf"
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/source/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/source/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/global",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.src.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_debug_with_deltas(self, CreaterepoWrapperCls, run):
        # This should not actually create deltas, only binary repos do.
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_deltas": True,
                "createrepo_enable_cache": False,
            },
        )
        compose.has_comps = False
        compose.old_composes = [self.topdir + "/old"]
        touch(
            os.path.join(self.topdir, "old", "test-1.0-20151203.0", "STATUS"),
            "FINISHED",
        )

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "debuginfo", self.pkgset
        )

        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.debuginfo.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/debug/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/debug/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(
            list_file, "Packages/b/bash-debuginfo-4.3.30-2.fc21.x86_64.rpm\n"
        )

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_rpms_with_productid(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "product_id": "yes",  # Truthy value is enough for this test
            },
        )
        compose.has_comps = False
        product_id = compose.paths.work.product_id("x86_64", compose.variants["Server"])
        repodata_dir = os.path.join(
            compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
            "repodata",
        )
        touch(product_id)
        os.mkdir(repodata_dir)

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "rpm", self.pkgset
        )

        self.maxDiff = None
        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.rpm.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/os",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/os",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(
            repo.get_modifyrepo_cmd.mock_calls,
            [mock.call(repodata_dir, product_id, compress_type="gz")],
        )
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.x86_64.rpm\n")

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_debug_with_productid(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "product_id": "yes",  # Truthy value is enough for this test
            },
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, "x86_64", compose.variants["Server"], "debuginfo", self.pkgset
        )

        self.maxDiff = None
        list_file = (
            self.topdir + "/work/x86_64/repo_package_list/Server.x86_64.debuginfo.conf"
        )
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/x86_64/debug/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/x86_64/debug/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/x86_64",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(
            list_file, "Packages/b/bash-debuginfo-4.3.30-2.fc21.x86_64.rpm\n"
        )

    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_source_with_productid(self, CreaterepoWrapperCls, run):
        compose = DummyCompose(
            self.topdir,
            {
                "createrepo_checksum": "sha256",
                "createrepo_enable_cache": False,
                "product_id": "yes",  # Truthy value is enough for this test
            },
        )
        compose.has_comps = False

        repo = CreaterepoWrapperCls.return_value
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        create_variant_repo(
            compose, None, compose.variants["Server"], "srpm", self.pkgset
        )

        self.maxDiff = None
        list_file = self.topdir + "/work/global/repo_package_list/Server.None.srpm.conf"
        self.assertEqual(
            CreaterepoWrapperCls.mock_calls[0], mock.call(createrepo_c=True)
        )
        self.assertEqual(
            repo.get_createrepo_cmd.mock_calls,
            [
                mock.call(
                    self.topdir + "/compose/Server/source/tree",
                    checksum="sha256",
                    database=True,
                    groupfile=None,
                    workers=3,
                    outputdir=self.topdir + "/compose/Server/source/tree",
                    pkglist=list_file,
                    skip_stat=True,
                    update=True,
                    update_md_path="/repo/global",
                    deltas=False,
                    oldpackagedirs=None,
                    use_xz=False,
                    extra_args=[],
                    cachedir=None,
                )
            ],
        )
        self.assertEqual(repo.get_modifyrepo_cmd.mock_calls, [])
        self.assertFileContent(list_file, "Packages/b/bash-4.3.30-2.fc21.src.rpm\n")

    @unittest.skipUnless(Modulemd is not None, "Skipped test, no module support.")
    @mock.patch("pungi.phases.createrepo.find_file_in_repodata")
    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_modules_artifacts_not_in_compose(
        self, CreaterepoWrapperCls, run, modulemd_filename
    ):
        compose = DummyCompose(self.topdir, {"createrepo_checksum": "sha256"})
        compose.has_comps = False

        variant = compose.variants["Server"]
        variant.arch_mmds["x86_64"] = {}
        variant.arch_mmds["x86_64"]["test:f27:1:2017"] = variant.add_fake_module(
            "test:f27:1:2017", rpm_nvrs=["pkg-0:1.0.0-1.x86_64"]
        )
        variant.arch_mmds["x86_64"]["test:f28:1:2017"] = variant.add_fake_module(
            "test:f28:1:2017", rpm_nvrs=["pkg-0:2.0.0-1.x86_64"]
        )

        repo = CreaterepoWrapperCls.return_value
        repo.get_modifyrepo_cmd.side_effect = make_mocked_modifyrepo_cmd(
            self, {"f27": [], "f28": []}
        )
        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        repodata_dir = os.path.join(
            compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
            "repodata",
        )
        modulemd_filename.return_value = (
            "Server/x86_64/os/repodata/3511d16a7-modules.yaml.gz"
        )
        modules_metadata = mock.Mock()

        create_variant_repo(
            compose,
            "x86_64",
            compose.variants["Server"],
            "rpm",
            self.pkgset,
            modules_metadata,
        )

        self.assertEqual(
            repo.get_modifyrepo_cmd.mock_calls,
            [mock.call(repodata_dir, mock.ANY, compress_type="gz", mdtype="modules")],
        )

    @unittest.skipUnless(Modulemd is not None, "Skipped test, no module support.")
    @mock.patch("pungi.phases.createrepo.find_file_in_repodata")
    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_modules_artifacts(
        self, CreaterepoWrapperCls, run, modulemd_filename
    ):
        compose = DummyCompose(self.topdir, {"createrepo_checksum": "sha256"})
        compose.has_comps = False

        variant = compose.variants["Server"]
        variant.arch_mmds["x86_64"] = {
            "test:f27:2018:cafe": variant.add_fake_module(
                "test:f27:2018:cafe",
                rpm_nvrs=["bash-0:4.3.30-2.fc21.x86_64"],
                with_artifacts=True,
            ),
            "test:f28:2018:beef": variant.add_fake_module(
                "test:f28:2018:beef",
                rpm_nvrs=["pkg-0:2.0.0-1.x86_64"],
                with_artifacts=True,
            ),
        }
        variant.module_uid_to_koji_tag = {
            "test:f28:2018:beef": "tag-1",
            "test:f27:2018:cafe": "tag-2",
        }

        repo = CreaterepoWrapperCls.return_value
        repo.get_modifyrepo_cmd.side_effect = make_mocked_modifyrepo_cmd(
            self,
            {"f27": ["bash-0:4.3.30-2.fc21.x86_64"], "f28": ["pkg-0:2.0.0-1.x86_64"]},
        )

        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))

        repodata_dir = os.path.join(
            compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
            "repodata",
        )

        modules_metadata = ModulesMetadata(compose)

        modulemd_filename.return_value = "Server/x86_64/os/repodata/3511d16a723e1bd69826e591508f07e377d2212769b59178a9-modules.yaml.gz"  # noqa: E501
        create_variant_repo(
            compose,
            "x86_64",
            compose.variants["Server"],
            "rpm",
            self.pkgset,
            modules_metadata,
        )

        self.assertEqual(
            repo.get_modifyrepo_cmd.mock_calls,
            [mock.call(repodata_dir, mock.ANY, compress_type="gz", mdtype="modules")],
        )

    @unittest.skipUnless(Modulemd is not None, "Skipped test, no module support.")
    @mock.patch("pungi.phases.createrepo.find_file_in_repodata")
    @mock.patch("pungi.phases.createrepo.run")
    @mock.patch("pungi.phases.createrepo.CreaterepoWrapper")
    def test_variant_repo_extra_modulemd(
        self, CreaterepoWrapperCls, run, modulemd_filename
    ):
        compose = DummyCompose(
            self.topdir, {"createrepo_extra_modulemd": {"Server": mock.Mock()}}
        )
        compose.has_comps = False

        variant = compose.variants["Server"]
        variant.arch_mmds["x86_64"] = {}
        variant.module_uid_to_koji_tag = {}

        repo = CreaterepoWrapperCls.return_value

        copy_fixture("server-rpms.json", compose.paths.compose.metadata("rpms.json"))
        copy_fixture(
            "fake-modulemd.yaml",
            os.path.join(compose.topdir, "work/global/tmp-Server/x86_64/*.yaml"),
        )

        repodata_dir = os.path.join(
            compose.paths.compose.os_tree("x86_64", compose.variants["Server"]),
            "repodata",
        )

        modules_metadata = ModulesMetadata(compose)

        modulemd_filename.return_value = "Server/x86_64/os/repodata/3511d16a723e1bd69826e591508f07e377d2212769b59178a9-modules.yaml.gz"  # noqa: E501
        create_variant_repo(
            compose,
            "x86_64",
            compose.variants["Server"],
            "rpm",
            self.pkgset,
            modules_metadata,
        )

        self.assertEqual(
            repo.get_modifyrepo_cmd.mock_calls,
            [mock.call(repodata_dir, mock.ANY, compress_type="gz", mdtype="modules")],
        )
        self.assertEqual(
            list(modules_metadata.productmd_modules_metadata["Server"]["x86_64"]),
            ["mymodule:master:1:cafe"],
        )


class TestGetProductIds(PungiTestCase):
    def mock_get(self, filenames):
        def _mock_get(scm, dest, compose=None):
            for filename in filenames:
                touch(os.path.join(dest, filename))

        return _mock_get

    def assertProductIds(self, mapping):
        pids = glob.glob(self.compose.paths.work.product_id("*", "*"))
        expected = set()
        for variant, arches in mapping.items():
            for arch in arches:
                expected.add(
                    os.path.join(
                        self.topdir,
                        "work",
                        arch,
                        "product_id",
                        "%s.%s.pem" % (variant, arch),
                        "productid",
                    )
                )
        six.assertCountEqual(self, pids, expected)

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    def test_not_configured(self, get_dir_from_scm):
        self.compose = DummyCompose(self.topdir, {})
        get_productids_from_scm(self.compose)
        self.assertEqual(get_dir_from_scm.call_args_list, [])
        self.assertProductIds({})

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    def test_correct(self, get_dir_from_scm):
        cfg = mock.Mock()
        self.compose = DummyCompose(self.topdir, {"product_id": cfg})
        get_dir_from_scm.side_effect = self.mock_get(
            [
                "Client-amd64-cert.pem",
                "Everything-amd64-cert.pem",
                "Server-amd64-cert.pem",
                "Everything-x86_64-cert.pem",
                "Server-x86_64-cert.pem",
            ]
        )

        get_productids_from_scm(self.compose)

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [mock.call(cfg, mock.ANY, compose=self.compose)],
        )
        self.assertProductIds(
            {
                "Client": ["amd64"],
                "Everything": ["amd64", "x86_64"],
                "Server": ["amd64", "x86_64"],
            }
        )

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    def test_allow_missing(self, get_dir_from_scm):
        cfg = mock.Mock()
        self.compose = DummyCompose(
            self.topdir, {"product_id": cfg, "product_id_allow_missing": True}
        )
        get_dir_from_scm.side_effect = self.mock_get(
            ["Server-amd64-cert.pem", "Server-x86_64-cert.pem"]
        )

        get_productids_from_scm(self.compose)

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [mock.call(cfg, mock.ANY, compose=self.compose)],
        )
        self.assertProductIds({"Server": ["amd64", "x86_64"]})

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    def test_missing_fails(self, get_dir_from_scm):
        cfg = mock.Mock()
        self.compose = DummyCompose(self.topdir, {"product_id": cfg})
        get_dir_from_scm.side_effect = self.mock_get(
            ["Server-amd64-cert.pem", "Server-x86_64-cert.pem"]
        )

        with self.assertRaises(RuntimeError) as ctx:
            get_productids_from_scm(self.compose)

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [mock.call(cfg, mock.ANY, compose=self.compose)],
        )
        self.assertRegex(
            str(ctx.exception),
            r"No product certificate found \(arch: amd64, variant: (Everything|Client)\)",  # noqa: E501
        )

    @mock.patch("pungi.phases.createrepo.get_dir_from_scm")
    def test_multiple_matching(self, get_dir_from_scm):
        cfg = mock.Mock()
        self.compose = DummyCompose(self.topdir, {"product_id": cfg})
        get_dir_from_scm.side_effect = self.mock_get(
            [
                "Client-amd64-cert.pem",
                "Client-amd64-cert-duplicate.pem",
                "Everything-amd64-cert.pem",
                "Server-amd64-cert.pem",
                "Everything-x86_64-cert.pem",
                "Server-x86_64-cert.pem",
            ]
        )

        with self.assertRaises(RuntimeError) as ctx:
            get_productids_from_scm(self.compose)

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [mock.call(cfg, mock.ANY, compose=self.compose)],
        )
        self.assertRegex(str(ctx.exception), "Multiple product certificates found.+")
