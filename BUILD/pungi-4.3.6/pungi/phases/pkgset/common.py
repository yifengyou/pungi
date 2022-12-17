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
import threading

from kobo.shortcuts import run
from kobo.threads import run_in_threads

from pungi.arch import get_valid_arches
from pungi.wrappers.createrepo import CreaterepoWrapper
from pungi.util import (
    copy_all,
    is_arch_multilib,
    PartialFuncWorkerThread,
    PartialFuncThreadPool,
)
from pungi.module_util import (
    Modulemd,
    collect_module_defaults,
    collect_module_obsoletes,
)
from pungi.phases.createrepo import add_modular_metadata


def populate_arch_pkgsets(compose, path_prefix, global_pkgset):
    result = {}
    exclusive_noarch = compose.conf["pkgset_exclusive_arch_considers_noarch"]
    for arch in compose.get_arches():
        compose.log_info("Populating package set for arch: %s", arch)
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib, add_src=True)
        pkgset = global_pkgset.subset(arch, arches, exclusive_noarch=exclusive_noarch)
        pkgset.save_file_list(
            compose.paths.work.package_list(arch=arch, pkgset=global_pkgset),
            remove_path_prefix=path_prefix,
        )
        result[arch] = pkgset
    return result


def get_create_global_repo_cmd(compose, path_prefix, repo_dir_global, pkgset):
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)

    # find an old compose suitable for repodata reuse
    update_md_path = None
    old_repo_dir = compose.paths.old_compose_path(
        compose.paths.work.pkgset_repo(pkgset.name, arch="global")
    )
    if old_repo_dir:
        if os.path.isdir(os.path.join(old_repo_dir, "repodata")):
            compose.log_info("Using old repodata from: %s", old_repo_dir)
            update_md_path = old_repo_dir
    else:
        compose.log_info("No suitable old compose found in: %s", compose.old_composes)

    # IMPORTANT: must not use --skip-stat here -- to make sure that correctly
    # signed files are pulled in
    cmd = repo.get_createrepo_cmd(
        path_prefix,
        update=True,
        database=False,
        skip_stat=False,
        pkglist=compose.paths.work.package_list(arch="global", pkgset=pkgset),
        outputdir=repo_dir_global,
        baseurl="file://%s" % path_prefix,
        workers=compose.conf["createrepo_num_workers"],
        update_md_path=update_md_path,
        checksum=createrepo_checksum,
    )
    return cmd


def run_create_global_repo(compose, cmd, logfile):
    msg = "Running createrepo for the global package set"
    compose.log_info("[BEGIN] %s", msg)
    run(cmd, logfile=logfile, show_cmd=True)
    compose.log_info("[DONE ] %s", msg)


def create_arch_repos(compose, path_prefix, paths, pkgset, mmds):
    run_in_threads(
        _create_arch_repo,
        [
            (
                compose,
                arch,
                path_prefix,
                paths,
                pkgset,
                mmds.get(arch) if mmds else None,
            )
            for arch in compose.get_arches()
        ],
        threads=compose.conf["createrepo_num_threads"],
    )


def _create_arch_repo(worker_thread, args, task_num):
    """Create a single pkgset repo for given arch."""
    compose, arch, path_prefix, paths, pkgset, mmd = args
    repo_dir = compose.paths.work.pkgset_repo(pkgset.name, arch=arch)
    paths[arch] = repo_dir

    # Try to reuse arch repo from old compose
    reuse = getattr(pkgset, "reuse", None)
    if reuse:
        old_repo_dir = compose.paths.old_compose_path(repo_dir)
        if old_repo_dir and os.path.isdir(old_repo_dir):
            msg = "Copying repodata for reuse: %s" % old_repo_dir
            try:
                compose.log_info("[BEGIN] %s", msg)
                copy_all(old_repo_dir, repo_dir)
                compose.log_info("[DONE ] %s", msg)
                return
            except Exception as e:
                compose.log_debug(str(e))
                compose.log_info("[FAILED] %s will try to create arch repo", msg)

    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    repo_dir_global = compose.paths.work.pkgset_repo(pkgset.name, arch="global")
    msg = "Running createrepo for arch '%s'" % arch

    compose.log_info("[BEGIN] %s", msg)
    cmd = repo.get_createrepo_cmd(
        path_prefix,
        update=True,
        database=False,
        skip_stat=True,
        pkglist=compose.paths.work.package_list(arch=arch, pkgset=pkgset),
        outputdir=repo_dir,
        baseurl="file://%s" % path_prefix,
        workers=compose.conf["createrepo_num_workers"],
        update_md_path=repo_dir_global,
        checksum=createrepo_checksum,
    )
    run(
        cmd,
        logfile=compose.paths.log.log_file(arch, "arch_repo.%s" % pkgset.name),
        show_cmd=True,
    )
    # Add modulemd to the repo for all modules in all variants on this architecture.
    if Modulemd and mmd:
        names = set(x.get_module_name() for x in mmd)
        overrides_dir = compose.conf.get("module_defaults_override_dir")
        mod_index = collect_module_defaults(
            compose.paths.work.module_defaults_dir(), names, overrides_dir=overrides_dir
        )
        mod_index = collect_module_obsoletes(
            compose.paths.work.module_obsoletes_dir(), names, mod_index
        )
        for x in mmd:
            mod_index.add_module_stream(x)
        add_modular_metadata(
            repo,
            repo_dir,
            mod_index,
            compose.paths.log.log_file(arch, "arch_repo_modulemd.%s" % pkgset.name),
        )

    compose.log_info("[DONE ] %s", msg)


class MaterializedPackageSet(object):
    """A wrapper for PkgsetBase object that represents the package set created
    as repos on the filesystem.
    """

    def __init__(self, package_sets, paths):
        self.package_sets = package_sets
        self.paths = paths

    @property
    def name(self):
        return self.package_sets["global"].name

    def __getitem__(self, key):
        """Direct access to actual package set for particular arch."""
        return self.package_sets[key]

    def get(self, arch, default=None):
        """Get package set for particular arch."""
        return self.package_sets.get(arch, default or [])

    def iter_packages(self, arch=None):
        """Yield all packages in the set, optionally filtering for some arch
        only.
        """
        if not arch:
            for arch in self.package_sets:
                for file_path in self.get(arch):
                    yield self.package_sets[arch][file_path]
        else:
            for file_path in self.get(arch):
                yield self.package_sets[arch][file_path]

    @classmethod
    def create(klass, compose, pkgset_global, path_prefix, mmd=None):
        """Create per-arch pkgsets and create repodata for each arch."""
        repo_dir_global = compose.paths.work.pkgset_repo(
            pkgset_global.name, arch="global"
        )
        paths = {"global": repo_dir_global}

        pkgset_global.save_file_list(
            compose.paths.work.package_list(arch="global", pkgset=pkgset_global),
            remove_path_prefix=path_prefix,
        )
        pkgset_global.save_file_cache(
            compose.paths.work.pkgset_file_cache(pkgset_global.name)
        )

        if getattr(pkgset_global, "reuse", None) is None:
            cmd = get_create_global_repo_cmd(
                compose, path_prefix, repo_dir_global, pkgset_global
            )
            logfile = compose.paths.log.log_file(
                "global", "arch_repo.%s" % pkgset_global.name
            )
            t = threading.Thread(
                target=run_create_global_repo, args=(compose, cmd, logfile)
            )
            t.start()

        package_sets = populate_arch_pkgsets(compose, path_prefix, pkgset_global)
        package_sets["global"] = pkgset_global

        if getattr(pkgset_global, "reuse", None) is None:
            t.join()

        create_arch_repos(compose, path_prefix, paths, pkgset_global, mmd)

        return klass(package_sets, paths)

    @classmethod
    def create_many(klass, create_partials):
        """
        Creates multiple MaterializedPackageSet in threads.

        :param list of functools.partial create_partials: List of Partial objects
            created using functools.partial(MaterializedPackageSet.create, compose,
            pkgset_global, path_prefix, mmd=mmd).
        :return: List of MaterializedPackageSet objects.
        """
        # Create two pools - small pool for small package sets and big pool for
        # big package sets. This ensure there will not be too many createrepo
        # tasks which would need lot of CPU or memory at the same time.
        big_pool = PartialFuncThreadPool()
        big_pool.add(PartialFuncWorkerThread(big_pool))
        small_pool = PartialFuncThreadPool()
        for i in range(10):
            small_pool.add(PartialFuncWorkerThread(small_pool))

        # Divide the package sets into big_pool/small_pool based on their size.
        for partial in create_partials:
            pkgset = partial.args[1]
            if len(pkgset) < 500:
                small_pool.queue_put(partial)
            else:
                big_pool.queue_put(partial)

        small_pool.start()
        big_pool.start()
        try:
            small_pool.stop()
        except Exception:
            big_pool.kill()
            raise
        finally:
            big_pool.stop()

        return small_pool.results + big_pool.results


def get_all_arches(compose):
    all_arches = set(["src"])
    for arch in compose.get_arches():
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib)
        all_arches.update(arches)
    return all_arches
