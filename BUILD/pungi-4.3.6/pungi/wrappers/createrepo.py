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


from kobo.shortcuts import force_list


class CreaterepoWrapper(object):
    def __init__(self, createrepo_c=True):
        if createrepo_c:
            self.createrepo = "createrepo_c"
            self.mergerepo = "mergerepo_c"
            self.modifyrepo = "modifyrepo_c"
        else:
            self.createrepo = "createrepo"
            self.mergerepo = "mergerepo"
            self.modifyrepo = "modifyrepo"

    def get_createrepo_cmd(
        self,
        directory,
        baseurl=None,
        outputdir=None,
        basedir=None,
        excludes=None,
        pkglist=None,
        groupfile=None,
        cachedir=None,
        update=True,
        update_md_path=None,
        skip_stat=False,
        checkts=False,
        split=False,
        pretty=True,
        database=True,
        checksum=None,
        unique_md_filenames=True,
        distro=None,
        content=None,
        repo=None,
        revision=None,
        deltas=False,
        oldpackagedirs=None,
        num_deltas=None,
        workers=None,
        use_xz=False,
        compress_type=None,
        extra_args=None,
    ):
        # groupfile = /path/to/comps.xml

        cmd = [self.createrepo, directory]

        if baseurl:
            cmd.append("--baseurl=%s" % baseurl)

        if outputdir:
            cmd.append("--outputdir=%s" % outputdir)

        if basedir:
            cmd.append("--basedir=%s" % basedir)

        for i in force_list(excludes or []):
            cmd.append("--excludes=%s" % i)

        if pkglist:
            cmd.append("--pkglist=%s" % pkglist)

        if groupfile:
            cmd.append("--groupfile=%s" % groupfile)

        if cachedir:
            cmd.append("--cachedir=%s" % cachedir)

        if update:
            cmd.append("--update")

        if update_md_path:
            cmd.append("--update-md-path=%s" % update_md_path)

        if skip_stat:
            cmd.append("--skip-stat")

        if checkts:
            cmd.append("--checkts")

        if split:
            cmd.append("--split")

        # HACK:
        if "createrepo_c" in self.createrepo:
            pretty = False
        if pretty:
            cmd.append("--pretty")

        if database:
            cmd.append("--database")
        else:
            cmd.append("--no-database")

        if checksum:
            cmd.append("--checksum=%s" % checksum)

        if unique_md_filenames:
            cmd.append("--unique-md-filenames")
        else:
            cmd.append("--simple-md-filenames")

        for i in force_list(distro or []):
            cmd.append("--distro=%s" % i)

        for i in force_list(content or []):
            cmd.append("--content=%s" % i)

        for i in force_list(repo or []):
            cmd.append("--repo=%s" % i)

        if revision:
            cmd.append("--revision=%s" % revision)

        if deltas:
            cmd.append("--deltas")

        for i in force_list(oldpackagedirs or []):
            cmd.append("--oldpackagedirs=%s" % i)

        if num_deltas:
            cmd.append("--num-deltas=%d" % int(num_deltas))

        if workers:
            cmd.append("--workers=%d" % int(workers))

        if use_xz:
            cmd.append("--xz")

        if compress_type:
            cmd.append("--compress-type=%s" % compress_type)

        if extra_args:
            cmd.extend(force_list(extra_args))

        return cmd

    def get_mergerepo_cmd(
        self,
        outputdir,
        repos,
        database=True,
        pkglist=None,
        nogroups=False,
        noupdateinfo=None,
    ):
        cmd = [self.mergerepo]

        cmd.append("--outputdir=%s" % outputdir)

        for repo in repos:
            if "://" not in repo:
                repo = "file://" + repo
            cmd.append("--repo=%s" % repo)

        if database:
            cmd.append("--database")
        else:
            cmd.append("--nodatabase")

        # XXX: a custom mergerepo hack, not in upstream git repo
        if pkglist:
            cmd.append("--pkglist=%s" % pkglist)

        if nogroups:
            cmd.append("--nogroups")

        if noupdateinfo:
            cmd.append("--noupdateinfo")

        return cmd

    def get_modifyrepo_cmd(
        self, repo_path, file_path, mdtype=None, compress_type=None, remove=False
    ):
        cmd = [self.modifyrepo]

        cmd.append(file_path)
        cmd.append(repo_path)

        if mdtype:
            cmd.append("--mdtype=%s" % mdtype)

        if remove:
            cmd.append("--remove")

        if compress_type:
            cmd.append("--compress")
            cmd.append("--compress-type=%s" % compress_type)

        return cmd
