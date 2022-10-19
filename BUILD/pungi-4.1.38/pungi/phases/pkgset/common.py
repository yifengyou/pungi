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

from kobo.shortcuts import run, relative_path
from kobo.threads import run_in_threads

import pungi.phases.pkgset.pkgsets
from pungi.arch import get_valid_arches
from pungi.wrappers.createrepo import CreaterepoWrapper
from pungi.util import is_arch_multilib, find_old_compose, iter_module_defaults
from pungi.phases.createrepo import add_modular_metadata


# TODO: per arch?
def populate_arch_pkgsets(compose, path_prefix, global_pkgset):
    result = {}
    exclusive_noarch = compose.conf['pkgset_exclusive_arch_considers_noarch']
    for arch in compose.get_arches():
        compose.log_info("Populating package set for arch: %s" % arch)
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib, add_src=True)
        pkgset = pungi.phases.pkgset.pkgsets.PackageSetBase(compose.conf["sigkeys"], logger=compose._logger, arches=arches)
        pkgset.merge(global_pkgset, arch, arches, exclusive_noarch=exclusive_noarch)
        pkgset.save_file_list(compose.paths.work.package_list(arch=arch), remove_path_prefix=path_prefix)
        result[arch] = pkgset
    return result


def get_create_global_repo_cmd(compose, path_prefix):
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    repo_dir_global = compose.paths.work.arch_repo(arch="global")

    if compose.DEBUG and os.path.isdir(os.path.join(repo_dir_global, "repodata")):
        compose.log_warning("[SKIP ] Running createrepo for the global package set")
        return

    # find an old compose suitable for repodata reuse
    old_compose_path = None
    update_md_path = None
    if compose.old_composes:
        old_compose_path = find_old_compose(
            compose.old_composes,
            compose.ci_base.release.short,
            compose.ci_base.release.version,
            compose.ci_base.release.type_suffix,
            compose.ci_base.base_product.short if compose.ci_base.release.is_layered else None,
            compose.ci_base.base_product.version if compose.ci_base.release.is_layered else None,
        )
        if old_compose_path is None:
            compose.log_info("No suitable old compose found in: %s" % compose.old_composes)
        else:
            repo_dir = compose.paths.work.arch_repo(arch="global")
            rel_path = relative_path(repo_dir, os.path.abspath(compose.topdir).rstrip("/") + "/")
            old_repo_dir = os.path.join(old_compose_path, rel_path)
            if os.path.isdir(old_repo_dir):
                compose.log_info("Using old repodata from: %s" % old_repo_dir)
                update_md_path = old_repo_dir

    # IMPORTANT: must not use --skip-stat here -- to make sure that correctly signed files are pulled in
    cmd = repo.get_createrepo_cmd(path_prefix, update=True, database=False, skip_stat=False,
                                  pkglist=compose.paths.work.package_list(arch="global"), outputdir=repo_dir_global,
                                  baseurl="file://%s" % path_prefix, workers=compose.conf["createrepo_num_workers"],
                                  update_md_path=update_md_path, checksum=createrepo_checksum)
    return cmd


def run_create_global_repo(compose, cmd):
    msg = "Running createrepo for the global package set"
    compose.log_info("[BEGIN] %s" % msg)

    run(cmd, logfile=compose.paths.log.log_file("global", "arch_repo"), show_cmd=True)
    compose.log_info("[DONE ] %s" % msg)


def create_arch_repos(compose, path_prefix):
    run_in_threads(
        _create_arch_repo,
        [(compose, arch, path_prefix) for arch in compose.get_arches()],
        threads=compose.conf['createrepo_num_threads'],
    )


def _create_arch_repo(worker_thread, args, task_num):
    """Create a single pkgset repo for given arch."""
    compose, arch, path_prefix = args
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    repo_dir_global = compose.paths.work.arch_repo(arch="global")
    repo_dir = compose.paths.work.arch_repo(arch=arch)
    msg = "Running createrepo for arch '%s'" % arch

    if compose.DEBUG and os.path.isdir(os.path.join(repo_dir, "repodata")):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)
    cmd = repo.get_createrepo_cmd(path_prefix, update=True, database=False, skip_stat=True,
                                  pkglist=compose.paths.work.package_list(arch=arch), outputdir=repo_dir,
                                  baseurl="file://%s" % path_prefix, workers=compose.conf["createrepo_num_workers"],
                                  update_md_path=repo_dir_global, checksum=createrepo_checksum)
    run(cmd, logfile=compose.paths.log.log_file(arch, "arch_repo"), show_cmd=True)
    # Add modulemd to the repo for all modules in all variants on this architecture.
    mmds = list(iter_module_defaults(compose.paths.work.module_defaults_dir()))
    for variant in compose.get_variants(arch=arch):
        mmds.extend(variant.arch_mmds.get(arch, {}).values())
    if mmds:
        add_modular_metadata(
            repo, repo_dir, mmds, compose.paths.log.log_file(arch, "arch_repo_modulemd")
        )

    compose.log_info("[DONE ] %s" % msg)
