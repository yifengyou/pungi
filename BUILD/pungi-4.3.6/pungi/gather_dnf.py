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


from enum import Enum
from itertools import count
import logging
import os
import re

from kobo.rpmlib import parse_nvra

import pungi.common
import pungi.dnf_wrapper
import pungi.multilib_dnf
import pungi.util
from pungi.linker import Linker
from pungi.profiler import Profiler
from pungi.util import DEBUG_PATTERNS


def get_source_name(pkg):
    # Workaround for rhbz#1418298
    return pkg.sourcerpm.rsplit("-", 2)[0]


class GatherOptions(pungi.common.OptionsBase):
    def __init__(self, **kwargs):
        super(GatherOptions, self).__init__()

        # include all unused sub-packages of already included RPMs
        self.fulltree = False

        # A set of packages for which fulltree does not apply.
        self.fulltree_excludes = set()

        # include langpacks
        self.langpacks = []  # format: [{"package": "langpack-pattern-%s"}]

        # resolve dependencies
        self.resolve_deps = True

        # pull build dependencies
        self.selfhosting = False

        # none, all, build
        # TODO: validate values
        self.greedy_method = "none"

        # multilib options
        self.multilib_methods = []
        self.multilib_blacklist = []
        self.multilib_whitelist = []

        # prepopulate
        self.prepopulate = []

        # lookaside repos; packages will be flagged accordingly
        self.lookaside_repos = []

        # exclude source packages
        self.exclude_source = False

        # exclude debug packages
        self.exclude_debug = False

        self.merge_options(**kwargs)

    def __str__(self):
        lines = [
            "fulltree=%s" % self.fulltree,
            "fulltree_excludes=%d items" % len(self.fulltree_excludes),
            "resolve_deps=%s" % self.resolve_deps,
            "selfhosting=%s" % self.selfhosting,
            "greedy_method=%s" % self.greedy_method,
            "langpacks=%s" % self.langpacks,
            "multilib_methods=%s" % self.multilib_methods,
            "multilib_blacklist=%d items" % len(self.multilib_blacklist),
            "multilib_whitelist=%d items" % len(self.multilib_whitelist),
            "lookaside_repos=%s" % self.lookaside_repos,
            "prepopulate=%d items" % len(self.prepopulate),
            "exclude_source=%s" % self.exclude_source,
            "exclude_debug=%s" % self.exclude_debug,
        ]
        return "[\n%s\n]" % "\n".join("    " + line for line in lines)


class QueryCache(object):
    def __init__(self, queue, *args, **kwargs):
        self.cache = {}
        self.nargs = len(args)

        if kwargs:
            queue = queue.filter(**kwargs)

        for pkg in queue:
            key = tuple(getattr(pkg, arg) for arg in args)
            pkgs = self.cache.setdefault(key, [])
            if pkg not in pkgs:
                # use list preserve package order
                pkgs.append(pkg)

    def get(self, *args):
        if len(args) != self.nargs:
            raise ValueError("Expected %s arguments, got %s" % (self.nargs, len(args)))
        key = tuple(args)
        return self.cache.get(key, None)


class PkgFlag(Enum):
    lookaside = 1
    input = 2
    greedy_build = 4
    prepopulate = 8
    conditional = 16
    self_hosting = 32
    fulltree = 64
    multilib = 128
    langpack = 256
    fulltree_exclude = 512


class GatherBase(object):
    def __init__(self, dnf_obj):
        self.dnf = dnf_obj

        q = self._query
        # We can not filter only latest packages yet, because we need to apply
        # excludes only to main repos and not lookaside. Filtering latest here
        # makes that impossible as it could remove older versions from
        # lookaside.

        # source packages
        self.q_source_packages = q.filter(
            arch=self.dnf.arch_wrapper.source_arches
        ).apply()
        q = q.difference(self.q_source_packages)

        # filter arches
        q = q.filter(arch=self.dnf.arch_wrapper.all_arches).apply()
        q_noarch = q.filter(arch="noarch").apply()
        q_native = q.filter(arch=self.dnf.arch_wrapper.native_arches).apply()
        q_multilib = q.difference(q_native).union(q_noarch).apply()

        # debug packages
        self.q_debug_packages = q.filter(name__glob=DEBUG_PATTERNS).apply()
        self.q_native_debug_packages = self.q_debug_packages.intersection(q_native)
        self.q_multilib_debug_packages = self.q_debug_packages.intersection(q_multilib)

        # binary packages
        self.q_binary_packages = q.difference(self.q_debug_packages)
        self.q_native_binary_packages = q_native.difference(self.q_debug_packages)
        self.q_multilib_binary_packages = q_multilib.difference(self.q_debug_packages)
        self.q_noarch_binary_packages = q_noarch.difference(self.q_debug_packages)

    @property
    def _query(self):
        return self.dnf._sack.query()

    def is_noarch_package(self, pkg):
        return pkg.arch == "noarch"

    def is_native_package(self, pkg):
        if pkg.arch in self.dnf.arch_wrapper.source_arches:
            return False
        if pkg.arch == "noarch":
            return True
        if pkg.arch in self.dnf.arch_wrapper.native_arches:
            return True
        return False


class Gather(GatherBase):
    def __init__(self, dnf_obj, gather_options, logger=None):
        super(Gather, self).__init__(dnf_obj)
        self.logger = logger
        if not self.logger:
            # default logger
            self.logger = logging.getLogger("gather_dnf")
            self.logger.setLevel(logging.DEBUG)

            if not self.logger.handlers:
                # default logging handler
                handler = logging.StreamHandler()
                handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s [%(levelname)-8s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
                handler.setLevel(logging.DEBUG)
                self.logger.addHandler(handler)

        self.opts = gather_options
        self.logger.debug("Gather received gather_options=%s" % gather_options)
        self._multilib = pungi.multilib_dnf.Multilib.from_globs(
            self.dnf._sack,
            gather_options.multilib_methods,
            blacklist=self.opts.multilib_blacklist,
            whitelist=self.opts.multilib_whitelist,
        )

        # already processed packages
        self.finished_add_binary_package_deps = {}  # {pkg: [deps]}
        self.finished_add_debug_package_deps = {}  # {pkg: [deps]}
        self.finished_add_source_package_deps = {}  # {pkg: [deps]}

        self.finished_get_package_deps_reqs = {}

        self.finished_add_conditional_packages = {}  # {pkg: [pkgs]}
        self.finished_add_source_packages = {}  # {pkg: src-pkg|None}
        self.sourcerpm_cache = {}  # {src_nvra: src-pkg|None}
        self.finished_add_debug_packages = {}  # {pkg: [debug-pkgs]}
        self.finished_add_fulltree_packages = {}  # {pkg: [pkgs]}
        self.finished_add_langpack_packages = {}  # {pkg: [pkgs]}
        self.finished_add_multilib_packages = {}  # {pkg: pkg|None}

        # result
        self.result_binary_packages = set()
        self.result_debug_packages = set()
        self.result_source_packages = set()
        self.result_package_flags = {}

    def _set_flag(self, pkg, *flags):
        self.result_package_flags.setdefault(pkg, set()).update(flags)

    def _get_best_package(self, package_list, pkg=None, req=None, debuginfo=False):
        if not package_list:
            return []

        # The list can contain packages from lookaside and outside of
        # lookaside. If the package is in both, we want to prefer the version
        # from lookaside. This can be achieved by removing any package that is
        # also in lookaside from the list.
        lookaside_pkgs = set()
        for pkg in package_list:
            if pkg.repoid in self.opts.lookaside_repos:
                lookaside_pkgs.add("{0.name}-{0.evr}".format(pkg))

        if self.opts.greedy_method == "all":
            return list(package_list)

        all_pkgs = []
        for pkg in package_list:
            # Remove packages that are also in lookaside
            if (
                "{0.name}-{0.evr}".format(pkg) not in lookaside_pkgs
                or pkg.repoid in self.opts.lookaside_repos
            ):
                all_pkgs.append(pkg)

        if not debuginfo:
            native_pkgs = set(
                self.q_native_binary_packages.filter(pkg=all_pkgs).apply()
            )
            multilib_pkgs = set(
                self.q_multilib_binary_packages.filter(pkg=all_pkgs).apply()
            )
        else:
            native_pkgs = set(self.q_native_debug_packages.filter(pkg=all_pkgs).apply())
            multilib_pkgs = set(
                self.q_multilib_debug_packages.filter(pkg=all_pkgs).apply()
            )

        result = set()

        # try seen native packages first
        seen_pkgs = native_pkgs & self.result_binary_packages
        if seen_pkgs:
            result = seen_pkgs

        # then try seen multilib packages
        if not result:
            seen_pkgs = multilib_pkgs & self.result_binary_packages
            if seen_pkgs:
                result = seen_pkgs

        if not result:
            result = native_pkgs

        if not result:
            result = multilib_pkgs

        if not result:
            return []

        # return package with shortest name, alphabetically ordered
        result = list(result)
        result.sort(key=lambda x: x.name)
        result.sort(key=lambda x: len(x.name))

        # best arch
        arches = self.dnf.arch_wrapper.all_arches
        result.sort(key=lambda x: arches.index(x.arch))
        match = result[0]

        if self.opts.greedy_method == "build" and req:
            if self.is_native_package(match):
                return [i for i in native_pkgs if i.sourcerpm == match.sourcerpm]
            else:
                return [i for i in multilib_pkgs if i.sourcerpm == match.sourcerpm]
        return [match]

    def is_from_lookaside(self, pkg):
        if not self.opts.lookaside_repos:
            return False
        pkgs = self.dnf.sack.query().filter(
            name=pkg.name,
            version=pkg.version,
            release=pkg.release,
            arch=pkg.arch,
            reponame=self.opts.lookaside_repos,
        )
        return pkg in pkgs

    def _add_packages(self, packages, pulled_by=None, req=None, reason=None, dest=None):
        dest = dest if dest is not None else self.result_binary_packages
        for i in packages:
            assert i is not None
            if i not in dest:
                pb = ""
                if pulled_by:
                    pb = " (pulled by %s, repo: %s)" % (pulled_by, pulled_by.repo.id)
                if req:
                    pb += " (Requires: %s)" % req
                if reason:
                    pb += " (%s)" % reason
                self.logger.debug("Added package %s%s" % (i, pb))
                dest.add(i)
                # lookaside
                if self.is_from_lookaside(i):
                    self._set_flag(i, PkgFlag.lookaside)
                if i.sourcerpm.rsplit("-", 2)[0] in self.opts.fulltree_excludes:
                    self._set_flag(i, PkgFlag.fulltree_exclude)

    def _get_package_deps(self, pkg, debuginfo=False):
        """Return all direct (1st level) deps for a package.

        The return value is a set of tuples (pkg, reldep). Each package is
        tagged with the particular reldep that pulled it in. Requires_pre and
        _post are not distinguished.
        """
        queue = self.q_debug_packages if debuginfo else self.q_binary_packages
        assert pkg is not None
        result = set()

        if pkg.repoid in self.opts.lookaside_repos:
            # Don't resolve deps for stuff in lookaside.
            return result

        # DNF package has the _pre and _post attributes only if they are not
        # empty.
        requires = (
            pkg.requires
            + getattr(pkg, "requires_pre", [])
            + getattr(pkg, "requires_post", [])
        )

        q = queue.filter(provides=requires).apply()
        for req in requires:
            deps = self.finished_get_package_deps_reqs.setdefault(str(req), set())
            if deps:
                result.update((dep, req) for dep in deps)
                continue

            # TODO: need query also debuginfo
            deps = q.filter(provides=req)
            if deps:
                deps = self._get_best_package(deps, req=req, debuginfo=debuginfo)
                self.finished_get_package_deps_reqs[str(req)].update(deps)
                result.update((dep, req) for dep in deps)
            else:
                self.logger.warning(
                    "Unresolvable dependency %s in %s.%s", req, pkg.name, pkg.arch
                )

        return result

    def _filter_queue(self, queue, exclude):
        """Given an name of a queue (stored as attribute in `self`), exclude
        all given packages and keep only the latest per package name and arch.
        """
        setattr(
            self, queue, getattr(self, queue).filter(pkg__neq=exclude).latest().apply()
        )

    @Profiler("Gather._apply_excludes()")
    def _apply_excludes(self, excludes):
        """Exclude packages from all queues. An excluded package will no longer
        be visible in the depsolving process (as if it was not in the repo in
        the first place).

        All packages matching patterns in `excludes` argument are removed, plus
        anything matched by multilib blacklist. Finally only latest versions of
        each package (per arch) is preserved in the queue.
        """
        exclude = set()
        for pattern in excludes:
            with Profiler("Gather._apply_excludes():exclude"):
                if pattern.endswith(".+"):
                    pkgs = self.q_multilib_binary_packages.filter(
                        name__glob=pattern[:-2],
                        arch__neq="noarch",
                        reponame__neq=self.opts.lookaside_repos,
                    )
                elif pattern.endswith(".src"):
                    pkgs = self.q_source_packages.filter(
                        name__glob=pattern[:-4], reponame__neq=self.opts.lookaside_repos
                    )
                elif pungi.util.pkg_is_debug(pattern):
                    pkgs = self.q_debug_packages.filter(
                        name__glob=pattern, reponame__neq=self.opts.lookaside_repos
                    )
                else:
                    pkgs = self.q_binary_packages.filter(
                        name__glob=pattern, reponame__neq=self.opts.lookaside_repos
                    )

                exclude.update(pkgs)
                self.logger.debug("EXCLUDED by %s: %s", pattern, [str(p) for p in pkgs])
                self.dnf._sack.add_excludes(pkgs)

        for pattern in self.opts.multilib_blacklist:
            with Profiler("Gather._apply_excludes():exclude-multilib-blacklist"):
                # TODO: does whitelist affect this in any way?
                pkgs = self.q_multilib_binary_packages.filter(
                    name__glob=pattern, arch__neq="noarch"
                )
                exclude.update(pkgs)
                self.logger.debug("EXCLUDED by %s: %s", pattern, [str(p) for p in pkgs])
                self.dnf._sack.add_excludes(pkgs)

        all_queues = [
            "q_binary_packages",
            "q_native_binary_packages",
            "q_multilib_binary_packages",
            "q_noarch_binary_packages",
            "q_source_packages",
            "q_native_debug_packages",
            "q_multilib_debug_packages",
        ]

        with Profiler("Gather._apply_excludes():exclude-queries"):
            for queue in all_queues:
                self._filter_queue(queue, exclude)

    @Profiler("Gather.add_initial_packages()")
    def add_initial_packages(self, pattern_list):
        added = set()
        added_debuginfo = set()

        excludes = []
        includes = []
        for pattern in pattern_list:
            if pattern.startswith("-"):
                excludes.append(pattern[1:])
            else:
                includes.append(pattern)

        self._apply_excludes(excludes)
        self.init_query_cache()

        for pattern in includes:
            with Profiler("Gather.add_initial_packages():include"):
                debuginfo = False
                if pattern == "system-release" and self.opts.greedy_method == "all":
                    pkgs = self.q_binary_packages.filter(
                        provides="system-release"
                    ).apply()
                else:
                    for p in DEBUG_PATTERNS:
                        p = p.replace("*", ".+")
                        if re.match(p, pattern):
                            debuginfo = True
                            break
                    if debuginfo:
                        if pattern.endswith(".+"):
                            pkgs = self.q_multilib_debug_packages.filter(
                                name__glob=pattern[:-2]
                            ).apply()
                        else:
                            pkgs = self.q_debug_packages.filter(
                                name__glob=pattern
                            ).apply()
                    else:
                        if pattern.endswith(".+"):
                            pkgs = self.q_multilib_binary_packages.filter(
                                name__glob=pattern[:-2]
                            ).apply()
                        else:
                            pkgs = self.q_binary_packages.filter(
                                name__glob=pattern
                            ).apply()

                if not pkgs:
                    self.logger.error("No package matches pattern %s" % pattern)

                # The pattern could have been a glob. In that case we want to
                # group the packages by name and get best match in those
                # smaller groups.
                packages_by_name = {}
                for po in pkgs:
                    packages_by_name.setdefault(po.name, []).append(po)

                for name, packages in packages_by_name.items():
                    pkgs = self._get_best_package(packages, debuginfo=debuginfo)
                    if pkgs:
                        if debuginfo:
                            added_debuginfo.update(pkgs)
                        else:
                            added.update(pkgs)

        for pkg in added | added_debuginfo:
            self._set_flag(pkg, PkgFlag.input)

        return added, added_debuginfo

    @Profiler("Gather.init_query_cache()")
    def init_query_cache(self):
        # HACK: workaround for insufficient hawkey query performance
        # Must be executed *after* add_initial_packages() to exclude packages properly.

        # source
        self.source_pkgs_cache = QueryCache(
            self.q_source_packages, "name", "version", "release"
        )

        # debug
        self.native_debug_packages_cache = QueryCache(
            self.q_native_debug_packages, "sourcerpm"
        )
        self.multilib_debug_packages_cache = QueryCache(
            self.q_multilib_debug_packages, "sourcerpm"
        )

        # packages by sourcerpm
        self.q_native_pkgs_by_sourcerpm_cache = QueryCache(
            self.q_native_binary_packages, "sourcerpm", arch__neq="noarch"
        )
        self.q_multilib_pkgs_by_sourcerpm_cache = QueryCache(
            self.q_multilib_binary_packages, "sourcerpm", arch__neq="noarch"
        )
        self.q_noarch_pkgs_by_sourcerpm_cache = QueryCache(
            self.q_native_binary_packages, "sourcerpm", arch="noarch"
        )

        # multilib
        self.q_multilib_binary_packages_cache = QueryCache(
            self.q_multilib_binary_packages,
            "name",
            "version",
            "release",
            arch__neq="noarch",
        )

        # prepopulate
        self.prepopulate_cache = QueryCache(self.q_binary_packages, "name", "arch")

    @Profiler("Gather.add_prepopulate_packages()")
    def add_prepopulate_packages(self):
        added = set()

        for name_arch in self.opts.prepopulate:
            name, arch = name_arch.rsplit(".", 1)
            pkgs = self.prepopulate_cache.get(name, arch)
            pkgs = self._get_best_package(pkgs)
            if pkgs:
                added.update(pkgs)
            else:
                self.logger.warning("Prepopulate: Doesn't match: %s", name_arch)

        for pkg in added:
            self._set_flag(pkg, PkgFlag.prepopulate)

        return added

    @Profiler("Gather.add_binary_package_deps()")
    def add_binary_package_deps(self):
        added = set()

        if not self.opts.resolve_deps:
            return added

        for pkg in self.result_binary_packages.copy():
            assert pkg is not None

            if pkg not in self.finished_add_binary_package_deps:
                deps = self._get_package_deps(pkg)
                for i, req in deps:
                    if i not in self.result_binary_packages:
                        self._add_packages(
                            [i], pulled_by=pkg, req=req, reason="binary-dep"
                        )
                        added.add(i)
                self.finished_add_binary_package_deps[pkg] = deps

        return added

    @Profiler("Gather.add_debug_package_deps()")
    def add_debug_package_deps(self):
        added = set()

        if not self.opts.resolve_deps or self.opts.exclude_debug:
            return added

        for pkg in self.result_debug_packages.copy():

            if pkg not in self.finished_add_debug_package_deps:
                deps = self._get_package_deps(pkg, debuginfo=True)
                for i, req in deps:
                    if i in self.result_binary_packages:
                        # The dependency is already satisfied by binary package
                        continue
                    if i not in self.result_debug_packages:
                        self._add_packages(
                            [i],
                            pulled_by=pkg,
                            req=req,
                            reason="debug-dep",
                            dest=self.result_debug_packages,
                        )
                        added.add(i)
                self.finished_add_debug_package_deps[pkg] = deps

        return added

    @Profiler("Gather.add_conditional_packages()")
    def add_conditional_packages(self):
        """
        For each binary package add their conditional dependencies
        as specified in comps.
        Return newly added packages.
        """
        added = set()

        if not self.opts.resolve_deps:
            return added

        for pkg in self.result_binary_packages.copy():
            assert pkg is not None

            try:
                deps = self.finished_add_conditional_packages[pkg]
            except KeyError:
                deps = set()
                for cond in self.conditional_packages:
                    if cond["name"] != pkg.name:
                        continue
                    pkgs = self.q_binary_packages.filter(name=cond["install"]).apply()
                    pkgs = self._get_best_package(pkgs)  # TODO: multilib?
                    deps.update(pkgs)
                self.finished_add_conditional_packages[pkg] = deps

            for i in deps:
                if i not in self.result_binary_packages:
                    self._add_packages([i], pulled_by=pkg, reason="cond-dep")
                    self._set_flag(pkg, PkgFlag.conditional)
                    added.add(i)

        return added

    @Profiler("Gather.add_source_package_deps()")
    def add_source_package_deps(self):
        added = set()

        if not self.opts.resolve_deps:
            return added
        if not self.opts.selfhosting:
            return added
        if self.opts.exclude_source:
            return added

        for pkg in self.result_source_packages:
            assert pkg is not None

            try:
                deps = self.finished_add_source_package_deps[pkg]
            except KeyError:
                deps = self._get_package_deps(pkg)
                self.finished_add_source_package_deps[pkg] = set(
                    dep for (dep, req) in deps
                )
                for i, req in deps:
                    if i not in self.result_binary_packages:
                        self._add_packages(
                            [i], pulled_by=pkg, req=req, reason="source-dep"
                        )
                        added.add(i)
                        self._set_flag(pkg, PkgFlag.self_hosting)

        return added

    def _get_matching_srpm(self, pkg, sources):
        """
        Get a source rpm from the same repo that pkg comes from. If there is no
        such package, get the first one.
        """
        for srpm in sources:
            if pkg.repo == srpm.repo:
                return srpm
        return sources[0]

    @Profiler("Gather.add_source_packages()")
    def add_source_packages(self):
        """
        For each binary package add it's source package.
        Return newly added source packages.
        """
        added = set()

        if self.opts.exclude_source:
            return added

        for pkg in self.result_binary_packages:
            assert pkg is not None

            try:
                source_pkg = self.finished_add_source_packages[pkg]
            except KeyError:
                source_pkg = None
                if pkg.sourcerpm:
                    source_pkg = self.sourcerpm_cache.get(pkg.sourcerpm, None)
                    if source_pkg is None:
                        nvra = parse_nvra(pkg.sourcerpm)
                        source_pkgs = self.source_pkgs_cache.get(
                            nvra["name"], nvra["version"], nvra["release"]
                        )
                        if source_pkgs:
                            source_pkg = self._get_matching_srpm(pkg, source_pkgs)
                            self.sourcerpm_cache[pkg.sourcerpm] = source_pkg
                self.finished_add_source_packages[pkg] = source_pkg

            if not source_pkg:
                continue

            if (
                source_pkg.repoid in self.opts.lookaside_repos
                or pkg.repoid in self.opts.lookaside_repos
            ):
                self._set_flag(source_pkg, PkgFlag.lookaside)
            if source_pkg not in self.result_source_packages:
                added.add(source_pkg)
            self.result_source_packages.add(source_pkg)

        return added

    @Profiler("Gather.add_debug_packages()")
    def add_debug_packages(self):
        """
        For each binary package add debuginfo packages built from the same source.
        Return newly added debug packages.
        """
        added = set()

        if self.opts.exclude_debug:
            return added

        for pkg in self.result_binary_packages:
            assert pkg is not None

            if pkg in self.finished_add_debug_packages:
                continue

            candidates = []
            if pkg.sourcerpm:
                if self.is_native_package(pkg):
                    candidates = self.native_debug_packages_cache.get(pkg.sourcerpm)
                else:
                    candidates = self.multilib_debug_packages_cache.get(pkg.sourcerpm)

            if not candidates:
                continue

            debug_pkgs = []
            pkg_in_lookaside = pkg.repoid in self.opts.lookaside_repos
            for i in candidates:
                if pkg.arch != i.arch:
                    continue
                if "-debugsource" not in i.name and i.name != "%s-debuginfo" % pkg.name:
                    # If it's not debugsource package or does not match name of
                    # the package, we don't want it in.
                    continue
                if i.repoid in self.opts.lookaside_repos or pkg_in_lookaside:
                    self._set_flag(i, PkgFlag.lookaside)
                if i not in self.result_debug_packages:
                    added.add(i)
                    debug_pkgs.append(i)
                    self.logger.debug(
                        "Added debuginfo %s (for %s, repo: %s)" % (i, pkg, i.repo.id)
                    )

            self.finished_add_debug_packages[pkg] = debug_pkgs
            self.result_debug_packages.update(debug_pkgs)

        return added

    @Profiler("Gather.add_fulltree_packages()")
    def add_fulltree_packages(self):
        """
        For each binary package add all binary packages built from the same source.
        Return newly added binary packages.
        """
        added = set()

        if not self.opts.fulltree:
            return added

        for pkg in sorted(self.result_binary_packages):
            assert pkg is not None

            if get_source_name(pkg) in self.opts.fulltree_excludes:
                self.logger.debug("No fulltree for %s due to exclude list", pkg)
                continue

            try:
                fulltree_pkgs = self.finished_add_fulltree_packages[pkg]
            except KeyError:
                native_fulltree_pkgs = (
                    self.q_native_pkgs_by_sourcerpm_cache.get(pkg.sourcerpm) or []
                )
                multilib_fulltree_pkgs = (
                    self.q_multilib_pkgs_by_sourcerpm_cache.get(pkg.sourcerpm) or []
                )
                noarch_fulltree_pkgs = (
                    self.q_noarch_pkgs_by_sourcerpm_cache.get(pkg.sourcerpm) or []
                )

                if not native_fulltree_pkgs:
                    # no existing native pkgs -> pull multilib
                    pull_native = False
                elif set(native_fulltree_pkgs) & self.result_binary_packages:
                    # native pkgs in result -> pull native
                    pull_native = True
                elif set(multilib_fulltree_pkgs) & self.result_binary_packages:
                    # multilib pkgs in result -> pull multilib
                    pull_native = False
                else:
                    # fallback / default
                    pull_native = True

                # We pull packages determined by `pull_native`, or everything
                # if we're greedy
                fulltree_pkgs = []
                if pull_native or self.opts.greedy_method == "all":
                    fulltree_pkgs.extend(native_fulltree_pkgs)
                if not pull_native or self.opts.greedy_method == "all":
                    fulltree_pkgs.extend(multilib_fulltree_pkgs)

                # always pull all noarch subpackages
                fulltree_pkgs += noarch_fulltree_pkgs

            for i in fulltree_pkgs:
                if i not in self.result_binary_packages:
                    self._add_packages([i], reason="fulltree")
                    self._set_flag(i, PkgFlag.fulltree)
                    added.add(i)

                # don't run fulltree on added packages
                self.finished_add_fulltree_packages[i] = []

            self.finished_add_fulltree_packages[pkg] = fulltree_pkgs

        return added

    @Profiler("Gather.add_langpack_packages()")
    def add_langpack_packages(self, langpack_patterns):
        """
        For each binary package add all matching langpack packages.
        Return newly added binary packages.

        langpack_patterns: [{"name": <str>, "install": <str>}]
        """
        added = set()

        if not self.opts.langpacks:
            return added

        exceptions = ["man-pages-overrides"]

        for pkg in sorted(self.result_binary_packages):
            assert pkg is not None

            try:
                langpack_pkgs = self.finished_add_langpack_packages[pkg]
            except KeyError:
                patterns = [
                    i["install"] for i in langpack_patterns if i["name"] == pkg.name
                ]
                patterns = [i.replace("%s", "*") for i in patterns]

                if not patterns:
                    self.finished_add_langpack_packages[pkg] = []
                    continue

                langpack_pkgs = self.q_binary_packages.filter(
                    name__glob=patterns
                ).apply()
                langpack_pkgs = langpack_pkgs.filter(
                    name__glob__not=["*-devel", "*-static"]
                )
                langpack_pkgs = langpack_pkgs.filter(name__neq=exceptions)

            pkgs_by_name = {}
            for i in langpack_pkgs:
                pkgs_by_name.setdefault(i.name, set()).add(i)

            langpack_pkgs = set()
            for name in sorted(pkgs_by_name):
                pkgs = pkgs_by_name[name]
                i = self._get_best_package(pkgs)
                if i:
                    # TODO: greedy
                    i = i[0]
                langpack_pkgs.add(i)
                self._set_flag(i, PkgFlag.langpack)
                if i not in self.result_binary_packages:
                    self._add_packages([i], pulled_by=pkg, reason="langpack")
                    added.add(pkg)
            self.finished_add_langpack_packages[pkg] = langpack_pkgs

        return added

    @Profiler("Gather.add_multilib_packages()")
    def add_multilib_packages(self):
        added = set()

        for pkg in sorted(self.result_binary_packages):
            if pkg in self.finished_add_multilib_packages:
                continue

            if pkg.arch in ("noarch", "src", "nosrc"):
                self.finished_add_multilib_packages[pkg] = None
                continue

            if pkg.arch in self.dnf.arch_wrapper.multilib_arches:
                self.finished_add_multilib_packages[pkg] = None
                continue

            pkgs = self.q_multilib_binary_packages_cache.get(
                pkg.name, pkg.version, pkg.release
            )
            pkgs = self._get_best_package(pkgs)
            multilib_pkgs = []
            for i in pkgs:
                is_multilib = self._multilib.is_multilib(i)
                if is_multilib:
                    multilib_pkgs.append(i)
                    added.add(i)
                    self._set_flag(i, PkgFlag.multilib)
                    self._add_packages([i], reason="multilib:%s" % is_multilib)
                    self.finished_add_multilib_packages[pkg] = i
                    # TODO: ^^^ may get multiple results; i686, i586, etc.

        return added

    @Profiler("Gather.gather()")
    def gather(self, pattern_list, conditional_packages=None):
        self.conditional_packages = conditional_packages or []

        self.logger.debug("INITIAL PACKAGES")
        added, added_debuginfo = self.add_initial_packages(pattern_list)
        self._add_packages(added)
        if added_debuginfo:
            self._add_packages(added_debuginfo, dest=self.result_debug_packages)

        added = self.log_count("PREPOPULATE", self.add_prepopulate_packages)
        self._add_packages(added, reason="prepopulate")

        for pass_num in count(1):
            self.logger.debug("PASS %s" % pass_num)

            if self.log_count("CONDITIONAL DEPS", self.add_conditional_packages):
                continue

            # resolve deps
            if self.log_count("BINARY DEPS", self.add_binary_package_deps):
                continue

            if self.log_count("SOURCE DEPS", self.add_source_package_deps):
                continue

            if self.log_count("SOURCE PACKAGES", self.add_source_packages):
                continue

            if self.log_count("DEBUG PACKAGES", self.add_debug_packages):
                continue

            if self.log_count("DEBUG DEPS", self.add_debug_package_deps):
                continue

            if self.log_count("FULLTREE", self.add_fulltree_packages):
                continue

            if self.log_count(
                "LANGPACKS", self.add_langpack_packages, self.opts.langpacks
            ):
                continue

            if self.log_count("MULTILIB", self.add_multilib_packages):
                continue

            # nothing added -> break depsolving cycle
            break

    def download(self, destdir):
        pkglist = (
            self.result_binary_packages
            | self.result_debug_packages
            | self.result_source_packages
        )
        self.dnf.download_packages(pkglist)
        linker = Linker(logger=self.logger)

        for pkg in pkglist:
            basename = os.path.basename(pkg.relativepath)
            target = os.path.join(destdir, basename)

            # Link downloaded package in (or link package from file repo)
            try:
                linker.link(pkg.localPkg(), target)
            except Exception:
                self.logger.error("Unable to link %s from the yum cache." % pkg.name)
                raise

    def log_count(self, msg, method, *args):
        """
        Print a message, run the function with given arguments and log length
        of result.
        """
        self.logger.debug("%s", msg)
        added = method(*args)
        self.logger.debug("ADDED: %s", len(added))
        return added
