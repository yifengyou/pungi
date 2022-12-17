# -*- coding: utf-8 -*-

import mock
import os

from pungi.runroot import Runroot
from tests import helpers


class TestRunrootOpenSSH(helpers.PungiTestCase):
    def setUp(self):
        super(TestRunrootOpenSSH, self).setUp()
        self.compose = helpers.DummyCompose(
            self.topdir,
            {
                "runroot": True,
                "runroot_method": "openssh",
                "runroot_ssh_user": "root",
                "runroot_ssh_hostnames": {"x86_64": "localhost"},
                "runroot_tag": "f28-build",
            },
        )

        self.runroot = Runroot(self.compose)

    def test_get_runroot_method(self):
        method = self.runroot.get_runroot_method()
        self.assertEqual(method, "openssh")

    def test_get_runroot_method_phase(self):
        self.compose.conf["runroot_method"] = {"ostree": "openssh"}
        method = self.runroot.get_runroot_method(phase="ostree")
        self.assertEqual(method, "openssh")

        # Test fallback to local
        method = self.runroot.get_runroot_method(phase="createiso")
        self.assertEqual(method, "local")

    def test_get_runroot_method_global_runroot_method(self):
        self.compose.conf["runroot_method"] = {"ostree": "openssh"}
        self.compose.conf["global_runroot_method"] = "koji"
        method = self.runroot.get_runroot_method(phase="ostree")
        self.assertEqual(method, "openssh")

        # Test global_runroot_method
        method = self.runroot.get_runroot_method(phase="createiso")
        self.assertEqual(method, "koji")

    def _ssh_call(self, cmd, suffix=None):
        """
        Helper method returning default SSH mock.call with given command `cmd`.
        """
        logfile = ("/foo/runroot." + suffix + ".log") if suffix else "/foo/runroot.log"
        return mock.call(
            ["ssh", "-oBatchMode=yes", "-n", "-l", "root", "localhost", cmd],
            logfile=logfile,
            show_cmd=True,
        )

    @mock.patch("pungi.runroot.run")
    def test_run(self, run):
        run.return_value = (0, "dummy output\n")
        self.runroot.run("df -h", log_file="/foo/runroot.log", arch="x86_64")
        run.assert_has_calls(
            [
                self._ssh_call("df -h"),
                self._ssh_call(
                    "rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )

    @mock.patch("pungi.runroot.run")
    def test_get_buildroot_rpms(self, run):
        # Run the runroot task at first.
        run.return_value = (0, "foo-1-1.fc29.noarch\nbar-1-1.fc29.noarch\n")
        self.runroot.run("df -h", log_file="/foo/runroot.log", arch="x86_64")

        rpms = self.runroot.get_buildroot_rpms()
        self.assertEqual(set(rpms), set(["foo-1-1.fc29.noarch", "bar-1-1.fc29.noarch"]))

    @mock.patch("pungi.runroot.run")
    def test_run_templates(self, run):
        self.compose.conf[
            "runroot_ssh_init_template"
        ] = "/usr/sbin/init_runroot {runroot_tag}"
        self.compose.conf[
            "runroot_ssh_install_packages_template"
        ] = "install {runroot_key} {packages}"
        self.compose.conf["runroot_ssh_run_template"] = "run {runroot_key} {command}"

        run.return_value = (0, "key\n")
        self.runroot.run(
            "df -h",
            log_file="/foo/runroot.log",
            arch="x86_64",
            packages=["lorax", "automake"],
        )
        run.assert_has_calls(
            [
                self._ssh_call("/usr/sbin/init_runroot f28-build", suffix="init"),
                self._ssh_call("install key lorax automake", suffix="install_packages"),
                self._ssh_call("run key df -h"),
                self._ssh_call(
                    "run key rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )

    @mock.patch("pungi.runroot.run")
    def test_run_templates_no_init(self, run):
        self.compose.conf[
            "runroot_ssh_install_packages_template"
        ] = "install {packages}"
        self.compose.conf["runroot_ssh_run_template"] = "run {command}"

        run.return_value = (0, "key\n")
        self.runroot.run(
            "df -h",
            log_file="/foo/runroot.log",
            arch="x86_64",
            packages=["lorax", "automake"],
        )
        run.assert_has_calls(
            [
                self._ssh_call("install lorax automake", suffix="install_packages"),
                self._ssh_call("run df -h"),
                self._ssh_call(
                    "run rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )

    @mock.patch("pungi.runroot.run")
    def test_run_templates_no_packages(self, run):
        self.compose.conf[
            "runroot_ssh_install_packages_template"
        ] = "install {packages}"
        self.compose.conf["runroot_ssh_run_template"] = "run {command}"

        run.return_value = (0, "key\n")
        self.runroot.run("df -h", log_file="/foo/runroot.log", arch="x86_64")
        run.assert_has_calls(
            [
                self._ssh_call("run df -h"),
                self._ssh_call(
                    "run rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )

    @mock.patch("pungi.runroot.run")
    def test_run_templates_no_install_packages(self, run):
        self.compose.conf["runroot_ssh_run_template"] = "run {command}"

        run.return_value = (0, "key\n")
        self.runroot.run(
            "df -h",
            log_file="/foo/runroot.log",
            arch="x86_64",
            packages=["lorax", "automake"],
        )
        run.assert_has_calls(
            [
                self._ssh_call("run df -h"),
                self._ssh_call(
                    "run rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )

    @mock.patch("pungi.runroot.run")
    def test_run_templates_output_dir(self, run):
        self.compose.conf["runroot_ssh_run_template"] = "run {command}"

        run.return_value = (0, "key\n")
        self.runroot.run(
            "df -h",
            log_file="/foo/runroot.log",
            arch="x86_64",
            packages=["lorax", "automake"],
            chown_paths=["/mnt/foo/compose", "/mnt/foo/x"],
        )
        run.assert_has_calls(
            [
                self._ssh_call(
                    "run df -h ; EXIT_CODE=$? ; "
                    "chmod -R a+r /mnt/foo/compose /mnt/foo/x ; "
                    "chown -R %d /mnt/foo/compose /mnt/foo/x ; exit $EXIT_CODE"
                    % os.getuid()
                ),
                self._ssh_call(
                    "run rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                    suffix="rpms",
                ),
            ]
        )


class TestRunrootKoji(helpers.PungiTestCase):
    def setUp(self):
        super(TestRunrootKoji, self).setUp()
        self.compose = helpers.DummyCompose(
            self.topdir,
            {"runroot": True, "runroot_tag": "f28-build"},
        )

        self.runroot = Runroot(self.compose)

    def test_has_losetup_error(self):
        self.assertFalse(self.runroot._has_losetup_error(None))

        with mock.patch("pungi.runroot.open", mock.mock_open(read_data="")):
            self.assertFalse(self.runroot._has_losetup_error("/foo_log_dir"))

        with mock.patch(
            "pungi.runroot.open",
            mock.mock_open(read_data="losetup: cannot find an unused loop device"),
        ):
            self.assertTrue(self.runroot._has_losetup_error("/bar_log_dir"))

    @mock.patch("pungi.runroot.kojiwrapper.KojiWrapper")
    def test_run_koji_retry(self, mock_kojiwrapper):
        self.compose.conf["koji_profile"] = "test"
        mock_kojiwrapper.return_value.get_runroot_cmd.return_value = ["df -h"]
        mock_kojiwrapper.return_value.run_runroot_cmd.side_effect = [
            {"retcode": 1, "task_id": 1},
            {"retcode": 0, "task_id": 2},
        ]
        self.runroot._has_losetup_error = mock.Mock(side_effect=[True, False])
        self.runroot._run_koji("")
        self.assertEqual(mock_kojiwrapper.return_value.run_runroot_cmd.call_count, 2)
