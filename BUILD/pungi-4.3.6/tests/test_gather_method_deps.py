# -*- coding: utf-8 -*-

import mock

from pungi.phases.gather.methods import method_deps as deps
from tests import helpers


class TestWritePungiConfig(helpers.PungiTestCase):
    def setUp(self):
        super(TestWritePungiConfig, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.package_sets = self._make_pkgset_phase(["p1"]).package_sets

    def assertWritten(self, PungiWrapper, **kwargs):
        wrapper = PungiWrapper.return_value
        self.assertEqual(wrapper.mock_calls, [mock.call.write_kickstart(**kwargs)])

    @mock.patch("pungi.phases.gather.methods.method_deps.PungiWrapper")
    def test_correct(self, PungiWrapper):
        pkgs = [("pkg1", None), ("pkg2", "x86_64")]
        grps = ["grp1"]
        filter = [("pkg3", None), ("pkg4", "x86_64")]
        white = mock.Mock()
        black = mock.Mock()
        prepopulate = mock.Mock()
        fulltree = mock.Mock()
        deps.write_pungi_config(
            self.compose,
            "x86_64",
            self.compose.variants["Server"],
            pkgs,
            grps,
            filter,
            white,
            black,
            prepopulate=prepopulate,
            fulltree_excludes=fulltree,
            package_sets=self.package_sets,
        )
        self.assertWritten(
            PungiWrapper,
            packages=["pkg1", "pkg2.x86_64"],
            ks_path=self.topdir + "/work/x86_64/pungi/Server.x86_64.conf",
            lookaside_repos={},
            multilib_whitelist=white,
            multilib_blacklist=black,
            groups=["grp1"],
            prepopulate=prepopulate,
            repos={
                "pungi-repo-0": self.topdir + "/work/x86_64/repo/p1",
                "comps-repo": self.topdir + "/work/x86_64/comps_repo_Server",
            },
            exclude_packages=["pkg3", "pkg4.x86_64"],
            fulltree_excludes=fulltree,
        )

    @mock.patch("pungi.phases.gather.methods.method_deps.PungiWrapper")
    def test_duplicated_package_name(self, PungiWrapper):
        pkgs = [("pkg1", None), ("pkg1", "x86_64")]
        grps = []
        filter = [("pkg2", None), ("pkg2", "x86_64")]
        white = mock.Mock()
        black = mock.Mock()
        prepopulate = mock.Mock()
        fulltree = mock.Mock()
        deps.write_pungi_config(
            self.compose,
            "x86_64",
            self.compose.variants["Server"],
            pkgs,
            grps,
            filter,
            white,
            black,
            prepopulate=prepopulate,
            fulltree_excludes=fulltree,
            package_sets=self.package_sets,
        )
        self.assertWritten(
            PungiWrapper,
            packages=["pkg1", "pkg1.x86_64"],
            ks_path=self.topdir + "/work/x86_64/pungi/Server.x86_64.conf",
            lookaside_repos={},
            multilib_whitelist=white,
            multilib_blacklist=black,
            groups=[],
            prepopulate=prepopulate,
            repos={
                "pungi-repo-0": self.topdir + "/work/x86_64/repo/p1",
                "comps-repo": self.topdir + "/work/x86_64/comps_repo_Server",
            },
            exclude_packages=["pkg2", "pkg2.x86_64"],
            fulltree_excludes=fulltree,
        )

    @mock.patch("pungi.phases.gather.get_lookaside_repos")
    @mock.patch("pungi.phases.gather.methods.method_deps.PungiWrapper")
    def test_with_lookaside(self, PungiWrapper, glr):
        glr.return_value = ["http://example.com/repo"]
        pkgs = [("pkg1", None)]
        deps.write_pungi_config(
            self.compose,
            "x86_64",
            self.compose.variants["Server"],
            pkgs,
            [],
            [],
            [],
            [],
            package_sets=self.package_sets,
        )
        self.assertWritten(
            PungiWrapper,
            packages=["pkg1"],
            ks_path=self.topdir + "/work/x86_64/pungi/Server.x86_64.conf",
            lookaside_repos={"lookaside-repo-0": "http://example.com/repo"},
            multilib_whitelist=[],
            multilib_blacklist=[],
            groups=[],
            prepopulate=None,
            repos={
                "pungi-repo-0": self.topdir + "/work/x86_64/repo/p1",
                "comps-repo": self.topdir + "/work/x86_64/comps_repo_Server",
            },
            exclude_packages=[],
            fulltree_excludes=None,
        )
        self.assertEqual(
            glr.call_args_list,
            [mock.call(self.compose, "x86_64", self.compose.variants["Server"])],
        )

    @mock.patch("pungi.phases.gather.methods.method_deps.PungiWrapper")
    def test_without_input(self, PungiWrapper):
        with self.assertRaises(RuntimeError) as ctx:
            deps.write_pungi_config(
                self.compose,
                "x86_64",
                self.compose.variants["Server"],
                [],
                [],
                [],
                [],
                [],
            )
        self.assertEqual(
            str(ctx.exception),
            "No packages included in Server.x86_64 (no comps groups, no input packages, no prepopulate)",  # noqa: E501
        )
        self.assertEqual(PungiWrapper.return_value.mock_calls, [])


class TestRaiseOnInvalidSigkeys(helpers.PungiTestCase):
    def test_raise_on_invalid_sigkeys(self):
        pkgset = {
            "global": mock.Mock(),
        }
        pkgset["global"].invalid_sigkey_rpms = [{"name": "pkg1"}]
        pkgset["global"].raise_invalid_sigkeys_exception = mock.Mock(
            side_effect=RuntimeError()
        )
        result = {
            "rpm": [{"path": "pkg1-1-1.el7"}],
        }
        with self.assertRaises(RuntimeError):
            deps.raise_on_invalid_sigkeys("", "", [pkgset], result)


class TestCheckDeps(helpers.PungiTestCase):
    def setUp(self):
        super(TestCheckDeps, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.arch = "x86_64"
        self.variant = self.compose.variants["Server"]

    def test_not_check_deps(self):
        self.compose.conf["check_deps"] = False
        self.assertIsNone(deps.check_deps(self.compose, self.arch, self.variant, {}))

    def test_missing_deps(self):
        self.compose.conf["check_deps"] = True
        missing_deps = {"foo.noarch": set(["bar = 1.1"])}
        with self.assertRaises(RuntimeError) as ctx:
            deps.check_deps(self.compose, self.arch, self.variant, missing_deps)
        self.assertEqual(str(ctx.exception), "Unresolved dependencies detected")
        self.assertEqual(
            self.compose.log_error.call_args_list,
            [
                mock.call(
                    "Unresolved dependencies for %s.%s in package foo.noarch: ['bar = 1.1']"  # noqa: E501
                    % (self.variant, self.arch)
                )
            ],
        )
