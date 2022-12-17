# -*- coding: utf-8 -*-


try:
    import unittest2 as unittest
except ImportError:
    import unittest

import mock
import six

import pungi.phases.repoclosure as repoclosure_phase
from tests.helpers import DummyCompose, PungiTestCase, mk_boom

try:
    import dnf  # noqa: F401

    HAS_DNF = True
except ImportError:
    HAS_DNF = False

try:
    import yum  # noqa: F401

    HAS_YUM = True
except ImportError:
    HAS_YUM = False


class TestRepoclosure(PungiTestCase):
    def setUp(self):
        super(TestRepoclosure, self).setUp()
        self.maxDiff = None

    def _get_repo(self, compose_id, variant, arch, path=None):
        path = path or arch + "/os"
        return {
            "%s-repoclosure-%s.%s" % (compose_id, variant, arch): self.topdir
            + "/compose/%s/%s" % (variant, path)
        }

    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_skip_if_disabled(self, mock_run, mock_grc):
        compose = DummyCompose(
            self.topdir, {"repoclosure_strictness": [("^.*$", {"*": "off"})]}
        )
        repoclosure_phase.run_repoclosure(compose)

        self.assertEqual(mock_grc.call_args_list, [])

    @unittest.skipUnless(HAS_YUM, "YUM is not available")
    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_default_backend(self, mock_run, mock_grc):
        with mock.patch("six.PY2", new=True):
            compose = DummyCompose(self.topdir, {})

        repoclosure_phase.run_repoclosure(compose)

        six.assertCountEqual(
            self,
            mock_grc.call_args_list,
            [
                mock.call(
                    backend="yum",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Everything", "amd64"),
                ),
                mock.call(
                    backend="yum",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Client", "amd64"),
                ),
                mock.call(
                    backend="yum",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "amd64"),
                ),
                mock.call(
                    backend="yum",
                    arch=["x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "x86_64"),
                ),
                mock.call(
                    backend="yum",
                    arch=["x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Everything", "x86_64"),
                ),
            ],
        )

    @unittest.skipUnless(HAS_DNF, "DNF is not available")
    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_dnf_backend(self, mock_run, mock_grc):
        compose = DummyCompose(self.topdir, {"repoclosure_backend": "dnf"})
        repoclosure_phase.run_repoclosure(compose)

        six.assertCountEqual(
            self,
            mock_grc.call_args_list,
            [
                mock.call(
                    backend="dnf",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Everything", "amd64"),
                ),
                mock.call(
                    backend="dnf",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Client", "amd64"),
                ),
                mock.call(
                    backend="dnf",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "amd64"),
                ),
                mock.call(
                    backend="dnf",
                    arch=["x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "x86_64"),
                ),
                mock.call(
                    backend="dnf",
                    arch=["x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Everything", "x86_64"),
                ),
            ],
        )

    @mock.patch("glob.glob")
    @mock.patch("pungi.wrappers.repoclosure.extract_from_fus_logs")
    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_hybrid_variant(self, mock_run, mock_grc, effl, glob):
        compose = DummyCompose(
            self.topdir, {"repoclosure_backend": "dnf", "gather_method": "hybrid"}
        )
        f = mock.Mock()
        glob.return_value = [f]

        def _log(a, v):
            return compose.paths.log.log_file(a, "repoclosure-%s" % compose.variants[v])

        repoclosure_phase.run_repoclosure(compose)

        self.assertEqual(mock_grc.call_args_list, [])
        six.assertCountEqual(
            self,
            effl.call_args_list,
            [
                mock.call([f], _log("amd64", "Everything")),
                mock.call([f], _log("amd64", "Client")),
                mock.call([f], _log("amd64", "Server")),
                mock.call([f], _log("x86_64", "Server")),
                mock.call([f], _log("x86_64", "Everything")),
            ],
        )

    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_report_error(self, mock_run, mock_grc):
        compose = DummyCompose(
            self.topdir, {"repoclosure_strictness": [("^.*$", {"*": "fatal"})]}
        )
        mock_run.side_effect = mk_boom(cls=RuntimeError)

        with self.assertRaises(RuntimeError):
            repoclosure_phase.run_repoclosure(compose)

    @unittest.skipUnless(HAS_DNF, "DNF is not available")
    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_overwrite_options_creates_correct_commands(
        self, mock_run, mock_grc
    ):
        compose = DummyCompose(
            self.topdir,
            {
                "repoclosure_backend": "dnf",
                "repoclosure_strictness": [
                    ("^.*$", {"*": "off"}),
                    ("^Server$", {"*": "fatal"}),
                ],
            },
        )
        repoclosure_phase.run_repoclosure(compose)

        six.assertCountEqual(
            self,
            mock_grc.call_args_list,
            [
                mock.call(
                    backend="dnf",
                    arch=["amd64", "x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "amd64"),
                ),
                mock.call(
                    backend="dnf",
                    arch=["x86_64", "noarch"],
                    lookaside={},
                    repos=self._get_repo(compose.compose_id, "Server", "x86_64"),
                ),
            ],
        )

    @mock.patch("pungi.phases.repoclosure._delete_repoclosure_cache_dirs")
    @mock.patch("pungi.wrappers.repoclosure.get_repoclosure_cmd")
    @mock.patch("pungi.phases.repoclosure.run")
    def test_repoclosure_uses_correct_behaviour(self, mock_run, mock_grc, mock_del):
        compose = DummyCompose(
            self.topdir,
            {
                "repoclosure_backend": "dnf",
                "repoclosure_strictness": [
                    ("^.*$", {"*": "off"}),
                    ("^Server$", {"*": "fatal"}),
                ],
            },
        )
        mock_run.side_effect = mk_boom(cls=RuntimeError)

        with self.assertRaises(RuntimeError):
            repoclosure_phase.run_repoclosure(compose)
