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
from six.moves import shlex_quote
import kobo.log
from kobo.shortcuts import run

from pungi.wrappers import kojiwrapper


class Runroot(kobo.log.LoggingBase):
    def __init__(self, compose, logger=None):
        """
        Creates new Runroot instance.

        :param Compose compose: Compose instance.
        :param Logger logger: Logger instance to log message to.
        """
        kobo.log.LoggingBase.__init__(self, logger=logger)
        self.compose = compose
        self.runroot_method = self.get_runroot_method()
        # Holds the result of last `run()` call.
        self._result = None

    def get_runroot_method(self):
        """
        Returns the runroot method by checking the `runroot_tag` and
        `runroot_method` options in configuration.

        :return: The configured method
        """
        runroot_tag = self.compose.conf.get("runroot_tag")
        runroot_method = self.compose.conf.get("runroot_method")
        if runroot_tag and not runroot_method:
            # If we have runroot tag and no method, let's assume koji method
            # for backwards compatibility.
            return "koji"
        # Otherwise use the configured method or default to local if nothing is
        # given.
        return runroot_method or "local"

    def _run_local(self, command, log_file=None, **kwargs):
        """
        Runs the runroot command locally.
        """
        run(command, show_cmd=True, logfile=log_file)
        self._result = True

    def _run_koji(self, command, log_file=None, packages=None, arch=None, **kwargs):
        """
        Runs the runroot command in Koji.
        """
        runroot_channel = self.compose.conf.get("runroot_channel")
        runroot_tag = self.compose.conf["runroot_tag"]

        koji_wrapper = kojiwrapper.KojiWrapper(self.compose.conf["koji_profile"])
        koji_cmd = koji_wrapper.get_runroot_cmd(
            runroot_tag, arch, command,
            channel=runroot_channel, use_shell=True, task_id=True,
            packages=packages, **kwargs
        )

        output = koji_wrapper.run_runroot_cmd(koji_cmd, log_file=log_file)
        if output["retcode"] != 0:
            raise RuntimeError(
                "Runroot task failed: %s. See %s for more details."
                % (output["task_id"], log_file)
            )
        self._result = output

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
        return run(ssh_cmd, show_cmd=True, logfile=log_file)[1]

    def _run_openssh(self, command, log_file=None, arch=None, packages=None,
                     chown_paths=None, **kwargs):
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
            # Make the files world readable
            command += " && chmod -R a+r %s" % paths
            # and owned by the same user that is running the process
            command += " && chown -R %d %s" % (os.getuid(), paths)

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
                hostname, user, init_template, fmt_dict, log_file=log_file)
            runroot_key = runroot_key.rstrip("\n\r")
        else:
            runroot_key = None

        # Install the packages needed for runroot task if configured.
        if install_packages_template and packages:
            fmt_dict = {"packages": " ".join(packages)}
            if runroot_key:
                fmt_dict["runroot_key"] = runroot_key
            self._ssh_run(
                hostname, user, install_packages_template, fmt_dict, log_file=log_file
            )

        # Run the runroot task and get the buildroot RPMs.
        if run_template:
            fmt_dict = {"command": command}
            if runroot_key:
                fmt_dict["runroot_key"] = runroot_key
            self._ssh_run(hostname, user, run_template, fmt_dict, log_file=log_file)

            fmt_dict["command"] = "rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'"
            buildroot_rpms = self._ssh_run(
                hostname, user, run_template, fmt_dict, log_file=log_file
            )
        else:
            self._ssh_run(hostname, user, command, log_file=log_file)
            buildroot_rpms = self._ssh_run(
                hostname,
                user,
                "rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                log_file=log_file,
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
            to allow the executor of this runroot task to accesss them.
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
