# -*- coding: utf-8 -*-


# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.

import os
import re
import six
from six.moves import shlex_quote
import kobo.log
from kobo.shortcuts import run

from pungi.wrappers import kojiwrapper


RUNROOT_TYPES = ["local", "koji", "openssh"]


class Runroot(kobo.log.LoggingBase):
    def __init__(self, compose, logger=None, phase=None):
        """
        Creates new Runroot instance.

        :param Compose compose: Compose instance.
        :param Logger logger: Logger instance to log message to.
        :param str phase: Pungi phase the runroot task is run as part of.
        """
        kobo.log.LoggingBase.__init__(self, logger=logger)
        self.compose = compose
        self.runroot_method = self.get_runroot_method(phase)
        # Holds the result of last `run()` call.
        self._result = None

    def get_runroot_method(self, phase=None):
        """
        Returns the runroot method by checking the `runroot_tag` and
        `runroot_method` options in configuration.

        :param str phase: Pungi phase to get the runroot method for.

        :return: The configured method
        """
        runroot_tag = self.compose.conf.get("runroot_tag")
        runroot_method = self.compose.conf.get("runroot_method")
        if runroot_tag and not runroot_method:
            # If we have runroot tag and no method, let's assume koji method
            # for backwards compatibility.
            return "koji"

        if isinstance(runroot_method, dict):
            # If runroot_method is set to dict, check if there is runroot_method
            # override for the current phase.
            if phase in runroot_method:
                return runroot_method[phase]
            global_runroot_method = self.compose.conf.get("global_runroot_method")
            return global_runroot_method or "local"

        # Otherwise use the configured method or default to local if nothing is
        # given.
        return runroot_method or "local"

    def _run_local(self, command, log_file=None, **kwargs):
        """
        Runs the runroot command locally.
        """
        run(command, show_cmd=True, logfile=log_file)
        self._result = True

    def _has_losetup_error(self, log_dir):
        """
        Check if there's losetup error in log.

        This error happens if the Koji builder runs out of loopback devices.
        This can happen if too many tasks that require them are scheduled on
        the same builder. A retried task might end up on a different builder,
        or maybe some other task will have finished already.

        :param str log_dir: path to buildinstall log dir,
            e.g. logs/s390x/buildinstall-BaseOS-logs/
        """
        if not log_dir:
            return False

        log_file = os.path.join(log_dir, "program.log")
        try:
            with open(log_file) as f:
                for line in f:
                    if "losetup: cannot find an unused loop device" in line:
                        return True
                    if re.match("losetup: .* failed to set up loop device", line):
                        return True
        except Exception:
            pass
        return False

    def _run_koji(self, command, log_file=None, packages=None, arch=None, **kwargs):
        """
        Runs the runroot command in Koji.
        """
        runroot_channel = self.compose.conf.get("runroot_channel")
        runroot_tag = self.compose.conf["runroot_tag"]
        log_dir = kwargs.pop("log_dir", None)

        koji_wrapper = kojiwrapper.KojiWrapper(self.compose)
        koji_cmd = koji_wrapper.get_runroot_cmd(
            runroot_tag,
            arch,
            command,
            channel=runroot_channel,
            use_shell=True,
            packages=packages,
            **kwargs
        )

        attempt = 0
        max_retries = 3
        while True:
            output = koji_wrapper.run_runroot_cmd(koji_cmd, log_file=log_file)
            if output["retcode"] == 0:
                self._result = output
                return
            elif attempt >= max_retries or not self._has_losetup_error(log_dir):
                raise RuntimeError(
                    "Runroot task failed: %s. See %s for more details."
                    % (output["task_id"], log_file)
                )
            attempt += 1

    def _ssh_run(self, hostname, user, command, fmt_dict=None, log_file=None):
        """
        Helper method to run the command using "ssh".

        :param str hostname: Hostname.
        :param str user: User for login.
        :param str command: Command to run.
        :param str fmt_dict: If set, the `command` is formatted like
            `command.format(**fmt_dict)`.
        :param str log_file: Log file.
        :return str: Output of remote command.
        """
        formatted_cmd = command.format(**fmt_dict) if fmt_dict else command
        ssh_cmd = ["ssh", "-oBatchMode=yes", "-n", "-l", user, hostname, formatted_cmd]
        output = run(ssh_cmd, show_cmd=True, logfile=log_file)[1]
        if six.PY3 and isinstance(output, bytes):
            return output.decode()
        else:
            return output

    def _log_file(self, base, suffix):
        return base.replace(".log", "." + suffix + ".log")

    def _run_openssh(
        self,
        command,
        log_file=None,
        arch=None,
        packages=None,
        chown_paths=None,
        **kwargs
    ):
        """
        Runs the runroot command on remote machine using ssh.
        """
        runroot_ssh_hostnames = self.compose.conf.get("runroot_ssh_hostnames", {})
        if arch not in runroot_ssh_hostnames:
            raise ValueError("The arch %r not in runroot_ssh_hostnames." % arch)

        # If the output dir is defined, change the permissions of files generated
        # by the runroot task, so the Pungi user can access them.
        if chown_paths:
            paths = " ".join(shlex_quote(pth) for pth in chown_paths)
            command += " ; EXIT_CODE=$?"
            # Make the files world readable
            command += " ; chmod -R a+r %s" % paths
            # and owned by the same user that is running the process
            command += " ; chown -R %d %s" % (os.getuid(), paths)
            # Exit with code of main command
            command += " ; exit $EXIT_CODE"

        hostname = runroot_ssh_hostnames[arch]
        user = self.compose.conf.get("runroot_ssh_username", "root")
        runroot_tag = self.compose.conf["runroot_tag"]
        init_template = self.compose.conf.get("runroot_ssh_init_template")
        install_packages_template = self.compose.conf.get(
            "runroot_ssh_install_packages_template"
        )
        run_template = self.compose.conf.get("runroot_ssh_run_template")

        # Init the runroot on remote machine and get the runroot_key.
        if init_template:
            fmt_dict = {"runroot_tag": runroot_tag}
            runroot_key = self._ssh_run(
                hostname,
                user,
                init_template,
                fmt_dict,
                log_file=self._log_file(log_file, "init"),
            )
            runroot_key = runroot_key.rstrip("\n\r")
        else:
            runroot_key = None

        # Install the packages needed for runroot task if configured.
        if install_packages_template and packages:
            fmt_dict = {"packages": " ".join(packages)}
            if runroot_key:
                fmt_dict["runroot_key"] = runroot_key
            self._ssh_run(
                hostname,
                user,
                install_packages_template,
                fmt_dict,
                log_file=self._log_file(log_file, "install_packages"),
            )

        # Run the runroot task and get the buildroot RPMs.
        if run_template:
            fmt_dict = {"command": command}
            if runroot_key:
                fmt_dict["runroot_key"] = runroot_key
            self._ssh_run(hostname, user, run_template, fmt_dict, log_file=log_file)

            fmt_dict[
                "command"
            ] = "rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'"
            buildroot_rpms = self._ssh_run(
                hostname,
                user,
                run_template,
                fmt_dict,
                log_file=self._log_file(log_file, "rpms"),
            )
        else:
            self._ssh_run(hostname, user, command, log_file=log_file)
            buildroot_rpms = self._ssh_run(
                hostname,
                user,
                "rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                log_file=self._log_file(log_file, "rpms"),
            )

        # Parse the buildroot_rpms and store it in self._result.
        self._result = []
        for i in buildroot_rpms.splitlines():
            if not i:
                continue
            self._result.append(i)

    def run(self, command, log_file=None, packages=None, arch=None, **kwargs):
        """
        Runs the runroot task using the `Runroot.runroot_method`. Blocks until
        the runroot task is successfully finished. Raises an exception on error.

        The **kwargs are optional and matches the  `KojiWrapper.get_runroot_cmd()`
        kwargs. Some `runroot_method` methods might ignore the kwargs which
        do not make sense for them.

        :param str command: Command to execute.
        :param str log_file: Log file into which the output of runroot task will
            be logged.
        :param list packages: List of packages which are needed for runroot task
            to be executed.
        :param str arch: Architecture on which the runroot task should be
            executed.
        :param str output_dir: Directory where the `command` stores its output.
            The permissions of this output_dir might be changed by `runroot_method`
            to allow the executor of this runroot task to access them.
            See `KojiWrapper.get_runroot_cmd()` for more information.
        """
        if self.runroot_method == "local":
            self._run_local(
                command, log_file=log_file, packages=packages, arch=arch, **kwargs
            )
        elif self.runroot_method == "koji":
            self._run_koji(
                command, log_file=log_file, packages=packages, arch=arch, **kwargs
            )
        elif self.runroot_method == "openssh":
            self._run_openssh(
                command, log_file=log_file, packages=packages, arch=arch, **kwargs
            )
        else:
            raise ValueError("Unknown runroot_method %r." % self.runroot_method)

    def run_pungi_buildinstall(self, args, log_file=None, arch=None, **kwargs):
        """
        Runs the Lorax buildinstall runroot command using the Pungi Buildinstall
        Koji plugin as pungi_buildinstall task.

        The **kwargs are optional and matches the
        `KojiWrapper.get_pungi_buildinstall_cmd()` kwargs.

        :param dict args: Arguments for the pungi_buildinstall Koji task.
        :param str log_file: Log file into which the output of the task will
            be logged.
        :param str arch: Architecture on which the task should be executed.
        """
        runroot_channel = self.compose.conf.get("runroot_channel")
        runroot_tag = self.compose.conf["runroot_tag"]

        koji_wrapper = kojiwrapper.KojiWrapper(self.compose)
        koji_cmd = koji_wrapper.get_pungi_buildinstall_cmd(
            runroot_tag,
            arch,
            args,
            channel=runroot_channel,
            chown_uid=os.getuid(),
            **kwargs
        )

        output = koji_wrapper.run_runroot_cmd(koji_cmd, log_file=log_file)
        if output["retcode"] != 0:
            raise RuntimeError(
                "Pungi-buildinstall task failed: %s. See %s for more details."
                % (output["task_id"], log_file)
            )
        self._result = output

    def run_pungi_ostree(self, args, log_file=None, arch=None, **kwargs):
        """
        Runs the OStree runroot command using the Pungi OSTree
        Koji plugin as pungi_ostree task.

        The **kwargs are optional and matches the
        `KojiWrapper.get_pungi_buildinstall_cmd()` kwargs.

        :param dict args: Arguments for the pungi_ostree Koji task.
        :param str log_file: Log file into which the output of the task will
            be logged.
        :param str arch: Architecture on which the task should be executed.
        """
        runroot_channel = self.compose.conf.get("runroot_channel")
        runroot_tag = self.compose.conf["runroot_tag"]

        koji_wrapper = kojiwrapper.KojiWrapper(self.compose)
        koji_cmd = koji_wrapper.get_pungi_ostree_cmd(
            runroot_tag, arch, args, channel=runroot_channel, **kwargs
        )

        output = koji_wrapper.run_runroot_cmd(koji_cmd, log_file=log_file)
        if output["retcode"] != 0:
            raise RuntimeError(
                "Pungi-buildinstall task failed: %s. See %s for more details."
                % (output["task_id"], log_file)
            )
        self._result = output

    def get_buildroot_rpms(self):
        """
        Returns the list of RPMs installed in a buildroot in which the runroot
        task was executed. This is needed to track what actually generated
        the data generated by runroot task.

        This must be called after the `run()` method successfully finished,
        otherwise raises an exception.

        :return: List of RPMs in buildroot in which the runroot task run.
        """
        if not self._result:
            raise ValueError(
                "Runroot.get_buildroot_rpms called before runroot task finished."
            )
        if self.runroot_method in ["local", "koji"]:
            if self.runroot_method == "local":
                task_id = None
            else:
                task_id = self._result["task_id"]
            return kojiwrapper.get_buildroot_rpms(self.compose, task_id)
        elif self.runroot_method == "openssh":
            # For openssh runroot_method, the result is list of buildroot_rpms.
            return self._result
        else:
            raise ValueError("Unknown runroot_method %r." % self.runroot_method)
