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
from collections import defaultdict
from fnmatch import fnmatch

import createrepo_c as cr
import kobo.rpmlib
from kobo.shortcuts import run

import pungi.phases.gather.method
from pungi import multilib_dnf
from pungi.arch import get_valid_arches, tree_arch_to_yum_arch
from pungi.phases.gather import _mk_pkg_map
from pungi.util import (
    get_arch_variant_data,
    pkg_is_debug,
)
from pungi.wrappers import fus
from pungi.wrappers.comps import CompsWrapper

from .method_nodeps import expand_groups


class FakePackage(object):
    """This imitates a DNF package object and can be passed to python-multilib
    library.
    """

    def __init__(self, pkg):
        self.pkg = pkg

    def __getattr__(self, attr):
        return getattr(self.pkg, attr)

    @property
    def files(self):
        return [
            os.path.join(dirname, basename) for (_, dirname, basename) in self.pkg.files
        ]

    @property
    def provides(self):
        # This is supposed to match what yum package object returns. It's a
        # nested tuple (name, flag, (epoch, version, release)). This code only
        # fills in the name, because that's all that python-multilib is using..
        return [(p[0].split()[0], None, (None, None, None)) for p in self.pkg.provides]


class GatherMethodHybrid(pungi.phases.gather.method.GatherMethodBase):
    enabled = True

    def __init__(self, *args, **kwargs):
        super(GatherMethodHybrid, self).__init__(*args, **kwargs)
        self.package_maps = {}
        self.packages = {}
        # Mapping from package name to set of langpack packages (stored as
        # names).
        self.langpacks = {}
        # Set of packages for which we already added langpacks.
        self.added_langpacks = set()
        # Set of NEVRAs of modular packages
        self.modular_packages = set()
        # Arch -> pkg name -> set of pkg object
        self.debuginfo = defaultdict(lambda: defaultdict(set))

        # caches for processed packages
        self.processed_multilib = set()
        self.processed_debuginfo = set()

    def _get_pkg_map(self, arch):
        """Create a mapping from NEVRA to actual package object. This will be
        done once for each architecture, since the package set is the same for
        all variants.

        The keys are in NEVRA format and only include the epoch if it's not
        zero. This makes it easier to query by results for the depsolver.
        """
        if arch not in self.package_maps:
            pkg_map = {}
            for pkg_arch in self.package_sets[arch].rpms_by_arch:
                for pkg in self.package_sets[arch].rpms_by_arch[pkg_arch]:
                    pkg_map[_fmt_nevra(pkg, pkg_arch)] = pkg
            self.package_maps[arch] = pkg_map

        return self.package_maps[arch]

    def _prepare_packages(self):
        repo_path = self.compose.paths.work.arch_repo(arch=self.arch)
        md = cr.Metadata()
        md.locate_and_load_xml(repo_path)
        for key in md.keys():
            pkg = md.get(key)
            if pkg.arch in self.valid_arches:
                self.packages[_fmt_nevra(pkg, arch=pkg.arch)] = FakePackage(pkg)

    def _get_package(self, nevra):
        if not self.packages:
            self._prepare_packages()
        return self.packages[nevra]

    def _prepare_debuginfo(self):
        """Prepare cache of debuginfo packages for easy access. The cache is
        indexed by package architecture and then by package name. There can be
        more than one debuginfo package with the same name.
        """
        for pkg_arch in self.package_sets[self.arch].rpms_by_arch:
            for pkg in self.package_sets[self.arch].rpms_by_arch[pkg_arch]:
                self.debuginfo[pkg.arch][pkg.name].add(pkg)

    def _get_debuginfo(self, name, arch):
        if not self.debuginfo:
            self._prepare_debuginfo()
        return self.debuginfo.get(arch, {}).get(name, set())

    def expand_list(self, patterns):
        """Given a list of globs, create a list of package names matching any
        of the pattern.
        """
        expanded = set()
        for pkg_arch in self.package_sets[self.arch].rpms_by_arch:
            for pkg in self.package_sets[self.arch].rpms_by_arch[pkg_arch]:
                for pattern in patterns:
                    if fnmatch(pkg.name, pattern):
                        expanded.add(pkg)
                        break
        return expanded

    def prepare_modular_packages(self):
        for var in self.compose.all_variants.values():
            for mmd in var.arch_mmds.get(self.arch, {}).values():
                self.modular_packages.update(mmd.get_rpm_artifacts().dup())

    def prepare_langpacks(self, arch, variant):
        if not self.compose.has_comps:
            return
        comps_file = self.compose.paths.work.comps(arch, variant, create_dir=False)
        comps = CompsWrapper(comps_file)

        for name, install in comps.get_langpacks().items():
            # Replace %s with * for fnmatch.
            install_match = install % "*"
            self.langpacks[name] = set()
            for pkg_arch in self.package_sets[arch].rpms_by_arch:
                for pkg in self.package_sets[arch].rpms_by_arch[pkg_arch]:
                    if not fnmatch(pkg.name, install_match):
                        # Does not match the pattern, ignore...
                        continue
                    if pkg.name.endswith("-devel") or pkg.name.endswith("-static"):
                        continue
                    if pkg_is_debug(pkg):
                        continue
                    self.langpacks[name].add(pkg.name)

    def __call__(
        self,
        arch,
        variant,
        package_sets,
        packages=[],
        groups=[],
        multilib_whitelist=[],
        multilib_blacklist=[],
        filter_packages=[],
        prepopulate=[],
        **kwargs
    ):
        self.arch = arch
        self.valid_arches = get_valid_arches(arch, multilib=True)
        self.package_sets = package_sets

        self.prepare_langpacks(arch, variant)
        self.prepare_modular_packages()

        self.multilib_methods = get_arch_variant_data(
            self.compose.conf, "multilib", arch, variant
        )
        self.multilib = multilib_dnf.Multilib(
            self.multilib_methods,
            set(p.name for p in self.expand_list(multilib_blacklist)),
            set(p.name for p in self.expand_list(multilib_whitelist)),
        )

        platform = get_platform(self.compose, variant, arch)

        packages.update(
            expand_groups(self.compose, arch, variant, groups, set_pkg_arch=False)
        )

        packages.update(tuple(pkg.rsplit(".", 1)) for pkg in prepopulate)

        # Filters are received as tuples (name, arch), we should convert it to
        # strings.
        filters = [_fmt_pkg(*p) for p in filter_packages]

        nvrs, out_modules = self.run_solver(variant, arch, packages, platform, filters)
        filter_modules(variant, arch, out_modules)
        return expand_packages(
            self._get_pkg_map(arch),
            variant.arch_mmds.get(arch, {}),
            pungi.phases.gather.get_lookaside_repos(self.compose, arch, variant),
            nvrs,
            filter_packages=filter_packages,
        )
        # maybe check invalid sigkeys

    def run_solver(self, variant, arch, packages, platform, filter_packages):
        repos = [self.compose.paths.work.arch_repo(arch=arch)]
        results = set()
        result_modules = set()

        modules = []
        for mmd in variant.arch_mmds.get(arch, {}).values():
            modules.append("%s:%s" % (mmd.peek_name(), mmd.peek_stream()))

        input_packages = []
        for pkg_name, pkg_arch in packages:
            input_packages.extend(self._expand_wildcard(pkg_name, pkg_arch))

        step = 0

        while True:
            step += 1
            conf_file = self.compose.paths.work.fus_conf(arch, variant, step)
            fus.write_config(conf_file, sorted(modules), sorted(input_packages))
            cmd = fus.get_cmd(
                conf_file,
                tree_arch_to_yum_arch(arch),
                repos,
                pungi.phases.gather.get_lookaside_repos(self.compose, arch, variant),
                platform=platform,
                filter_packages=filter_packages,
            )
            logfile = self.compose.paths.log.log_file(
                arch, "hybrid-depsolver-%s-iter-%d" % (variant, step)
            )
            # Adding this environement variable will tell GLib not to prefix
            # any log messages with the PID of the fus process (which is quite
            # useless for us anyway).
            env = os.environ.copy()
            env["G_MESSAGES_PREFIXED"] = ""
            self.compose.log_debug("[BEGIN] Running fus")
            run(cmd, logfile=logfile, show_cmd=True, env=env)
            output, out_modules = fus.parse_output(logfile)
            self.compose.log_debug("[DONE ] Running fus")
            # No need to resolve modules again. They are not going to change.
            modules = []
            # Reset input packages as well to only solve newly added things.
            input_packages = []
            # Preserve the results from this iteration.
            results.update(output)
            result_modules.update(out_modules)

            new_multilib = self.add_multilib(variant, arch, output)
            input_packages.extend(
                _fmt_pkg(pkg_name, pkg_arch)
                for pkg_name, pkg_arch in sorted(new_multilib)
            )

            new_debuginfo = self.add_debuginfo(arch, output)
            input_packages.extend(
                _fmt_pkg(pkg_name, pkg_arch)
                for pkg_name, pkg_arch in sorted(new_debuginfo)
            )

            new_langpacks = self.add_langpacks(output)
            input_packages.extend(new_langpacks)

            if not input_packages:
                # Nothing new was added, we can stop now.
                break

        return results, result_modules

    def add_multilib(self, variant, arch, nvrs):
        added = set()
        if not self.multilib_methods:
            return []

        for nvr, pkg_arch, flags in nvrs:
            if (nvr, pkg_arch) in self.processed_multilib:
                continue
            self.processed_multilib.add((nvr, pkg_arch))

            if "modular" in flags:
                continue

            if pkg_arch != arch:
                # Not a native package, not checking to add multilib
                continue

            nevr = kobo.rpmlib.parse_nvr(nvr)

            for add_arch in self.valid_arches:
                if add_arch == arch:
                    continue
                try:
                    multilib_candidate = self._get_package("%s.%s" % (nvr, add_arch))
                except KeyError:
                    continue
                if self.multilib.is_multilib(multilib_candidate):
                    added.add((nevr["name"], add_arch))

        return added

    def add_debuginfo(self, arch, nvrs):
        added = set()

        for nvr, pkg_arch, flags in nvrs:
            if (nvr, pkg_arch) in self.processed_debuginfo:
                continue
            self.processed_debuginfo.add((nvr, pkg_arch))

            if "modular" in flags:
                continue

            pkg = self._get_package("%s.%s" % (nvr, pkg_arch))

            # There are two ways how the debuginfo package can be named. We
            # want to get them all.
            for pattern in ["%s-debuginfo", "%s-debugsource"]:
                debuginfo_name = pattern % pkg.name
                debuginfo = self._get_debuginfo(debuginfo_name, pkg_arch)
                for dbg in debuginfo:
                    # For each debuginfo package that matches on name and
                    # architecture, we also need to check if it comes from the
                    # same build.
                    if dbg.sourcerpm == pkg.rpm_sourcerpm:
                        added.add((dbg.name, dbg.arch))

        return added

    def add_langpacks(self, nvrs):
        if not self.langpacks:
            return set()

        added = set()
        for nvr, pkg_arch, flags in nvrs:
            if "modular" in flags:
                continue
            name = nvr.rsplit("-", 2)[0]
            if name in self.added_langpacks:
                # This package is already processed.
                continue
            added.update(self.langpacks.get(name, []))
            self.added_langpacks.add(name)

        return sorted(added)

    def _expand_wildcard(self, pkg_name, pkg_arch):
        if "*" not in pkg_name:
            return [_fmt_pkg(pkg_name, pkg_arch)]

        packages = []

        for pkg in self.expand_list([pkg_name]):
            if pkg_is_debug(pkg):
                # No debuginfo
                continue

            if pkg_arch:
                if pkg_arch != pkg.arch:
                    # Arch is specified and does not match, skip the package.
                    continue
            else:
                if pkg.arch not in ("noarch", self.arch):
                    # No arch specified and package does not match
                    continue

            strict_nevra = "%s-%s:%s-%s.%s" % (
                pkg.name, pkg.epoch or "0", pkg.version, pkg.release, pkg.arch
            )
            if strict_nevra in self.modular_packages:
                # Wildcards should not match modular packages.
                continue

            packages.append(_fmt_nevra(pkg, pkg.arch))

        return packages


def get_platform(compose, variant, arch):
    """Find platform stream for modules. Raises RuntimeError if there are
    conflicting requests.
    """
    platforms = set()

    for var in compose.all_variants.values():
        for mmd in var.arch_mmds.get(arch, {}).values():
            for dep in mmd.peek_dependencies():
                streams = dep.peek_requires().get("platform")
                if streams:
                    platforms.update(streams.dup())

    if len(platforms) > 1:
        raise RuntimeError("There are conflicting requests for platform.")

    return list(platforms)[0] if platforms else None


def _fmt_pkg(pkg_name, arch):
    if arch:
        pkg_name += ".%s" % arch
    return pkg_name


def _nevra(**kwargs):
    if kwargs.get("epoch") not in (None, "", 0, "0"):
        return "%(name)s-%(epoch)s:%(version)s-%(release)s.%(arch)s" % kwargs
    return "%(name)s-%(version)s-%(release)s.%(arch)s" % kwargs


def _fmt_nevra(pkg, arch):
    return _nevra(
        name=pkg.name,
        epoch=pkg.epoch,
        version=pkg.version,
        release=pkg.release,
        arch=arch,
    )


def _get_srpm_nevra(pkg):
    nevra = kobo.rpmlib.parse_nvra(pkg.sourcerpm)
    nevra["epoch"] = nevra["epoch"] or pkg.epoch
    return _nevra(**nevra)


def _make_result(paths):
    return [{"path": path, "flags": []} for path in sorted(paths)]


def expand_packages(nevra_to_pkg, variant_modules, lookasides, nvrs, filter_packages):
    """For each package add source RPM."""
    # This will serve as the final result. We collect sets of paths to the
    # packages.
    rpms = set()
    srpms = set()
    debuginfo = set()

    filters = set(filter_packages)

    # Collect list of all packages in lookaside. These will not be added to the
    # result. Fus handles this in part: if a package is explicitly mentioned as
    # input (which can happen with comps group expansion), it will be in the
    # output even if it's in lookaside.
    lookaside_packages = set()
    for repo in lookasides:
        md = cr.Metadata()
        md.locate_and_load_xml(repo)
        for key in md.keys():
            pkg = md.get(key)
            url = os.path.join(pkg.location_base or repo, pkg.location_href)
            # Strip file:// prefix
            lookaside_packages.add(url[7:])

    for nvr, pkg_arch, flags in nvrs:
        pkg = nevra_to_pkg["%s.%s" % (nvr, pkg_arch)]
        if pkg.file_path in lookaside_packages:
            # Package is in lookaside, don't add it and ignore sources and
            # debuginfo too.
            continue
        if pkg_is_debug(pkg):
            debuginfo.add(pkg.file_path)
        else:
            rpms.add(pkg.file_path)

        try:
            srpm_nevra = _get_srpm_nevra(pkg)
            srpm = nevra_to_pkg[srpm_nevra]
            if (srpm.name, "src") in filters:
                # Filtered package, skipping
                continue
            if srpm.file_path not in lookaside_packages:
                srpms.add(srpm.file_path)
        except KeyError:
            # Didn't find source RPM.. this should be logged
            pass

    return _mk_pkg_map(_make_result(rpms), _make_result(srpms), _make_result(debuginfo))


def filter_modules(variant, arch, nsvcs_to_keep):
    """Remove any arch-specific module metadata from the module if it's not
    listed in the list to keep. This will ultimately cause the module to not be
    included in the final repodata and module metadata.
    """
    for nsvc in list(variant.arch_mmds.get(arch, {}).keys()):
        if nsvc not in nsvcs_to_keep:
            del variant.arch_mmds[arch][nsvc]
