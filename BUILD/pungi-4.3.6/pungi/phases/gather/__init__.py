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


import glob
import json
import os
import shutil
import threading

from kobo.rpmlib import parse_nvra
from kobo.shortcuts import run
from productmd.rpms import Rpms
from six.moves import cPickle as pickle

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

import pungi.wrappers.kojiwrapper
from pungi.arch import get_compatible_arches, split_name_arch
from pungi.compose import get_ordered_variant_uids
from pungi.module_util import (
    Modulemd,
    collect_module_defaults,
    collect_module_obsoletes,
)
from pungi.phases.base import PhaseBase
from pungi.phases.createrepo import add_modular_metadata
from pungi.util import get_arch_data, get_arch_variant_data, get_variant_data, makedirs
from pungi.wrappers.scm import get_file_from_scm

from ...wrappers.createrepo import CreaterepoWrapper
from .link import link_files


def get_gather_source(name):
    import pungi.phases.gather.sources

    return pungi.phases.gather.sources.ALL_SOURCES[name.lower()]


def get_gather_method(name):
    import pungi.phases.gather.methods

    return pungi.phases.gather.methods.ALL_METHODS[name.lower()]


class GatherPhase(PhaseBase):
    """GATHER"""

    name = "gather"

    def __init__(self, compose, pkgset_phase):
        PhaseBase.__init__(self, compose)
        # pkgset_phase provides package_sets and path_prefix
        self.pkgset_phase = pkgset_phase
        # Prepare empty manifest
        self.manifest_file = self.compose.paths.compose.metadata("rpms.json")
        self.manifest = Rpms()
        self.manifest.compose.id = self.compose.compose_id
        self.manifest.compose.type = self.compose.compose_type
        self.manifest.compose.date = self.compose.compose_date
        self.manifest.compose.respin = self.compose.compose_respin

    def validate(self):
        errors = []

        if not Modulemd:
            # Modules are not supported, check if we need them
            for variant in self.compose.variants.values():
                if variant.modules:
                    errors.append("Modular compose requires libmodulemd package.")

        variant_as_lookaside = self.compose.conf.get("variant_as_lookaside", [])
        all_variants = self.compose.all_variants

        # check whether variants from configuration value
        # 'variant_as_lookaside' are correct
        for (requiring, required) in variant_as_lookaside:
            if requiring in all_variants and required not in all_variants:
                errors.append(
                    "variant_as_lookaside: variant %r doesn't exist but is "
                    "required by %r" % (required, requiring)
                )

        # check whether variants from configuration value
        # 'variant_as_lookaside' have same architectures
        for (requiring, required) in variant_as_lookaside:
            if (
                requiring in all_variants
                and required in all_variants
                and not set(all_variants[requiring].arches).issubset(
                    set(all_variants[required].arches)
                )
            ):
                errors.append(
                    "variant_as_lookaside: architectures of variant '%s' "
                    "aren't subset of architectures of variant '%s'"
                    % (requiring, required)
                )

        if errors:
            raise ValueError("\n".join(errors))

    def _write_manifest(self):
        self.compose.log_info("Writing RPM manifest: %s" % self.manifest_file)
        self.manifest.dump(self.manifest_file)

    def run(self):
        pkg_map = gather_wrapper(
            self.compose, self.pkgset_phase.package_sets, self.pkgset_phase.path_prefix
        )

        for variant_uid in get_ordered_variant_uids(self.compose):
            variant = self.compose.all_variants[variant_uid]
            if variant.is_empty:
                continue
            for arch in variant.arches:
                link_files(
                    self.compose,
                    arch,
                    variant,
                    pkg_map[arch][variant.uid],
                    self.pkgset_phase.package_sets,
                    manifest=self.manifest,
                )

        self._write_manifest()

    def stop(self):
        super(GatherPhase, self).stop()


def _mk_pkg_map(rpm=None, srpm=None, debuginfo=None, iterable_class=list):
    return {
        "rpm": rpm or iterable_class(),
        "srpm": srpm or iterable_class(),
        "debuginfo": debuginfo or iterable_class(),
    }


def get_parent_pkgs(arch, variant, result_dict):
    """Find packages for parent variant (if any).

    :param result_dict: already known packages; a mapping from arch to variant uid
                        to package type to a list of dicts with path to package
    """
    result = _mk_pkg_map(iterable_class=set)
    if variant.parent is None:
        return result
    for pkg_type, pkgs in result_dict.get(arch, {}).get(variant.parent.uid, {}).items():
        for pkg in pkgs:
            nvra = parse_nvra(pkg["path"])
            result[pkg_type].add((nvra["name"], nvra["arch"]))
    return result


def get_gather_methods(compose, variant):
    methods = compose.conf["gather_method"]
    global_method_name = methods
    if isinstance(methods, dict):
        try:
            methods = get_variant_data(compose.conf, "gather_method", variant)[-1]
            global_method_name = None
        except IndexError:
            raise RuntimeError(
                "Variant %s has no configured gather_method" % variant.uid
            )
    return global_method_name, methods


def load_old_gather_result(compose, arch, variant):
    """
    Helper method to load `gather_packages` result from old compose.
    """
    gather_result = compose.paths.work.gather_result(variant=variant, arch=arch)
    old_gather_result = compose.paths.old_compose_path(gather_result)
    if not old_gather_result:
        return None

    compose.log_info("Loading old GATHER phase results: %s", old_gather_result)
    try:
        with open(old_gather_result, "rb") as f:
            old_result = pickle.load(f)
            return old_result
    except Exception as e:
        compose.log_debug(
            "Failed to load old GATHER phase results %s : %s"
            % (old_gather_result, str(e))
        )
        return None


def reuse_old_gather_packages(compose, arch, variant, package_sets, methods):
    """
    Tries to reuse `gather_packages` result from older compose.

    :param Compose compose: Compose instance.
    :param str arch: Architecture to reuse old gather data for.
    :param str variant: Variant to reuse old gather data for.
    :param list package_sets: List of package sets to gather packages from.
    :param str methods: Gather method.
    :return: Old `gather_packages` result or None if old result cannot be used.
    """
    log_msg = "Cannot reuse old GATHER phase results - %s"
    if not compose.conf["gather_allow_reuse"]:
        compose.log_info(log_msg % "reuse of old gather results is disabled.")
        return

    old_result = load_old_gather_result(compose, arch, variant)
    if old_result is None:
        compose.log_info(log_msg % "no old gather results.")
        return

    old_config = compose.load_old_compose_config()
    if old_config is None:
        compose.log_info(log_msg % "no old compose config dump.")
        return

    # Do not reuse when required variant is not reused.
    if not hasattr(compose, "_gather_reused_variant_arch"):
        setattr(compose, "_gather_reused_variant_arch", [])
    variant_as_lookaside = compose.conf.get("variant_as_lookaside", [])
    for (requiring, required) in variant_as_lookaside:
        if (
            requiring == variant.uid
            and (required, arch) not in compose._gather_reused_variant_arch
        ):
            compose.log_info(
                log_msg % "variant %s as lookaside is not reused." % required
            )
            return

    # Do not reuse if there's external lookaside repo.
    with open(compose.paths.log.log_file("global", "config-dump"), "r") as f:
        config_dump = json.load(f)
    if config_dump.get("gather_lookaside_repos") or old_config.get(
        "gather_lookaside_repos"
    ):
        compose.log_info(log_msg % "there's external lookaside repo.")
        return

    # The dumps/loads is needed to convert all unicode strings to non-unicode ones.
    config = json.loads(json.dumps(compose.conf))
    for opt, value in old_config.items():
        if opt == "gather_lookaside_repos":
            continue

        # Skip checking for frequently changing configuration options which do *not*
        # influence Gather phase:
        #   - product_id - Changes with every compose.
        #   - pkgset_koji_builds - This influences the gather phase, but the
        #     change itself is not a reason to not reuse old gather phase. if
        #     new pkgset_koji_builds value leads to significant change in input
        #     package set, we will find that later in this function when comparing
        #     old and new package set.
        config_whitelist = ["product_id", "pkgset_koji_builds"]
        if opt in config_whitelist:
            continue

        if opt not in config or config[opt] != value:
            compose.log_info(
                log_msg % ("compose configuration option %s changed." % opt)
            )
            return

    result = {
        "rpm": [],
        "srpm": [],
        "debuginfo": [],
    }

    for pkgset in package_sets:
        global_pkgset = pkgset["global"]

        # Return in case the old file cache does not exist.
        if global_pkgset.old_file_cache is None:
            compose.log_info(log_msg % "old file cache does not exist.")
            return

        # Do quick check to find out the number of input RPMs is the same in both
        # old and new cache.
        if len(global_pkgset.old_file_cache) != len(global_pkgset.file_cache):
            compose.log_info(log_msg % "some RPMs have been added/removed.")
            return

        # Create temporary dict mapping RPM path to record in `old_result`. This
        # is needed later to make things faster.
        old_result_cache = {}
        for old_result_key, old_result_records in old_result.items():
            for old_result_record in old_result_records:
                old_result_cache[old_result_record["path"]] = [
                    old_result_key,
                    old_result_record,
                ]

        # The `old_file_cache` contains all the input RPMs from old pkgset. Some
        # of these RPMs will be in older versions/releases than the ones in the
        # new `file_cache`. This is OK, but we need to be able to pair them so we
        # know that particular RPM package from `old_file_cache` has been updated
        # by another package in the new `file_cache`.
        # Following code uses "`rpm_obj.arch`-`rpm_obj.sourcerpm`-`rpm_obj.name`"
        # as a key to map RPMs from `old_file_cache` to RPMs in `file_cache`.
        #
        # At first, we need to create helper dict with the mentioned key. The value
        # is tuple in (rpm_obj, old_result_key, old_result_record) format.
        key_to_old_rpm_obj = {}
        for rpm_path, rpm_obj in global_pkgset.old_file_cache.items():
            key = "%s-%s-%s" % (
                rpm_obj.arch,
                rpm_obj.sourcerpm or rpm_obj.name,
                rpm_obj.name,
            )

            # With the current approach, we cannot reuse old gather result in case
            # there are multiple RPMs with the same arch, sourcerpm and name.
            if key in key_to_old_rpm_obj:
                compose.log_info(
                    log_msg % ("two RPMs with the same key exist: %s." % key)
                )
                return

            old_result_key, old_result_record = old_result_cache.get(
                rpm_path, [None, None]
            )
            key_to_old_rpm_obj[key] = [rpm_obj, old_result_key, old_result_record]

        # The `key_to_old_rpm_obj` now contains all the RPMs in the old global
        # package set. We will now compare these old RPMs with the RPMs in the
        # current global package set.
        for rpm_path, rpm_obj in global_pkgset.file_cache.items():
            key = "%s-%s-%s" % (
                rpm_obj.arch,
                rpm_obj.sourcerpm or rpm_obj.name,
                rpm_obj.name,
            )

            # Check that this RPM existed even in the old package set.
            if key not in key_to_old_rpm_obj:
                compose.log_info(log_msg % "some RPMs have been added.")
                return

            # Check that requires or provides of this RPM is still the same.
            old_rpm_obj, old_result_key, old_result_record = key_to_old_rpm_obj[key]
            if (
                old_rpm_obj.requires != rpm_obj.requires
                or old_rpm_obj.provides != rpm_obj.provides
            ):
                compose.log_info(
                    log_msg % "requires or provides of some RPMs have changed."
                )
                return

            # Add this RPM into the current result in case it has been in the
            # old result.
            if old_result_key and old_result_record:
                # Update the path to RPM, because in the `old_result_record`,
                # we might have path to old build of this RPM, but the rpm_path
                # contains the updated one with the same requires/provides.
                old_result_record["path"] = rpm_path
                result[old_result_key].append(old_result_record)

            # Delete the key from key_to_old_rpm_obj so we can find out later if all
            # RPMs from the old package set have their counterpart in the current
            # package set.
            del key_to_old_rpm_obj[key]

        # Check that all the RPMs from old_file_cache has been mapped to some RPM
        # in the new file cache.
        for per_arch_dict in key_to_old_rpm_obj.values():
            if len(per_arch_dict) != 0:
                compose.log_info(log_msg % "some RPMs have been removed.")
                return

    compose._gather_reused_variant_arch.append((variant.uid, arch))

    # Copy old gather log for debugging
    try:
        if methods == "hybrid":
            log_dir = compose.paths.log.topdir(arch, create_dir=False)
            old_log_dir = compose.paths.old_compose_path(log_dir)
            for log_file in glob.glob(
                os.path.join(old_log_dir, "hybrid-depsolver-%s-iter-*" % variant)
            ):
                compose.log_info(
                    "Copying old gather log %s to %s" % (log_file, log_dir)
                )
                shutil.copy2(log_file, log_dir)
        else:
            log_dir = os.path.dirname(
                compose.paths.work.pungi_log(arch, variant, create_dir=False)
            )
            old_log_dir = compose.paths.old_compose_path(log_dir)
            compose.log_info("Copying old gather log %s to %s" % (old_log_dir, log_dir))
            shutil.copytree(old_log_dir, log_dir)
    except Exception as e:
        compose.log_warning("Copying old gather log failed: %s" % str(e))

    return result


def gather_packages(compose, arch, variant, package_sets, fulltree_excludes=None):
    # multilib white/black-list is per-arch, common for all variants
    multilib_whitelist = get_multilib_whitelist(compose, arch)
    multilib_blacklist = get_multilib_blacklist(compose, arch)
    global_method_name, methods = get_gather_methods(compose, variant)

    msg = "Gathering packages (arch: %s, variant: %s)" % (arch, variant)

    if variant.is_empty:
        compose.log_info("[SKIP ] %s" % msg)
        return _mk_pkg_map()

    compose.log_info("[BEGIN] %s" % msg)

    result = {
        "rpm": [],
        "srpm": [],
        "debuginfo": [],
    }

    prepopulate = get_prepopulate_packages(compose, arch, variant)
    fulltree_excludes = fulltree_excludes or set()

    reused_result = reuse_old_gather_packages(
        compose, arch, variant, package_sets, methods
    )
    if reused_result:
        result = reused_result
    elif methods == "hybrid":
        # This variant is using a hybrid solver. Gather all inputs and run the
        # method once.

        packages = []
        groups = []
        filter_packages = []

        # Here we do want to get list of comps groups and additional packages.
        packages, groups, filter_packages = get_variant_packages(
            compose, arch, variant, "comps", package_sets
        )

        result = get_gather_method("hybrid")(compose)(
            arch,
            variant,
            packages=packages,
            groups=groups,
            filter_packages=filter_packages,
            multilib_whitelist=multilib_whitelist,
            multilib_blacklist=multilib_blacklist,
            package_sets=package_sets,
            fulltree_excludes=fulltree_excludes,
            prepopulate=prepopulate,
        )

    else:

        for source_name in ("module", "comps", "json"):

            packages, groups, filter_packages = get_variant_packages(
                compose, arch, variant, source_name, package_sets
            )
            if not packages and not groups:
                # No inputs, nothing to do really.
                continue

            try:
                method_name = global_method_name or methods[source_name]
            except KeyError:
                raise RuntimeError(
                    "Variant %s has no configured gather_method for source %s"
                    % (variant.uid, source_name)
                )

            GatherMethod = get_gather_method(method_name)
            method = GatherMethod(compose)
            method.source_name = source_name
            compose.log_debug(
                "Gathering source %s, method %s (arch: %s, variant: %s)"
                % (source_name, method_name, arch, variant)
            )
            pkg_map = method(
                arch,
                variant,
                packages,
                groups,
                filter_packages,
                multilib_whitelist,
                multilib_blacklist,
                package_sets,
                fulltree_excludes=fulltree_excludes,
                prepopulate=prepopulate if source_name == "comps" else set(),
            )

            for t in ("rpm", "srpm", "debuginfo"):
                result[t].extend(pkg_map.get(t, []))

    gather_result = compose.paths.work.gather_result(variant=variant, arch=arch)
    with open(gather_result, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)

    compose.log_info("[DONE ] %s" % msg)
    return result


def write_packages(compose, arch, variant, pkg_map, path_prefix):
    """Write a list of packages to a file (one per package type).

    If any path begins with ``path_prefix``, this prefix will be stripped.
    """
    msg = "Writing package list (arch: %s, variant: %s)" % (arch, variant)
    compose.log_info("[BEGIN] %s" % msg)

    for pkg_type, pkgs in pkg_map.items():
        file_name = compose.paths.work.package_list(
            arch=arch, variant=variant, pkg_type=pkg_type
        )
        with open(file_name, "w") as pkg_list:
            for pkg in pkgs:
                # TODO: flags?
                pkg_path = pkg["path"]
                if pkg_path.startswith(path_prefix):
                    pkg_path = pkg_path[len(path_prefix) :]
                pkg_list.write("%s\n" % pkg_path)

    compose.log_info("[DONE ] %s" % msg)


def trim_packages(compose, arch, variant, pkg_map, parent_pkgs=None, remove_pkgs=None):
    """Remove parent variant's packages from pkg_map <-- it gets modified in
    this function

    There are three cases where changes may happen:

     * If a package is mentioned explicitly in ``remove_pkgs``, it will be
       removed from the addon. Sources and debuginfo are not removed from
       layered-products though.
     * If a packages is present in parent, it will be removed from addon
       unconditionally.
     * A package in addon that is not present in parent and has
       ``fulltree-exclude`` flag will be moved to parent (unless it's
       explicitly included into the addon).

    :param parent_pkgs: mapping from pkg_type to a list of tuples (name, arch)
                        of packages present in parent variant
    :param remove_pkgs: mapping from pkg_type to a list of package names to be
                        removed from the variant
    """
    # TODO: remove debuginfo and srpm leftovers

    if not variant.parent:
        return

    msg = "Trimming package list (arch: %s, variant: %s)" % (arch, variant)
    compose.log_info("[BEGIN] %s" % msg)

    remove_pkgs = remove_pkgs or {}
    parent_pkgs = parent_pkgs or {}

    addon_pkgs = _mk_pkg_map(iterable_class=set)
    move_to_parent_pkgs = _mk_pkg_map()
    removed_pkgs = _mk_pkg_map()
    for pkg_type, pkgs in pkg_map.items():

        new_pkgs = []
        for pkg in pkgs:
            pkg_path = pkg["path"]
            if not pkg_path:
                continue
            nvra = parse_nvra(pkg_path)
            key = (nvra["name"], nvra["arch"])

            if nvra["name"] in remove_pkgs.get(pkg_type, set()):
                # TODO: make an option to turn this off
                if variant.type == "layered-product" and pkg_type in (
                    "srpm",
                    "debuginfo",
                ):
                    new_pkgs.append(pkg)
                    # User may not have addons available, therefore we need to
                    # keep addon SRPMs in layered products in order not to violate GPL.
                    # The same applies on debuginfo availability.
                    continue
                compose.log_warning(
                    "Removed addon package (arch: %s, variant: %s): %s: %s"
                    % (arch, variant, pkg_type, pkg_path)
                )
                removed_pkgs[pkg_type].append(pkg)
            elif key not in parent_pkgs.get(pkg_type, set()):
                if "fulltree-exclude" in pkg["flags"] and "input" not in pkg["flags"]:
                    # If a package wasn't explicitly included ('input') in an
                    # addon, move it to parent variant (cannot move it to
                    # optional, because addons can't depend on optional). This
                    # is a workaround for not having $addon-optional.
                    move_to_parent_pkgs[pkg_type].append(pkg)
                else:
                    new_pkgs.append(pkg)
                    addon_pkgs[pkg_type].add(nvra["name"])
            else:
                removed_pkgs[pkg_type].append(pkg)

        pkg_map[pkg_type] = new_pkgs
        compose.log_info(
            "Removed packages (arch: %s, variant: %s): %s: %s"
            % (arch, variant, pkg_type, len(removed_pkgs[pkg_type]))
        )
        compose.log_info(
            "Moved to parent (arch: %s, variant: %s): %s: %s"
            % (arch, variant, pkg_type, len(move_to_parent_pkgs[pkg_type]))
        )

    compose.log_info("[DONE ] %s" % msg)
    return addon_pkgs, move_to_parent_pkgs, removed_pkgs


def _make_lookaside_repo(compose, variant, arch, pkg_map, package_sets=None):
    """
    Create variant lookaside repo for given variant and architecture with
    packages from the map. If the repo repo already exists, then nothing will
    happen. This could happen if multiple variants depend on this one.
    """
    repo = compose.paths.work.lookaside_repo(arch, variant, create_dir=False)
    if os.path.exists(repo):
        # We have already generated this, nothing to do.
        return repo

    makedirs(repo)
    msg = "Generating lookaside repo from %s.%s" % (variant.uid, arch)
    compose.log_info("[BEGIN] %s", msg)

    prefixes = {
        "repos": lambda: os.path.join(
            compose.paths.work.topdir(arch="global"), "download"
        )
        + "/",
        "koji": lambda: pungi.wrappers.kojiwrapper.KojiWrapper(
            compose
        ).koji_module.config.topdir.rstrip("/")
        + "/",
    }
    path_prefix = prefixes[compose.conf["pkgset_source"]]()
    package_list = set()
    for pkg_arch in pkg_map.keys():
        try:
            for pkg_type, packages in pkg_map[pkg_arch][variant.uid].items():
                # We want all packages for current arch, and SRPMs for any
                # arch. Ultimately there will only be one source repository, so
                # we need a union of all SRPMs.
                if pkg_type == "srpm" or pkg_arch == arch:
                    for pkg in packages:
                        pkg = pkg["path"]
                        if path_prefix and pkg.startswith(path_prefix):
                            pkg = pkg[len(path_prefix) :]
                        package_list.add(pkg)
        except KeyError:
            raise RuntimeError(
                "Variant '%s' does not have architecture " "'%s'!" % (variant, pkg_arch)
            )

    pkglist = compose.paths.work.lookaside_package_list(arch=arch, variant=variant)
    with open(pkglist, "w") as f:
        for pkg in sorted(package_list):
            f.write("%s\n" % pkg)

    cr = CreaterepoWrapper(compose.conf["createrepo_c"])
    update_metadata = None
    if package_sets:
        pkgset = package_sets[-1]
        update_metadata = compose.paths.work.pkgset_repo(pkgset.name, arch)
    cmd = cr.get_createrepo_cmd(
        path_prefix,
        update=True,
        database=True,
        skip_stat=True,
        pkglist=pkglist,
        outputdir=repo,
        baseurl="file://%s" % path_prefix,
        workers=compose.conf["createrepo_num_workers"],
        update_md_path=update_metadata,
    )
    run(
        cmd,
        logfile=compose.paths.log.log_file(arch, "lookaside_repo_%s" % (variant.uid)),
        show_cmd=True,
    )

    # Add modular metadata into the repo
    if variant.arch_mmds:
        mod_index = Modulemd.ModuleIndex()
        for mmd in variant.arch_mmds[arch].values():
            mod_index.add_module_stream(mmd)

        module_names = set(mod_index.get_module_names())
        defaults_dir = compose.paths.work.module_defaults_dir()
        overrides_dir = compose.conf.get("module_defaults_override_dir")
        collect_module_defaults(
            defaults_dir, module_names, mod_index, overrides_dir=overrides_dir
        )
        obsoletes_dir = compose.paths.work.module_obsoletes_dir()
        mod_index = collect_module_obsoletes(obsoletes_dir, module_names, mod_index)

        log_file = compose.paths.log.log_file(
            arch, "lookaside_repo_modules_%s" % (variant.uid)
        )
        add_modular_metadata(cr, repo, mod_index, log_file)

    compose.log_info("[DONE ] %s", msg)

    return repo


def _update_config(compose, variant_uid, arch, repo):
    """
    Add the variant lookaside repository into the configuration.
    """
    lookasides = compose.conf.setdefault("gather_lookaside_repos", [])
    lookasides.append(("^%s$" % variant_uid, {arch: repo}))


def _update_lookaside_config(compose, variant, arch, pkg_map, package_sets=None):
    """
    Make sure lookaside repo for all variants that the given one depends on
    exist, and that configuration is updated to use those repos.
    """
    for dest, lookaside_variant_uid in compose.conf.get("variant_as_lookaside", []):
        lookaside_variant = compose.all_variants[lookaside_variant_uid]
        if dest != variant.uid:
            continue
        if arch not in lookaside_variant.arches:
            compose.log_warning(
                "[SKIP] Skipping lookaside from %s for %s.%s due to arch mismatch",
                lookaside_variant.uid,
                variant.uid,
                arch,
            )
            continue
        repo = _make_lookaside_repo(
            compose, lookaside_variant, arch, pkg_map, package_sets
        )
        _update_config(compose, variant.uid, arch, repo)


def _gather_variants(
    result, compose, variant_type, package_sets, exclude_fulltree=False
):
    """Run gathering on all arches of all variants of given type.

    If ``exclude_fulltree`` is set, all source packages from parent variants
    will be added to fulltree excludes for the processed variants.
    """

    for variant_uid in get_ordered_variant_uids(compose):
        variant = compose.all_variants[variant_uid]
        if variant.type != variant_type:
            continue
        threads_list = []
        que = Queue()
        errors = Queue()
        for arch in variant.arches:
            fulltree_excludes = set()
            if exclude_fulltree:
                for pkg_name, pkg_arch in get_parent_pkgs(arch, variant, result)[
                    "srpm"
                ]:
                    fulltree_excludes.add(pkg_name)

            # Get lookaside repos for this variant from other variants. Based
            # on the ordering we already know that we have the packages from
            # there.
            _update_lookaside_config(compose, variant, arch, result, package_sets)

            def worker(que, errors, arch, *args, **kwargs):
                try:
                    que.put((arch, gather_packages(*args, **kwargs)))
                except Exception as exc:
                    compose.log_error(
                        "Error in gathering for %s.%s: %s", variant, arch, exc
                    )
                    compose.traceback("gather-%s-%s" % (variant, arch))
                    errors.put(exc)

            # Run gather_packages() in parallel with multi threads and store
            # its return value in a Queue() for later use.
            t = threading.Thread(
                target=worker,
                args=(que, errors, arch, compose, arch, variant, package_sets),
                kwargs={"fulltree_excludes": fulltree_excludes},
            )
            threads_list.append(t)
            t.start()

        for t in threads_list:
            t.join()

        while not errors.empty():
            exc = errors.get()
            raise exc

        while not que.empty():
            arch, pkg_map = que.get()
            result.setdefault(arch, {})[variant.uid] = pkg_map

        # Remove the module -> pkgset mapping to save memory
        variant.nsvc_to_pkgset = None


def _trim_variants(
    result, compose, variant_type, remove_pkgs=None, move_to_parent=True
):
    """Trim all varians of given type.

    Returns a map of all packages included in these variants.
    """
    all_included_packages = {}
    for arch in compose.get_arches():
        for variant in compose.get_variants(arch=arch, types=[variant_type]):
            pkg_map = result[arch][variant.uid]
            parent_pkgs = get_parent_pkgs(arch, variant, result)
            included_packages, move_to_parent_pkgs, removed_pkgs = trim_packages(
                compose, arch, variant, pkg_map, parent_pkgs, remove_pkgs=remove_pkgs
            )

            # update all_addon_pkgs
            for pkg_type, pkgs in included_packages.items():
                all_included_packages.setdefault(pkg_type, set()).update(pkgs)

            if move_to_parent:
                # move packages to parent
                parent_pkg_map = result[arch][variant.parent.uid]
                for pkg_type, pkgs in move_to_parent_pkgs.items():
                    for pkg in pkgs:
                        compose.log_debug(
                            "Moving package to parent "
                            "(arch: %s, variant: %s, pkg_type: %s): %s"
                            % (
                                arch,
                                variant.uid,
                                pkg_type,
                                os.path.basename(pkg["path"]),
                            )
                        )
                        if pkg not in parent_pkg_map[pkg_type]:
                            parent_pkg_map[pkg_type].append(pkg)
    return all_included_packages


def gather_wrapper(compose, package_sets, path_prefix):
    result = {}

    _gather_variants(result, compose, "variant", package_sets)
    _gather_variants(result, compose, "addon", package_sets, exclude_fulltree=True)
    _gather_variants(
        result, compose, "layered-product", package_sets, exclude_fulltree=True
    )
    _gather_variants(result, compose, "optional", package_sets)

    all_addon_pkgs = _trim_variants(result, compose, "addon")
    # TODO do we really want to move packages to parent here?
    all_lp_pkgs = _trim_variants(
        result, compose, "layered-product", remove_pkgs=all_addon_pkgs
    )

    # merge all_addon_pkgs with all_lp_pkgs
    for pkg_type in set(all_addon_pkgs.keys()) | set(all_lp_pkgs.keys()):
        all_addon_pkgs.setdefault(pkg_type, set()).update(
            all_lp_pkgs.get(pkg_type, set())
        )

    _trim_variants(
        result, compose, "optional", remove_pkgs=all_addon_pkgs, move_to_parent=False
    )

    # write packages (package lists) for all variants
    for arch in compose.get_arches():
        for variant in compose.get_variants(arch=arch):
            pkg_map = result[arch][variant.uid]
            write_packages(compose, arch, variant, pkg_map, path_prefix=path_prefix)

    return result


def write_prepopulate_file(compose):
    """Download prepopulate file according to configuration.

    It is stored in a location where ``get_prepopulate_packages`` function
    expects.
    """
    if "gather_prepopulate" not in compose.conf:
        return

    prepopulate_file = os.path.join(
        compose.paths.work.topdir(arch="global"), "prepopulate.json"
    )
    msg = "Writing prepopulate file: %s" % prepopulate_file

    scm_dict = compose.conf["gather_prepopulate"]
    if isinstance(scm_dict, dict):
        file_name = os.path.basename(scm_dict["file"])
        if scm_dict["scm"] == "file":
            scm_dict["file"] = os.path.join(
                compose.config_dir, os.path.basename(scm_dict["file"])
            )
    else:
        file_name = os.path.basename(scm_dict)
        scm_dict = os.path.join(compose.config_dir, os.path.basename(scm_dict))

    compose.log_debug(msg)
    tmp_dir = compose.mkdtemp(prefix="prepopulate_file_")
    get_file_from_scm(scm_dict, tmp_dir, compose=compose)
    shutil.copy2(os.path.join(tmp_dir, file_name), prepopulate_file)
    shutil.rmtree(tmp_dir)


def get_prepopulate_packages(compose, arch, variant, include_arch=True):
    """Read prepopulate file and return list of packages for given tree.

    If ``variant`` is ``None``, all variants in the file are considered. The
    result of this function is a set of strings of format
    ``package_name.arch``. If ``include_arch`` is False, the ".arch" suffix
    is not included in packages in returned list.
    """
    result = set()

    prepopulate_file = os.path.join(
        compose.paths.work.topdir(arch="global"), "prepopulate.json"
    )
    if not os.path.isfile(prepopulate_file):
        return result

    with open(prepopulate_file, "r") as f:
        prepopulate_data = json.load(f)

    variants = [variant.uid] if variant else prepopulate_data.keys()

    for var in variants:
        for build, packages in prepopulate_data.get(var, {}).get(arch, {}).items():
            for i in packages:
                pkg_name, pkg_arch = split_name_arch(i)
                if pkg_arch not in get_compatible_arches(arch, multilib=True):
                    raise ValueError(
                        "Incompatible package arch '%s' for tree arch '%s' "
                        "in prepopulate package '%s'" % (pkg_arch, arch, pkg_name)
                    )
                if include_arch:
                    result.add(i)
                else:
                    result.add(pkg_name)
    return result


def get_additional_packages(compose, arch, variant):
    result = set()
    for i in get_arch_variant_data(compose.conf, "additional_packages", arch, variant):
        pkg_name, pkg_arch = split_name_arch(i)
        if pkg_arch is not None and pkg_arch not in get_compatible_arches(
            arch, multilib=True
        ):
            raise ValueError(
                "Incompatible package arch '%s' for tree arch '%s' in "
                "additional package '%s'" % (pkg_arch, arch, pkg_name)
            )
        result.add((pkg_name, pkg_arch))
    return result


def get_filter_packages(compose, arch, variant):
    result = set()
    for i in get_arch_variant_data(compose.conf, "filter_packages", arch, variant):
        result.add(split_name_arch(i))
    return result


def get_multilib_whitelist(compose, arch):
    return set(get_arch_data(compose.conf, "multilib_whitelist", arch))


def get_multilib_blacklist(compose, arch):
    return set(get_arch_data(compose.conf, "multilib_blacklist", arch))


def get_lookaside_repos(compose, arch, variant):
    return get_arch_variant_data(compose.conf, "gather_lookaside_repos", arch, variant)


def get_variant_packages(compose, arch, variant, source_name, package_sets=None):
    """Find inputs for depsolving of variant.arch combination.

    Returns a triple: a list of input packages, a list of input comps groups
    and a list of packages to be filtered out of the variant.

    For addons and layered products the inputs of parent variant are added as
    well. For optional it's parent and all its addons and layered products.

    The filtered packages are never inherited from parent.

    When system-release packages should be filtered, the ``package_sets``
    argument is required.
    """
    filter_packages = set()
    GatherSource = get_gather_source(source_name)
    source = GatherSource(compose)
    packages, groups = source(arch, variant)

    if source_name != "comps":
        # For modules and json source we want just the explicit packages.
        # Additional packages and possibly system-release will be added to
        # comps source.
        return packages, groups, filter_packages

    if variant is None:
        # no variant -> no parent -> we have everything we need
        # doesn't make sense to do any package filtering
        return packages, groups, filter_packages

    packages |= get_additional_packages(compose, arch, variant)
    filter_packages |= get_filter_packages(compose, arch, variant)

    if compose.conf["filter_system_release_packages"]:
        (
            system_release_packages,
            system_release_filter_packages,
        ) = get_system_release_packages(compose, arch, variant, package_sets)
        packages |= system_release_packages
        filter_packages |= system_release_filter_packages

    if variant.type == "optional":
        for var in variant.parent.get_variants(
            arch=arch, types=["self", "variant", "addon", "layered-product"]
        ):
            var_packages, var_groups, _ = get_variant_packages(
                compose, arch, var, source_name, package_sets=package_sets
            )
            packages |= var_packages
            groups |= var_groups

    if variant.type in ["addon", "layered-product"]:
        var_packages, var_groups, _ = get_variant_packages(
            compose, arch, variant.parent, source_name, package_sets=package_sets
        )
        packages |= var_packages
        groups |= var_groups

    return packages, groups, filter_packages


def get_system_release_packages(compose, arch, variant, package_sets):
    packages = set()
    filter_packages = set()

    system_release_packages = set()

    for pkgset in package_sets or []:
        for pkg in pkgset.iter_packages(arch):
            if pkg.is_system_release:
                system_release_packages.add(pkg)

    if not system_release_packages:
        return packages, filter_packages
    elif len(system_release_packages) == 1:
        # always include system-release package if available
        pkg = list(system_release_packages)[0]
        packages.add((pkg.name, None))
    else:
        if variant.type == "variant":
            # search for best match
            best_match = None
            for pkg in system_release_packages:
                if pkg.name.endswith(
                    "release-%s" % variant.uid.lower()
                ) or pkg.name.startswith("%s-release" % variant.uid.lower()):
                    best_match = pkg
                    break
        else:
            # addons: return release packages from parent variant
            return get_system_release_packages(
                compose, arch, variant.parent, package_sets
            )

        if not best_match:
            # no package matches variant name -> pick the first one
            best_match = sorted(system_release_packages)[0]

        packages.add((best_match.name, None))
        for pkg in system_release_packages:
            if pkg.name == best_match.name:
                continue
            filter_packages.add((pkg.name, None))

    return packages, filter_packages


def get_packages_to_gather(
    compose, arch=None, variant=None, include_arch=True, include_prepopulated=False
):
    """
    Returns the list of names of packages and list of names of groups which
    would be included in a compose as GATHER phase result.

    :param str arch: Arch to return packages for. If not set, returns packages
        for all arches.
    :param Variant variant: Variant to return packages for, If not set, returns
        packages for all variants of a compose.
    :param include_arch: When True, the arch of package will be included in
        returned list as ["pkg_name.arch", ...]. Otherwise only
        ["pkg_name", ...] is returned.
    :param include_prepopulated: When True, the prepopulated packages will
        be included in a list of packages.
    """
    packages = set([])
    groups = set([])
    for source_name in ("module", "comps", "json"):
        GatherSource = get_gather_source(source_name)
        src = GatherSource(compose)

        arches = [arch] if arch else compose.get_arches()

        for arch in arches:
            pkgs, grps = src(arch, variant)
            groups = groups.union(set(grps))

            additional_packages = get_additional_packages(compose, arch, None)
            for pkg_name, pkg_arch in pkgs | additional_packages:
                if not include_arch or pkg_arch is None:
                    packages.add(pkg_name)
                else:
                    packages.add("%s.%s" % (pkg_name, pkg_arch))

            if include_prepopulated:
                prepopulated = get_prepopulate_packages(
                    compose, arch, variant, include_arch
                )
                packages = packages.union(prepopulated)

    return list(packages), list(groups)
