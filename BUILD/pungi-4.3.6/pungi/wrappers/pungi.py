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

from .. import util


PACKAGES_RE = {
    "rpm": re.compile(r"^RPM(\((?P<flags>[^\)]*)\))?: (?P<path>.+)$"),
    "srpm": re.compile(r"^SRPM(\((?P<flags>[^\)]*)\))?: (?P<path>.+)$"),
    "debuginfo": re.compile(r"^DEBUGINFO(\((?P<flags>[^\)]*)\))?: (?P<path>.+)$"),
}


UNRESOLVED_DEPENDENCY_RE = re.compile(r"^.*Unresolvable dependency (.+) in ([^ ]+).*$")

MISSING_COMPS_PACKAGE_RE = re.compile(
    r"^.*Could not find a match for (.+) in any configured repo"
)


def _write_ks_section(f, section, lines):
    if lines:
        f.write("\n%%%s\n" % section)
        for i in sorted(lines):
            f.write("%s\n" % i)

        f.write("%end\n")


class PungiWrapper(object):
    def write_kickstart(
        self,
        ks_path,
        repos,
        groups,
        packages,
        exclude_packages=None,
        comps_repo=None,
        lookaside_repos=None,
        fulltree_excludes=None,
        multilib_blacklist=None,
        multilib_whitelist=None,
        prepopulate=None,
    ):
        groups = groups or []
        exclude_packages = exclude_packages or {}
        lookaside_repos = lookaside_repos or {}
        # repos = {name: url}
        fulltree_excludes = fulltree_excludes or set()
        multilib_blacklist = multilib_blacklist or set()
        multilib_whitelist = multilib_whitelist or set()
        ks_path = os.path.abspath(ks_path)

        ks_dir = os.path.dirname(ks_path)
        util.makedirs(ks_dir)

        kickstart = open(ks_path, "w")

        # repos
        for repo_name, repo_url in list(repos.items()) + list(lookaside_repos.items()):
            if "://" not in repo_url:
                repo_url = "file://" + os.path.abspath(repo_url)
            repo_str = "repo --name=%s --baseurl=%s" % (repo_name, repo_url)
            # TODO: make sure pungi works when there are no comps in repodata
            # XXX: if groups are ignored, langpacks are ignored too
            if comps_repo and repo_name != comps_repo:
                repo_str += " --ignoregroups=true"
            kickstart.write(repo_str + "\n")

        # %packages
        kickstart.write("\n")
        kickstart.write("%packages\n")

        for group in sorted(groups):
            kickstart.write("@%s --optional\n" % group)

        for package in sorted(packages):
            kickstart.write("%s\n" % package)

        for package in sorted(exclude_packages):
            kickstart.write("-%s\n" % package)

        kickstart.write("%end\n")

        _write_ks_section(kickstart, "fulltree-excludes", fulltree_excludes)
        _write_ks_section(kickstart, "multilib-blacklist", multilib_blacklist)
        _write_ks_section(kickstart, "multilib-whitelist", multilib_whitelist)
        _write_ks_section(kickstart, "prepopulate", prepopulate)

        kickstart.close()

    def get_pungi_cmd(
        self,
        config,
        destdir,
        name,
        version=None,
        flavor=None,
        selfhosting=False,
        fulltree=False,
        greedy=None,
        nodeps=False,
        nodownload=True,
        full_archlist=False,
        arch=None,
        cache_dir=None,
        lookaside_repos=None,
        multilib_methods=None,
        profiler=False,
    ):
        cmd = ["pungi"]

        # Gather stage
        cmd.append("-G")

        # path to a kickstart file
        cmd.append("--config=%s" % config)

        # destdir is optional in Pungi (defaults to current dir), but
        # want it mandatory here
        cmd.append("--destdir=%s" % destdir)

        # name
        cmd.append("--name=%s" % name)

        # version; optional, defaults to datestamp
        if version:
            cmd.append("--ver=%s" % version)

        # rhel variant; optional
        if flavor:
            cmd.append("--flavor=%s" % flavor)

        # turn selfhosting on
        if selfhosting:
            cmd.append("--selfhosting")

        # NPLB
        if fulltree:
            cmd.append("--fulltree")

        greedy = greedy or "none"
        cmd.append("--greedy=%s" % greedy)

        if nodeps:
            cmd.append("--nodeps")

        # don't download packages, just print paths
        if nodownload:
            cmd.append("--nodownload")

        if full_archlist:
            cmd.append("--full-archlist")

        if arch:
            cmd.append("--arch=%s" % arch)

        if multilib_methods:
            for i in multilib_methods:
                cmd.append("--multilib=%s" % i)

        if cache_dir:
            cmd.append("--cachedir=%s" % cache_dir)

        if lookaside_repos:
            for i in lookaside_repos:
                cmd.append("--lookaside-repo=%s" % i)

        return cmd

    def get_pungi_cmd_dnf(
        self,
        config,
        destdir,
        name,
        version=None,
        flavor=None,
        selfhosting=False,
        fulltree=False,
        greedy=None,
        nodeps=False,
        nodownload=True,
        full_archlist=False,
        arch=None,
        cache_dir=None,
        lookaside_repos=None,
        multilib_methods=None,
        profiler=False,
    ):
        cmd = ["pungi-gather"]

        # path to a kickstart file
        cmd.append("--config=%s" % config)

        # turn selfhosting on
        if selfhosting:
            cmd.append("--selfhosting")

        # NPLB
        if fulltree:
            cmd.append("--fulltree")

        greedy = greedy or "none"
        cmd.append("--greedy=%s" % greedy)

        if nodeps:
            cmd.append("--nodeps")

        if arch:
            cmd.append("--arch=%s" % arch)

        if not nodownload:
            cmd.append("--download-to=%s" % destdir)

        if multilib_methods:
            for i in multilib_methods:
                cmd.append("--multilib=%s" % i)

        if lookaside_repos:
            for i in lookaside_repos:
                cmd.append("--lookaside=%s" % i)

        if profiler:
            cmd.append("--profiler")

        return cmd

    def parse_log(self, f):
        packages = dict(((i, []) for i in PACKAGES_RE))
        broken_deps = {}
        missing_comps = set()

        for line in f:
            for file_type, pattern in PACKAGES_RE.items():
                match = pattern.match(line)
                if match:
                    item = {}
                    item["path"] = match.groupdict()["path"].strip()
                    if item["path"].startswith("file://"):
                        item["path"] = item["path"][7:]
                    flags = match.groupdict()["flags"] or ""
                    flags = sorted([i.strip() for i in flags.split(",") if i.strip()])
                    item["flags"] = flags
                    packages[file_type].append(item)
                    break

            match = MISSING_COMPS_PACKAGE_RE.match(line)
            if match:
                missing_comps.add(match.group(1))

            match = UNRESOLVED_DEPENDENCY_RE.match(line)
            if match:
                broken_deps.setdefault(match.group(2), set()).add(match.group(1))

        return packages, broken_deps, missing_comps

    def run_pungi(
        self,
        ks_file,
        destdir,
        name,
        selfhosting=False,
        fulltree=False,
        greedy="",
        cache_dir=None,
        arch="",
        multilib_methods=[],
        nodeps=False,
        lookaside_repos=[],
    ):
        """
        This is a replacement for get_pungi_cmd that runs it in-process. Not
        all arguments are supported.
        """
        from .. import ks, gather, config

        ksparser = ks.get_ksparser(ks_path=ks_file)
        cfg = config.Config()
        cfg.set("pungi", "destdir", destdir)
        cfg.set("pungi", "family", name)
        cfg.set("pungi", "iso_basename", name)
        cfg.set("pungi", "fulltree", str(fulltree))
        cfg.set("pungi", "selfhosting", str(selfhosting))
        cfg.set("pungi", "cachedir", cache_dir)
        cfg.set("pungi", "full_archlist", "True")
        cfg.set("pungi", "workdirbase", "%s/work" % destdir)
        cfg.set("pungi", "greedy", greedy)
        cfg.set("pungi", "nosource", "False")
        cfg.set("pungi", "nodebuginfo", "False")
        cfg.set("pungi", "force", "False")
        cfg.set("pungi", "resolve_deps", str(not nodeps))
        if arch:
            cfg.set("pungi", "arch", arch)
        if multilib_methods:
            cfg.set("pungi", "multilib", " ".join(multilib_methods))
        if lookaside_repos:
            cfg.set("pungi", "lookaside_repos", " ".join(lookaside_repos))

        mypungi = gather.Pungi(cfg, ksparser)

        with open(os.path.join(destdir, "out"), "w") as f:
            with mypungi.yumlock:
                mypungi._inityum()
                mypungi.gather()

                for line in mypungi.list_packages():
                    flags_str = ",".join(line["flags"])
                    if flags_str:
                        flags_str = "(%s)" % flags_str
                    f.write("RPM%s: %s\n" % (flags_str, line["path"]))
                mypungi.makeCompsFile()
                mypungi.getDebuginfoList()
                for line in mypungi.list_debuginfo():
                    flags_str = ",".join(line["flags"])
                    if flags_str:
                        flags_str = "(%s)" % flags_str
                    f.write("DEBUGINFO%s: %s\n" % (flags_str, line["path"]))
                for line in mypungi.list_srpms():
                    flags_str = ",".join(line["flags"])
                    if flags_str:
                        flags_str = "(%s)" % flags_str
                    f.write("SRPM%s: %s\n" % (flags_str, line["path"]))
