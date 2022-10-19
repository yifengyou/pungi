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

from kobo.shortcuts import run
from kobo.pkgset import SimpleRpmWrapper, RpmWrapper
from kobo.rpmlib import parse_nvra

from pungi.util import get_arch_variant_data, temp_dir
from pungi.wrappers.pungi import PungiWrapper

from pungi.arch import tree_arch_to_yum_arch, get_valid_arches
import pungi.phases.gather

import pungi.phases.gather.method


class GatherMethodDeps(pungi.phases.gather.method.GatherMethodBase):
    enabled = True

    def __call__(self, arch, variant, packages, groups, filter_packages, multilib_whitelist, multilib_blacklist, package_sets, path_prefix=None, fulltree_excludes=None, prepopulate=None):
        # result = {
        #     "rpm": [],
        #     "srpm": [],
        #     "debuginfo": [],
        # }

        write_pungi_config(self.compose, arch, variant, packages, groups, filter_packages,
                           multilib_whitelist, multilib_blacklist,
                           fulltree_excludes=fulltree_excludes, prepopulate=prepopulate,
                           source_name=self.source_name, package_sets=package_sets)
        result, missing_deps = resolve_deps(self.compose, arch, variant, source_name=self.source_name)
        raise_on_invalid_sigkeys(arch, variant, package_sets, result)
        check_deps(self.compose, arch, variant, missing_deps)
        return result


def raise_on_invalid_sigkeys(arch, variant, package_sets, result):
    """
    Raises RuntimeError if some package in compose is signed with an invalid
    sigkey.
    """
    invalid_sigkey_rpms = []
    for package in result["rpm"]:
        name = parse_nvra(package["path"])["name"]
        for forbidden_package in package_sets["global"].invalid_sigkey_rpms:
            if name == forbidden_package["name"]:
                invalid_sigkey_rpms.append(forbidden_package)

    if invalid_sigkey_rpms:
        package_sets["global"].raise_invalid_sigkeys_exception(
            invalid_sigkey_rpms)


def _format_packages(pkgs):
    """Sort packages and merge name with arch."""
    for pkg, pkg_arch in sorted(pkgs):
        if type(pkg) in [SimpleRpmWrapper, RpmWrapper]:
            pkg_name = pkg.name
        else:
            pkg_name = pkg
        if pkg_arch:
            yield '%s.%s' % (pkg_name, pkg_arch)
        else:
            yield pkg_name


def write_pungi_config(compose, arch, variant, packages, groups, filter_packages,
                       multilib_whitelist, multilib_blacklist, fulltree_excludes=None,
                       prepopulate=None, source_name=None, package_sets=None):
    """write pungi config (kickstart) for arch/variant"""
    pungi_wrapper = PungiWrapper()
    pungi_cfg = compose.paths.work.pungi_conf(variant=variant, arch=arch, source_name=source_name)
    msg = "Writing pungi config (arch: %s, variant: %s): %s" % (arch, variant, pungi_cfg)

    if compose.DEBUG and os.path.isfile(pungi_cfg):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info(msg)

    repos = {
        "pungi-repo": compose.paths.work.arch_repo(arch=arch),
    }
    if compose.has_comps:
        repos["comps-repo"] = compose.paths.work.comps_repo(arch=arch, variant=variant)
    if variant.type == "optional":
        for var in variant.parent.get_variants(
                arch=arch, types=["self", "variant", "addon", "layered-product"]):
            repos['%s-comps' % var.uid] = compose.paths.work.comps_repo(arch=arch, variant=var)
    if variant.type in ["addon", "layered-product"]:
        repos['parent-comps'] = compose.paths.work.comps_repo(arch=arch, variant=variant.parent)

    lookaside_repos = {}
    for i, repo_url in enumerate(pungi.phases.gather.get_lookaside_repos(compose, arch, variant)):
        lookaside_repos["lookaside-repo-%s" % i] = repo_url

    packages_str = list(_format_packages(packages))
    filter_packages_str = list(_format_packages(filter_packages))

    if not groups and not packages_str and not prepopulate:
        raise RuntimeError(
            'No packages included in %s.%s (no comps groups, no input packages, no prepopulate)'
            % (variant.uid, arch))

    package_whitelist = set()
    if variant.pkgset:
        multilib = get_arch_variant_data(compose.conf, 'multilib', arch, variant)
        for i in get_valid_arches(arch, multilib=multilib, add_noarch=True, add_src=True):
            for rpm_obj in variant.pkgset.rpms_by_arch.get(i, []):
                package_whitelist.add(
                    '{0.name}-{1}:{0.version}-{0.release}'.format(rpm_obj, rpm_obj.epoch or 0))

        # If the variant contains just modules or just comps groups, the pkgset
        # is sufficient and contains all necessary packages.

        has_additional_pkgs = get_arch_variant_data(
            compose.conf, "additional_packages", arch, variant
        )
        has_traditional_content = variant.groups or has_additional_pkgs
        if has_traditional_content and variant.modules is not None and package_sets:
            # The variant is hybrid. The modular builds are already available.
            # We need to add packages from base tag, but only if they are not
            # already on the whitelist.
            package_names = set(p.rsplit('-', 2)[0] for p in package_whitelist)
            for i in get_valid_arches(arch, multilib=multilib, add_noarch=True, add_src=True):
                for rpm_obj in package_sets[arch].rpms_by_arch.get(i, []):
                    if rpm_obj.name in package_names:
                        # We already have a package with this name in the whitelist, skip it.
                        continue
                    package_whitelist.add(
                        '{0.name}-{1}:{0.version}-{0.release}'.format(rpm_obj, rpm_obj.epoch or 0))

    pungi_wrapper.write_kickstart(
        ks_path=pungi_cfg, repos=repos, groups=groups, packages=packages_str,
        exclude_packages=filter_packages_str,
        lookaside_repos=lookaside_repos, fulltree_excludes=fulltree_excludes,
        multilib_whitelist=multilib_whitelist, multilib_blacklist=multilib_blacklist,
        prepopulate=prepopulate, package_whitelist=package_whitelist)


def resolve_deps(compose, arch, variant, source_name=None):
    pungi_wrapper = PungiWrapper()
    pungi_log = compose.paths.work.pungi_log(arch, variant, source_name=source_name)

    msg = "Running pungi (arch: %s, variant: %s)" % (arch, variant)
    if compose.DEBUG and os.path.exists(pungi_log):
        compose.log_warning("[SKIP ] %s" % msg)
        with open(pungi_log, "r") as f:
            res, broken_deps, _ = pungi_wrapper.parse_log(f)
            return res, broken_deps

    compose.log_info("[BEGIN] %s" % msg)
    pungi_conf = compose.paths.work.pungi_conf(arch, variant, source_name=source_name)

    multilib_methods = get_arch_variant_data(compose.conf, 'multilib', arch, variant)

    greedy_method = compose.conf["greedy_method"]

    # variant
    fulltree = compose.conf["gather_fulltree"]
    selfhosting = compose.conf["gather_selfhosting"]

    # profiling
    profiler = compose.conf["gather_profiler"]

    # optional
    if variant.type == "optional":
        fulltree = True
        selfhosting = True

    # addon
    if variant.type in ["addon", "layered-product"]:
        # packages having SRPM in parent variant are excluded from fulltree (via %fulltree-excludes)
        fulltree = True
        selfhosting = False

    lookaside_repos = {}
    for i, repo_url in enumerate(pungi.phases.gather.get_lookaside_repos(compose, arch, variant)):
        lookaside_repos["lookaside-repo-%s" % i] = repo_url

    yum_arch = tree_arch_to_yum_arch(arch)
    tmp_dir = compose.paths.work.tmp_dir(arch, variant)
    cache_dir = compose.paths.work.pungi_cache_dir(arch, variant)
    # TODO: remove YUM code, fully migrate to DNF
    backends = {
        'yum': pungi_wrapper.get_pungi_cmd,
        'dnf': pungi_wrapper.get_pungi_cmd_dnf,
    }
    get_cmd = backends[compose.conf['gather_backend']]
    cmd = get_cmd(pungi_conf, destdir=tmp_dir, name=variant.uid,
                  selfhosting=selfhosting, fulltree=fulltree, arch=yum_arch,
                  full_archlist=True, greedy=greedy_method, cache_dir=cache_dir,
                  lookaside_repos=lookaside_repos, multilib_methods=multilib_methods,
                  profiler=profiler)
    # Use temp working directory directory as workaround for
    # https://bugzilla.redhat.com/show_bug.cgi?id=795137
    with temp_dir(prefix='pungi_') as tmp_dir:
        run(cmd, logfile=pungi_log, show_cmd=True, workdir=tmp_dir, env=os.environ)

    with open(pungi_log, "r") as f:
        packages, broken_deps, missing_comps_pkgs = pungi_wrapper.parse_log(f)

    if missing_comps_pkgs:
        log_msg = ("Packages mentioned in comps do not exist for %s.%s: %s"
                   % (variant.uid, arch, ", ".join(sorted(missing_comps_pkgs))))
        compose.log_warning(log_msg)
        if compose.conf['require_all_comps_packages']:
            raise RuntimeError(log_msg)

    compose.log_info("[DONE ] %s" % msg)
    return packages, broken_deps


def check_deps(compose, arch, variant, missing_deps):
    if not compose.conf["check_deps"]:
        return

    if missing_deps:
        for pkg in sorted(missing_deps):
            compose.log_error("Unresolved dependencies in package %s: %s" % (pkg, sorted(missing_deps[pkg])))
        raise RuntimeError("Unresolved dependencies detected")
