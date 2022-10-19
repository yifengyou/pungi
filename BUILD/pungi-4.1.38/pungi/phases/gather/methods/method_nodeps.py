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
from pprint import pformat
from fnmatch import fnmatch
import six

import pungi.arch
from pungi.util import pkg_is_rpm, pkg_is_srpm, pkg_is_debug
from pungi.wrappers.comps import CompsWrapper

import pungi.phases.gather.method
from kobo.pkgset import SimpleRpmWrapper, RpmWrapper


class GatherMethodNodeps(pungi.phases.gather.method.GatherMethodBase):
    enabled = True

    def __call__(self, arch, variant, *args, **kwargs):
        fname = 'gather-nodeps-%s' % variant.uid
        if self.source_name:
            fname += '-' + self.source_name
        log_file = self.compose.paths.log.log_file(arch, fname)
        with open(log_file, 'w') as log:
            return self.worker(log, arch, variant, *args, **kwargs)

    def worker(self, log, arch, variant, pkgs, groups, filter_packages,
               multilib_whitelist, multilib_blacklist, package_sets,
               path_prefix=None, fulltree_excludes=None, prepopulate=None):
        pkgset = package_sets[arch]
        result = {
            "rpm": [],
            "srpm": [],
            "debuginfo": [],
        }

        group_packages = expand_groups(self.compose, arch, variant, groups)
        packages = pkgs | group_packages
        log.write('Requested packages:\n%s\n' % pformat(packages))

        seen_rpms = {}
        seen_srpms = {}

        valid_arches = pungi.arch.get_valid_arches(arch, multilib=True)
        compatible_arches = {}
        for i in valid_arches:
            compatible_arches[i] = pungi.arch.get_compatible_arches(i)

        log.write('\nGathering rpms\n')
        for i in pkgset:
            pkg = pkgset[i]
            if not pkg_is_rpm(pkg):
                continue
            for gathered_pkg, pkg_arch in packages:
                if isinstance(gathered_pkg, six.string_types) and not fnmatch(pkg.name, gathered_pkg):
                    continue
                elif (type(gathered_pkg) in [SimpleRpmWrapper, RpmWrapper]
                      and pkg.nevra != gathered_pkg.nevra):
                    continue
                if pkg_arch is not None and pkg.arch != pkg_arch and pkg.arch != 'noarch':
                    continue
                result["rpm"].append({
                    "path": pkg.file_path,
                    "flags": ["input"],
                })
                seen_rpms.setdefault(pkg.name, set()).add(pkg.arch)
                seen_srpms.setdefault(pkg.sourcerpm, set()).add(pkg.arch)
                log.write('Added %s (matched %s.%s) (sourcerpm: %s)\n'
                          % (pkg, gathered_pkg, pkg_arch, pkg.sourcerpm))

        log.write('\nGathering source rpms\n')
        for i in pkgset:
            pkg = pkgset[i]
            if not pkg_is_srpm(pkg):
                continue
            if pkg.file_name in seen_srpms:
                result["srpm"].append({
                    "path": pkg.file_path,
                    "flags": ["input"],
                })
                log.write('Adding %s\n' % pkg)

        log.write('\nGathering debuginfo packages\n')
        for i in pkgset:
            pkg = pkgset[i]
            if not pkg_is_debug(pkg):
                continue
            if pkg.sourcerpm not in seen_srpms:
                log.write('Not considering %s: corresponding srpm not included\n' % pkg)
                continue
            pkg_arches = set(compatible_arches[pkg.arch]) - set(['noarch'])
            seen_arches = set(seen_srpms[pkg.sourcerpm]) - set(['noarch'])
            if not (pkg_arches & seen_arches):
                # We only want to pull in a debuginfo if we have a binary
                # package for a compatible arch. Noarch packages should not
                # pull debuginfo (they would pull in all architectures).
                log.write('Not including %s: no package for this arch\n'
                          % pkg)
                continue
            result["debuginfo"].append({
                "path": pkg.file_path,
                "flags": ["input"],
            })
            log.write('Adding %s\n' % pkg)

        return result


def expand_groups(compose, arch, variant, groups, set_pkg_arch=True):
    """Read comps file filtered for given architecture and variant and return
    all packages in given groups.

    :returns: A set of tuples (pkg_name, arch)
    """
    if not groups:
        # No groups, nothing to do (this also covers case when there is no
        # comps file.
        return set()
    comps = []
    comps_file = compose.paths.work.comps(arch, variant, create_dir=False)
    comps.append(CompsWrapper(comps_file))

    if variant and variant.parent:
        parent_comps_file = compose.paths.work.comps(arch, variant.parent, create_dir=False)
        comps.append(CompsWrapper(parent_comps_file))

        if variant.type == 'optional':
            for v in variant.parent.variants.values():
                if v.id == variant.id:
                    continue
                comps_file = compose.paths.work.comps(arch, v, create_dir=False)
                if os.path.exists(comps_file):
                    comps.append(CompsWrapper(comps_file))

    packages = set()
    pkg_arch = arch if set_pkg_arch else None
    for group in groups:
        found = False
        ex = None
        for c in comps:
            try:
                packages.update([(pkg, pkg_arch) for pkg in c.get_packages(group)])
                found = True
                break
            except KeyError as e:
                ex = e

        if not found:
            raise ex

    return packages
