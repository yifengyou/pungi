from __future__ import absolute_import
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
import shutil
import glob
import six
from six.moves import shlex_quote

import kobo.log
from kobo.shortcuts import run, force_list
from pungi.util import (explode_rpm_package, makedirs, copy_all, temp_dir,
                        retry)


class ScmBase(kobo.log.LoggingBase):
    def __init__(self, logger=None, command=None):
        kobo.log.LoggingBase.__init__(self, logger=logger)
        self.command = command

    @retry(interval=60, timeout=300, wait_on=RuntimeError)
    def retry_run(self, cmd, **kwargs):
        """
        @param cmd - cmd passed to kobo.shortcuts.run()
        @param **kwargs - args passed to kobo.shortcuts.run()
        """

        return run(cmd, **kwargs)

    def run_process_command(self, cwd):
        if self.command:
            self.log_debug('Running "%s"' % self.command)
            retcode, output = run(
                self.command,
                workdir=cwd,
                can_fail=True,
                stdin_data="",
                universal_newlines=True,
            )
            if retcode != 0:
                self.log_error('Output was: %r' % output)
                raise RuntimeError('%r failed with exit code %s'
                                   % (self.command, retcode))


class FileWrapper(ScmBase):
    def export_dir(self, scm_root, scm_dir, target_dir, scm_branch=None):
        self.log_debug("Exporting directory %s from current working directory..."
                       % (scm_dir))
        if scm_root:
            raise ValueError("FileWrapper: 'scm_root' should be empty.")
        dirs = glob.glob(scm_dir)
        if not dirs:
            raise RuntimeError('No directories matched, can not export.')
        for i in dirs:
            copy_all(i, target_dir)

    def export_file(self, scm_root, scm_file, target_dir, scm_branch=None):
        if scm_root:
            raise ValueError("FileWrapper: 'scm_root' should be empty.")
        self.log_debug("Exporting file %s from current working directory..."
                       % (scm_file))
        files = glob.glob(scm_file)
        if not files:
            raise RuntimeError('No files matched, can not export.')
        for i in files:
            target_path = os.path.join(target_dir, os.path.basename(i))
            shutil.copy2(i, target_path)


class CvsWrapper(ScmBase):
    def export_dir(self, scm_root, scm_dir, target_dir, scm_branch=None):
        scm_dir = scm_dir.lstrip("/")
        scm_branch = scm_branch or "HEAD"
        with temp_dir() as tmp_dir:
            self.log_debug("Exporting directory %s from CVS %s (branch %s)..."
                           % (scm_dir, scm_root, scm_branch))
            self.retry_run(["/usr/bin/cvs", "-q", "-d", scm_root, "export", "-r", scm_branch, scm_dir],
                           workdir=tmp_dir, show_cmd=True)
            copy_all(os.path.join(tmp_dir, scm_dir), target_dir)

    def export_file(self, scm_root, scm_file, target_dir, scm_branch=None):
        scm_file = scm_file.lstrip("/")
        scm_branch = scm_branch or "HEAD"
        with temp_dir() as tmp_dir:
            target_path = os.path.join(target_dir, os.path.basename(scm_file))
            self.log_debug("Exporting file %s from CVS %s (branch %s)..." % (scm_file, scm_root, scm_branch))
            self.retry_run(["/usr/bin/cvs", "-q", "-d", scm_root, "export", "-r", scm_branch, scm_file],
                           workdir=tmp_dir, show_cmd=True)

            makedirs(target_dir)
            shutil.copy2(os.path.join(tmp_dir, scm_file), target_path)


class GitWrapper(ScmBase):

    def _clone(self, repo, branch, destdir):
        """Get a single commit from a repository.

        We can't use git-archive as that does not support arbitrary hash as
        commit, and git-clone can only get a branch too. Thus the workaround is
        to create a new local repo, fetch the commit from remote and then check
        it out. If that fails, we get a full clone.

        Finally the post-processing command is ran.
        """
        if "://" not in repo:
            repo = "file://%s" % repo

        run(["git", "init"], workdir=destdir)
        try:
            run(["git", "fetch", "--depth=1", repo, branch], workdir=destdir)
            run(["git", "checkout", "FETCH_HEAD"], workdir=destdir)
        except RuntimeError:
            # Fetch failed, to do a full clone we add a remote to our empty
            # repo, get its content and check out the reference we want.
            run(["git", "remote", "add", "origin", repo], workdir=destdir)
            self.retry_run(["git", "remote", "update", "origin"], workdir=destdir)
            run(["git", "checkout", branch], workdir=destdir)

        self.run_process_command(destdir)

    def export_dir(self, scm_root, scm_dir, target_dir, scm_branch=None):
        scm_dir = scm_dir.lstrip("/")
        scm_branch = scm_branch or "master"

        with temp_dir() as tmp_dir:
            self.log_debug("Exporting directory %s from git %s (branch %s)..."
                           % (scm_dir, scm_root, scm_branch))

            self._clone(scm_root, scm_branch, tmp_dir)

            copy_all(os.path.join(tmp_dir, scm_dir), target_dir)

    def export_file(self, scm_root, scm_file, target_dir, scm_branch=None):
        scm_file = scm_file.lstrip("/")
        scm_branch = scm_branch or "master"

        with temp_dir() as tmp_dir:
            target_path = os.path.join(target_dir, os.path.basename(scm_file))

            self.log_debug("Exporting file %s from git %s (branch %s)..."
                           % (scm_file, scm_root, scm_branch))

            self._clone(scm_root, scm_branch, tmp_dir)

            makedirs(target_dir)
            shutil.copy2(os.path.join(tmp_dir, scm_file), target_path)


class RpmScmWrapper(ScmBase):
    def _list_rpms(self, pats):
        for pat in force_list(pats):
            for rpm in glob.glob(pat):
                yield rpm

    def export_dir(self, scm_root, scm_dir, target_dir, scm_branch=None):
        for rpm in self._list_rpms(scm_root):
            scm_dir = scm_dir.lstrip("/")
            with temp_dir() as tmp_dir:
                self.log_debug("Extracting directory %s from RPM package %s..." % (scm_dir, rpm))
                explode_rpm_package(rpm, tmp_dir)

                makedirs(target_dir)
                # "dir" includes the whole directory while "dir/" includes it's content
                if scm_dir.endswith("/"):
                    copy_all(os.path.join(tmp_dir, scm_dir), target_dir)
                else:
                    run("cp -a %s %s/" % (shlex_quote(os.path.join(tmp_dir, scm_dir)),
                                          shlex_quote(target_dir)))

    def export_file(self, scm_root, scm_file, target_dir, scm_branch=None):
        for rpm in self._list_rpms(scm_root):
            scm_file = scm_file.lstrip("/")
            with temp_dir() as tmp_dir:
                self.log_debug("Exporting file %s from RPM file %s..." % (scm_file, rpm))
                explode_rpm_package(rpm, tmp_dir)

                makedirs(target_dir)
                for src in glob.glob(os.path.join(tmp_dir, scm_file)):
                    dst = os.path.join(target_dir, os.path.basename(src))
                    shutil.copy2(src, dst)


def _get_wrapper(scm_type, *args, **kwargs):
    SCM_WRAPPERS = {
        "file": FileWrapper,
        "cvs": CvsWrapper,
        "git": GitWrapper,
        "rpm": RpmScmWrapper,
    }
    try:
        return SCM_WRAPPERS[scm_type](*args, **kwargs)
    except KeyError:
        raise ValueError("Unknown SCM type: %s" % scm_type)


def get_file_from_scm(scm_dict, target_path, logger=None):
    """
    Copy one or more files from source control to a target path. A list of files
    created in ``target_path`` is returned.

    :param scm_dict:
        A dictionary describing the source control repository; this can
        optionally be a path to a directory on the local filesystem or reference
        an RPM. Supported keys for the dictionary are ``scm``, ``repo``,
        ``file``, and ``branch``. ``scm`` is the type of version control system
        used ('git', 'cvs', 'rpm', etc.), ``repo`` is the URL of the repository
        (or, if 'rpm' is the ``scm``, the package name), ``file`` is either a
        path or list of paths to copy, and ``branch`` is the branch to check
        out, if any.

    :param target_path:
        The destination path for the files being copied.

    :param logger:
        The logger to use for any logging performed.

    Example:
        >>> scm_dict = {
        >>>     'scm': 'git',
        >>>     'repo': 'https://pagure.io/pungi.git',
        >>>     'file': ['share/variants.dtd'],
        >>> }
        >>> target_path = '/tmp/path/'
        >>> get_file_from_scm(scm_dict, target_path)
        ['/tmp/path/share/variants.dtd']
    """
    if isinstance(scm_dict, six.string_types):
        scm_type = "file"
        scm_repo = None
        scm_file = os.path.abspath(scm_dict)
        scm_branch = None
        command = None
    else:
        scm_type = scm_dict["scm"]
        scm_repo = scm_dict["repo"]
        scm_file = scm_dict["file"]
        scm_branch = scm_dict.get("branch", None)
        command = scm_dict.get('command')

    scm = _get_wrapper(scm_type, logger=logger, command=command)

    files_copied = []
    for i in force_list(scm_file):
        with temp_dir(prefix="scm_checkout_") as tmp_dir:
            scm.export_file(scm_repo, i, scm_branch=scm_branch, target_dir=tmp_dir)
            files_copied += copy_all(tmp_dir, target_path)
    return files_copied


def get_dir_from_scm(scm_dict, target_path, logger=None):
    """
    Copy a directory from source control to a target path. A list of files
    created in ``target_path`` is returned.

    :param scm_dict:
        A dictionary describing the source control repository; this can
        optionally be a path to a directory on the local filesystem or reference
        an RPM. Supported keys for the dictionary are ``scm``, ``repo``,
        ``dir``, and ``branch``. ``scm`` is the type of version control system
        used ('git', 'cvs', 'rpm', etc.), ``repo`` is the URL of the repository
        (or, if 'rpm' is the ``scm``, the package name), ``dir`` is the
        directory to copy, and ``branch`` is the branch to check out, if any.

    :param target_path:
        The destination path for the directory being copied.

    :param logger:
        The logger to use for any logging performed.

    Example:
        >>> scm_dict = {
        >>>     'scm': 'git',
        >>>     'repo': 'https://pagure.io/pungi.git',
        >>>     'dir': 'share,
        >>> }
        >>> target_path = '/tmp/path/'
        >>> get_dir_from_scm(scm_dict, target_path)
        ['/tmp/path/share/variants.dtd', '/tmp/path/share/rawhide-fedora.ks', ...]
    """
    if isinstance(scm_dict, six.string_types):
        scm_type = "file"
        scm_repo = None
        scm_dir = os.path.abspath(scm_dict)
        scm_branch = None
        command = None
    else:
        scm_type = scm_dict["scm"]
        scm_repo = scm_dict.get("repo", None)
        scm_dir = scm_dict["dir"]
        scm_branch = scm_dict.get("branch", None)
        command = scm_dict.get("command")

    scm = _get_wrapper(scm_type, logger=logger, command=command)

    with temp_dir(prefix="scm_checkout_") as tmp_dir:
        scm.export_dir(scm_repo, scm_dir, scm_branch=scm_branch, target_dir=tmp_dir)
        files_copied = copy_all(tmp_dir, target_path)
    return files_copied
