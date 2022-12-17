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

from kobo.shortcuts import run

import pungi.phases.pkgset.pkgsets
from pungi.util import makedirs
from pungi.wrappers.pungi import PungiWrapper

from pungi.phases.pkgset.common import MaterializedPackageSet, get_all_arches
from pungi.phases.gather import get_prepopulate_packages, get_packages_to_gather
from pungi.linker import LinkerPool


import pungi.phases.pkgset.source


class PkgsetSourceRepos(pungi.phases.pkgset.source.PkgsetSourceBase):
    def __call__(self):
        package_sets, path_prefix = get_pkgset_from_repos(self.compose)
        return (package_sets, path_prefix)


def get_pkgset_from_repos(compose):
    # populate pkgset from yum repos
    # TODO: noarch hack - secondary arches, use x86_64 noarch where possible
    flist = []

    profiler = compose.conf["gather_profiler"]

    pool = LinkerPool.with_workers(10, "hardlink-or-copy", logger=compose._logger)

    path_prefix = (
        os.path.join(compose.paths.work.topdir(arch="global"), "download") + "/"
    )
    makedirs(path_prefix)

    seen_packages = set()
    for arch in compose.get_arches():
        # write a pungi config for remote repos and a local comps repo
        repos = {}
        for num, repo in enumerate(
            compose.conf["pkgset_repos"].get(arch, [])
            + compose.conf["pkgset_repos"].get("*", [])
        ):
            repo_path = repo
            if "://" not in repo_path:
                repo_path = os.path.join(compose.config_dir, repo)
            repos["repo-%s" % num] = repo_path

        comps_repo = None
        if compose.has_comps:
            repos["comps"] = compose.paths.work.comps_repo(arch=arch)
            comps_repo = "comps"
        write_pungi_config(compose, arch, None, repos=repos, comps_repo=comps_repo)

        pungi = PungiWrapper()
        pungi_conf = compose.paths.work.pungi_conf(arch=arch)
        pungi_log = compose.paths.log.log_file(arch, "pkgset_source")
        pungi_dir = compose.paths.work.pungi_download_dir(arch)

        backends = {
            "yum": pungi.get_pungi_cmd,
            "dnf": pungi.get_pungi_cmd_dnf,
        }
        get_cmd = backends[compose.conf["gather_backend"]]
        cmd = get_cmd(
            pungi_conf,
            destdir=pungi_dir,
            name="FOO",
            selfhosting=True,
            fulltree=True,
            multilib_methods=["all"],
            nodownload=False,
            full_archlist=True,
            arch=arch,
            cache_dir=compose.paths.work.pungi_cache_dir(arch=arch),
            profiler=profiler,
        )
        if compose.conf["gather_backend"] == "yum":
            cmd.append("--force")

        # TODO: runroot
        run(cmd, logfile=pungi_log, show_cmd=True, stdout=False)

        for root, dirs, files in os.walk(pungi_dir):
            for fn in files:
                if not fn.endswith(".rpm"):
                    continue
                if fn in seen_packages:
                    continue
                seen_packages.add(fn)
                src = os.path.join(root, fn)
                dst = os.path.join(path_prefix, os.path.basename(src))
                flist.append(dst)
                pool.queue_put((src, dst))

        # Clean up tmp dir
        # Workaround for rpm not honoring sgid bit which only appears when yum is used.
        yumroot_dir = os.path.join(pungi_dir, "work", arch, "yumroot")
        if os.path.isdir(yumroot_dir):
            try:
                shutil.rmtree(yumroot_dir)
            except Exception as e:
                compose.log_warning(
                    "Failed to clean up tmp dir: %s %s" % (yumroot_dir, str(e))
                )

    msg = "Linking downloaded pkgset packages"
    compose.log_info("[BEGIN] %s" % msg)
    pool.start()
    pool.stop()
    compose.log_info("[DONE ] %s" % msg)

    flist = sorted(set(flist))
    pkgset_global = populate_global_pkgset(compose, flist, path_prefix)

    package_set = MaterializedPackageSet.create(compose, pkgset_global, path_prefix)

    return [package_set], path_prefix


def populate_global_pkgset(compose, file_list, path_prefix):
    ALL_ARCHES = get_all_arches(compose)

    compose.log_info("Populating the global package set from a file list")
    pkgset = pungi.phases.pkgset.pkgsets.FilelistPackageSet(
        "repos", compose.conf["sigkeys"], logger=compose._logger, arches=ALL_ARCHES
    )
    pkgset.populate(file_list)

    return pkgset


def write_pungi_config(
    compose, arch, variant, repos=None, comps_repo=None, package_set=None
):
    """write pungi config (kickstart) for arch/variant"""
    pungi_wrapper = PungiWrapper()
    pungi_cfg = compose.paths.work.pungi_conf(variant=variant, arch=arch)

    compose.log_info(
        "Writing pungi config (arch: %s, variant: %s): %s", arch, variant, pungi_cfg
    )
    packages, grps = get_packages_to_gather(compose, arch, variant)

    # include *all* packages providing system-release
    if "system-release" not in packages:
        packages.append("system-release")

    prepopulate = get_prepopulate_packages(compose, arch, None)
    pungi_wrapper.write_kickstart(
        ks_path=pungi_cfg,
        repos=repos,
        groups=grps,
        packages=packages,
        exclude_packages=[],
        comps_repo=None,
        prepopulate=prepopulate,
    )
