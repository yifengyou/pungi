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
import time
import threading
import contextlib

import koji
from kobo.shortcuts import run
import six
from six.moves import configparser, shlex_quote
import six.moves.xmlrpc_client as xmlrpclib

from .. import util
from ..arch_utils import getBaseArch


class KojiWrapper(object):
    lock = threading.Lock()

    def __init__(self, profile):
        self.profile = profile
        with self.lock:
            self.koji_module = koji.get_profile_module(profile)
            session_opts = {}
            for key in ('krbservice', 'timeout', 'keepalive',
                        'max_retries', 'retry_interval', 'anon_retry',
                        'offline_retry', 'offline_retry_interval',
                        'debug', 'debug_xmlrpc', 'krb_rdns',
                        'serverca',
                        'use_fast_upload'):
                value = getattr(self.koji_module.config, key, None)
                if value is not None:
                    session_opts[key] = value
            self.koji_proxy = koji.ClientSession(self.koji_module.config.server, session_opts)

    def login(self):
        """Authenticate to the hub."""
        auth_type = self.koji_module.config.authtype
        if auth_type == 'ssl' or (os.path.isfile(os.path.expanduser(self.koji_module.config.cert))
                                  and auth_type is None):
            self.koji_proxy.ssl_login(os.path.expanduser(self.koji_module.config.cert),
                                      os.path.expanduser(self.koji_module.config.ca),
                                      os.path.expanduser(self.koji_module.config.serverca))
        elif auth_type == 'kerberos':
            self.koji_proxy.krb_login(
                getattr(self.koji_module.config, 'principal', None),
                getattr(self.koji_module.config, 'keytab', None))
        else:
            raise RuntimeError('Unsupported authentication type in Koji')

    def _get_cmd(self, *args):
        return ["koji", "--profile=%s" % self.profile] + list(args)

    def get_runroot_cmd(self, target, arch, command, quiet=False, use_shell=True,
                        channel=None, packages=None, mounts=None, weight=None,
                        task_id=True, new_chroot=False, chown_paths=None):
        cmd = self._get_cmd("runroot")

        if quiet:
            cmd.append("--quiet")

        if new_chroot:
            cmd.append("--new-chroot")

        if use_shell:
            cmd.append("--use-shell")

        if task_id:
            cmd.append("--task-id")

        if channel:
            cmd.append("--channel-override=%s" % channel)
        else:
            cmd.append("--channel-override=runroot-local")

        if weight:
            cmd.append("--weight=%s" % int(weight))

        for package in packages or []:
            cmd.append("--package=%s" % package)

        for mount in mounts or []:
            # directories are *not* created here
            cmd.append("--mount=%s" % mount)

        # IMPORTANT: all --opts have to be provided *before* args

        cmd.append(target)

        # i686 -> i386 etc.
        arch = getBaseArch(arch)
        cmd.append(arch)

        if isinstance(command, list):
            command = " ".join([shlex_quote(i) for i in command])

        # HACK: remove rpmdb and yum cache
        command = "rm -f /var/lib/rpm/__db*; rm -rf /var/cache/yum/*; set -x; " + command

        if chown_paths:
            paths = " ".join(shlex_quote(pth) for pth in chown_paths)
            # Make the files world readable
            command += " && chmod -R a+r %s" % paths
            # and owned by the same user that is running the process
            command += " && chown -R %d %s" % (os.getuid(), paths)
        cmd.append(command)

        return cmd

    @contextlib.contextmanager
    def get_koji_cmd_env(self):
        """Get environment variables for running a koji command.

        If we are authenticated with a keytab, we need a fresh credentials
        cache to avoid possible race condition.
        """
        if getattr(self.koji_module.config, 'keytab', None):
            with util.temp_dir(prefix='krb_ccache') as tempdir:
                env = os.environ.copy()
                env['KRB5CCNAME'] = 'DIR:%s' % tempdir
                yield env
        else:
            yield None

    def run_runroot_cmd(self, command, log_file=None):
        """
        Run koji runroot command and wait for results.

        If the command specified --task-id, and the first line of output
        contains the id, it will be captured and returned.
        """
        task_id = None
        with self.get_koji_cmd_env() as env:
            retcode, output = run(command, can_fail=True, logfile=log_file,
                                  show_cmd=True, env=env, universal_newlines=True)
        if "--task-id" in command:
            first_line = output.splitlines()[0]
            if re.match(r'^\d+$', first_line):
                task_id = int(first_line)
                # Remove first line from the output, preserving any trailing newlines.
                output_ends_with_eol = output.endswith("\n")
                output = "\n".join(output.splitlines()[1:])
                if output_ends_with_eol:
                    output += "\n"

        return {
            "retcode": retcode,
            "output": output,
            "task_id": task_id,
        }

    def get_image_build_cmd(self, config_options, conf_file_dest, wait=True, scratch=False):
        """
        @param config_options
        @param conf_file_dest -  a destination in compose workdir for the conf file to be written
        @param wait=True
        @param scratch=False
        """
        # Usage: koji image-build [options] <name> <version> <target> <install-tree-url> <arch> [<arch>...]
        sub_command = "image-build"
        # The minimum set of options
        min_options = ("name", "version", "target", "install_tree", "arches", "format", "kickstart", "ksurl", "distro")
        assert set(min_options).issubset(set(config_options['image-build'].keys())), "image-build requires at least %s got '%s'" % (", ".join(min_options), config_options)
        cfg_parser = configparser.ConfigParser()
        for section, opts in config_options.items():
            cfg_parser.add_section(section)
            for option, value in opts.items():
                if isinstance(value, list):
                    value = ','.join(value)
                if not isinstance(value, six.string_types):
                    # Python 3 configparser will reject non-string values.
                    value = str(value)
                cfg_parser.set(section, option, value)

        fd = open(conf_file_dest, "w")
        cfg_parser.write(fd)
        fd.close()

        cmd = self._get_cmd(sub_command, "--config=%s" % conf_file_dest)
        if wait:
            cmd.append("--wait")
        if scratch:
            cmd.append("--scratch")

        return cmd

    def get_live_media_cmd(self, options, wait=True):
        # Usage: koji spin-livemedia [options] <name> <version> <target> <arch> <kickstart-file>
        cmd = self._get_cmd('spin-livemedia')

        for key in ('name', 'version', 'target', 'arch', 'ksfile'):
            if key not in options:
                raise ValueError('Expected options to have key "%s"' % key)
            cmd.append(options[key])
        if 'install_tree' not in options:
            raise ValueError('Expected options to have key "install_tree"')
        cmd.append('--install-tree=%s' % options['install_tree'])

        for repo in options.get('repo', []):
            cmd.append('--repo=%s' % repo)

        if options.get('scratch'):
            cmd.append('--scratch')

        if options.get('skip_tag'):
            cmd.append('--skip-tag')

        if 'ksurl' in options:
            cmd.append('--ksurl=%s' % options['ksurl'])

        if 'release' in options:
            cmd.append('--release=%s' % options['release'])

        if 'can_fail' in options:
            cmd.append('--can-fail=%s' % ','.join(options['can_fail']))

        if wait:
            cmd.append('--wait')

        return cmd

    def get_create_image_cmd(self, name, version, target, arch, ks_file, repos,
                             image_type="live", image_format=None, release=None,
                             wait=True, archive=False, specfile=None, ksurl=None):
        # Usage: koji spin-livecd [options] <name> <version> <target> <arch> <kickstart-file>
        # Usage: koji spin-appliance [options] <name> <version> <target> <arch> <kickstart-file>
        # Examples:
        #  * name: RHEL-7.0
        #  * name: Satellite-6.0.1-RHEL-6
        #  ** -<type>.<arch>
        #  * version: YYYYMMDD[.n|.t].X
        #  * release: 1

        cmd = self._get_cmd()

        if image_type == "live":
            cmd.append("spin-livecd")
        elif image_type == "appliance":
            cmd.append("spin-appliance")
        else:
            raise ValueError("Invalid image type: %s" % image_type)

        if not archive:
            cmd.append("--scratch")

        cmd.append("--noprogress")

        if wait:
            cmd.append("--wait")
        else:
            cmd.append("--nowait")

        if specfile:
            cmd.append("--specfile=%s" % specfile)

        if ksurl:
            cmd.append("--ksurl=%s" % ksurl)

        if isinstance(repos, list):
            for repo in repos:
                cmd.append("--repo=%s" % repo)
        else:
            cmd.append("--repo=%s" % repos)

        if image_format:
            if image_type != "appliance":
                raise ValueError("Format can be specified only for appliance images'")
            supported_formats = ["raw", "qcow", "qcow2", "vmx"]
            if image_format not in supported_formats:
                raise ValueError("Format is not supported: %s. Supported formats: %s" % (image_format, " ".join(sorted(supported_formats))))
            cmd.append("--format=%s" % image_format)

        if release is not None:
            cmd.append("--release=%s" % release)

        # IMPORTANT: all --opts have to be provided *before* args
        # Usage: koji spin-livecd [options] <name> <version> <target> <arch> <kickstart-file>

        cmd.append(name)
        cmd.append(version)
        cmd.append(target)

        # i686 -> i386 etc.
        arch = getBaseArch(arch)
        cmd.append(arch)

        cmd.append(ks_file)

        return cmd

    def _has_connection_error(self, output):
        """Checks if output indicates connection error."""
        return re.search('error: failed to connect\n$', output)

    def _wait_for_task(self, task_id, logfile=None, max_retries=None):
        """Tries to wait for a task to finish. On connection error it will
        retry with `watch-task` command.
        """
        cmd = self._get_cmd('watch-task', str(task_id))
        attempt = 0

        while True:
            retcode, output = run(cmd, can_fail=True, logfile=logfile, universal_newlines=True)

            if retcode == 0 or not self._has_connection_error(output):
                # Task finished for reason other than connection error.
                return retcode, output

            attempt += 1
            if max_retries and attempt >= max_retries:
                break
            time.sleep(attempt * 10)

        raise RuntimeError('Failed to wait for task %s. Too many connection errors.' % task_id)

    def run_blocking_cmd(self, command, log_file=None, max_retries=None):
        """
        Run a blocking koji command. Returns a dict with output of the command,
        its exit code and parsed task id. This method will block until the
        command finishes.
        """
        with self.get_koji_cmd_env() as env:
            retcode, output = run(command, can_fail=True, logfile=log_file,
                                  env=env, universal_newlines=True)

        match = re.search(r"Created task: (\d+)", output)
        if not match:
            raise RuntimeError("Could not find task ID in output. Command '%s' returned '%s'."
                               % (" ".join(command), output))
        task_id = int(match.groups()[0])

        if retcode != 0 and self._has_connection_error(output):
            retcode, output = self._wait_for_task(task_id, logfile=log_file, max_retries=max_retries)

        return {
            "retcode": retcode,
            "output": output,
            "task_id": task_id,
        }

    def watch_task(self, task_id, log_file=None, max_retries=None):
        retcode, _ = self._wait_for_task(task_id, logfile=log_file, max_retries=max_retries)
        return retcode

    def get_image_paths(self, task_id, callback=None):
        """
        Given an image task in Koji, get a mapping from arches to a list of
        paths to results of the task.

        If callback is given, it will be called once with arch of every failed
        subtask.
        """
        result = {}

        # task = self.koji_proxy.getTaskInfo(task_id, request=True)
        children_tasks = self.koji_proxy.getTaskChildren(task_id, request=True)

        for child_task in children_tasks:
            if child_task['method'] not in ['createImage', 'createLiveMedia', 'createAppliance']:
                continue

            if child_task['state'] != koji.TASK_STATES['CLOSED']:
                # The subtask is failed, which can happen with the can_fail
                # option. If given, call the callback, and go to next child.
                if callback:
                    callback(child_task['arch'])
                continue

            is_scratch = child_task['request'][-1].get('scratch', False)
            task_result = self.koji_proxy.getTaskResult(child_task['id'])

            if is_scratch:
                topdir = os.path.join(
                    self.koji_module.pathinfo.work(),
                    self.koji_module.pathinfo.taskrelpath(child_task['id'])
                )
            else:
                build = self.koji_proxy.getImageBuild("%(name)s-%(version)s-%(release)s" % task_result)
                build["name"] = task_result["name"]
                build["version"] = task_result["version"]
                build["release"] = task_result["release"]
                build["arch"] = task_result["arch"]
                topdir = self.koji_module.pathinfo.imagebuild(build)

            for i in task_result["files"]:
                result.setdefault(task_result['arch'], []).append(os.path.join(topdir, i))

        return result

    def get_image_path(self, task_id):
        result = []
        task_info_list = []
        task_info_list.append(self.koji_proxy.getTaskInfo(task_id, request=True))
        task_info_list.extend(self.koji_proxy.getTaskChildren(task_id, request=True))

        # scan parent and child tasks for certain methods
        task_info = None
        for i in task_info_list:
            if i["method"] in ("createAppliance", "createLiveCD", 'createImage'):
                task_info = i
                break

        scratch = task_info["request"][-1].get("scratch", False)
        task_result = self.koji_proxy.getTaskResult(task_info["id"])
        task_result.pop("rpmlist", None)

        if scratch:
            topdir = os.path.join(self.koji_module.pathinfo.work(), self.koji_module.pathinfo.taskrelpath(task_info["id"]))
        else:
            build = self.koji_proxy.getImageBuild("%(name)s-%(version)s-%(release)s" % task_result)
            build["name"] = task_result["name"]
            build["version"] = task_result["version"]
            build["release"] = task_result["release"]
            build["arch"] = task_result["arch"]
            topdir = self.koji_module.pathinfo.imagebuild(build)
        for i in task_result["files"]:
            result.append(os.path.join(topdir, i))
        return result

    def get_wrapped_rpm_path(self, task_id, srpm=False):
        result = []
        task_info_list = []
        task_info_list.extend(self.koji_proxy.getTaskChildren(task_id, request=True))

        # scan parent and child tasks for certain methods
        task_info = None
        for i in task_info_list:
            if i["method"] in ("wrapperRPM"):
                task_info = i
                break

        # Get results of wrapperRPM task
        # {'buildroot_id': 2479520,
        #  'logs': ['checkout.log', 'root.log', 'state.log', 'build.log'],
        #  'rpms': ['foreman-discovery-image-2.1.0-2.el7sat.noarch.rpm'],
        #  'srpm': 'foreman-discovery-image-2.1.0-2.el7sat.src.rpm'}
        task_result = self.koji_proxy.getTaskResult(task_info["id"])

        # Get koji dir with results (rpms, srpms, logs, ...)
        topdir = os.path.join(self.koji_module.pathinfo.work(), self.koji_module.pathinfo.taskrelpath(task_info["id"]))

        # TODO: Maybe use different approach for non-scratch builds - see get_image_path()

        # Get list of filenames that should be returned
        result_files = task_result["rpms"]
        if srpm:
            result_files += [task_result["srpm"]]

        # Prepare list with paths to the required files
        for i in result_files:
            result.append(os.path.join(topdir, i))

        return result

    def get_signed_wrapped_rpms_paths(self, task_id, sigkey, srpm=False):
        result = []
        parent_task = self.koji_proxy.getTaskInfo(task_id, request=True)
        task_info_list = []
        task_info_list.extend(self.koji_proxy.getTaskChildren(task_id, request=True))

        # scan parent and child tasks for certain methods
        task_info = None
        for i in task_info_list:
            if i["method"] in ("wrapperRPM"):
                task_info = i
                break

        # Check parent_task if it's scratch build
        scratch = parent_task["request"][-1].get("scratch", False)
        if scratch:
            raise RuntimeError("Scratch builds cannot be signed!")

        # Get results of wrapperRPM task
        # {'buildroot_id': 2479520,
        #  'logs': ['checkout.log', 'root.log', 'state.log', 'build.log'],
        #  'rpms': ['foreman-discovery-image-2.1.0-2.el7sat.noarch.rpm'],
        #  'srpm': 'foreman-discovery-image-2.1.0-2.el7sat.src.rpm'}
        task_result = self.koji_proxy.getTaskResult(task_info["id"])

        # Get list of filenames that should be returned
        result_files = task_result["rpms"]
        if srpm:
            result_files += [task_result["srpm"]]

        # Prepare list with paths to the required files
        for i in result_files:
            rpminfo = self.koji_proxy.getRPM(i)
            build = self.koji_proxy.getBuild(rpminfo["build_id"])
            path = os.path.join(self.koji_module.pathinfo.build(build), self.koji_module.pathinfo.signed(rpminfo, sigkey))
            result.append(path)

        return result

    def get_build_nvrs(self, task_id):
        builds = self.koji_proxy.listBuilds(taskID=task_id)
        return [build.get("nvr") for build in builds if build.get("nvr")]

    def multicall_map(self, koji_session, koji_session_fnc, list_of_args=None, list_of_kwargs=None):
        """
        Calls the `koji_session_fnc` using Koji multicall feature N times based on the list of
        arguments passed in `list_of_args` and `list_of_kwargs`.
        Returns list of responses sorted the same way as input args/kwargs. In case of error,
        the error message is logged and None is returned.

        For example to get the package ids of "httpd" and "apr" packages:
            ids = multicall_map(session, session.getPackageID, ["httpd", "apr"])
            # ids is now [280, 632]

        :param KojiSessions koji_session: KojiSession to use for multicall.
        :param object koji_session_fnc: Python object representing the KojiSession method to call.
        :param list list_of_args: List of args which are passed to each call of koji_session_fnc.
        :param list list_of_kwargs: List of kwargs which are passed to each call of koji_session_fnc.
        """
        if list_of_args is None and list_of_kwargs is None:
            raise ValueError("One of list_of_args or list_of_kwargs must be set.")

        if (type(list_of_args) not in [type(None), list] or
                type(list_of_kwargs) not in [type(None), list]):
            raise ValueError("list_of_args and list_of_kwargs must be list or None.")

        if list_of_kwargs is None:
            list_of_kwargs = [{}] * len(list_of_args)
        if list_of_args is None:
            list_of_args = [[]] * len(list_of_kwargs)

        if len(list_of_args) != len(list_of_kwargs):
            raise ValueError("Length of list_of_args and list_of_kwargs must be the same.")

        koji_session.multicall = True
        for args, kwargs in zip(list_of_args, list_of_kwargs):
            if type(args) != list:
                args = [args]
            if type(kwargs) != dict:
                raise ValueError("Every item in list_of_kwargs must be a dict")
            koji_session_fnc(*args, **kwargs)

        responses = koji_session.multiCall(strict=True)

        if not responses:
            return None
        if type(responses) != list:
            raise ValueError(
                "Fault element was returned for multicall of method %r: %r" % (
                    koji_session_fnc, responses))

        results = []

        # For the response specification, see
        # https://web.archive.org/web/20060624230303/http://www.xmlrpc.com/discuss/msgReader$1208?mode=topic
        # Relevant part of this:
        # Multicall returns an array of responses. There will be one response for each call in
        # the original array. The result will either be a one-item array containing the result value,
        # or a struct of the form found inside the standard <fault> element.
        for response, args, kwargs in zip(responses, list_of_args, list_of_kwargs):
            if type(response) == list:
                if not response:
                    raise ValueError(
                        "Empty list returned for multicall of method %r with args %r, %r" % (
                        koji_session_fnc, args, kwargs))
                results.append(response[0])
            else:
                raise ValueError(
                    "Unexpected data returned for multicall of method %r with args %r, %r: %r" % (
                        koji_session_fnc, args, kwargs, response))

        return results

    @util.retry(wait_on=(xmlrpclib.ProtocolError, koji.GenericError))
    def retrying_multicall_map(self, *args, **kwargs):
        """
        Retrying version of multicall_map. This tries to retry the Koji call
        in case of koji.GenericError or xmlrpclib.ProtocolError.

        Please refer to koji_multicall_map for further specification of arguments.
        """
        return self.multicall_map(*args, **kwargs)


def get_buildroot_rpms(compose, task_id):
    """Get build root RPMs - either from runroot or local"""
    result = []
    if task_id:
        # runroot
        koji = KojiWrapper(compose.conf['koji_profile'])
        buildroot_infos = koji.koji_proxy.listBuildroots(taskID=task_id)
        buildroot_info = buildroot_infos[-1]
        data = koji.koji_proxy.listRPMs(componentBuildrootID=buildroot_info["id"])
        for rpm_info in data:
            fmt = "%(nvr)s.%(arch)s"
            result.append(fmt % rpm_info)
    else:
        # local
        retcode, output = run("rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'",
                              universal_newlines=True)
        for i in output.splitlines():
            if not i:
                continue
            result.append(i)
    return sorted(result)
