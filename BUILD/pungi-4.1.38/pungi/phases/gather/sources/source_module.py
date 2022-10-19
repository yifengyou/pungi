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


"""
Get a package list based on modulemd metadata loaded in pkgset phase. Each
modulemd file contains a list of exact RPM NEVRAs that should be include, so
just go over all modules in a given variant and join all lists together.
"""


import pungi.arch
import pungi.phases.gather.source


class GatherSourceModule(pungi.phases.gather.source.GatherSourceBase):
    enabled = True

    def __call__(self, arch, variant):
        groups = set()
        packages = set()

        # Check if this variant contains some modules
        if variant is None or variant.modules is None:
            return packages, groups

        compatible_arches = pungi.arch.get_compatible_arches(arch, multilib=True)

        for nsvc, mmd in variant.arch_mmds[arch].items():
            available_rpms = sum(
                (
                    variant.nsvc_to_pkgset[nsvc].rpms_by_arch.get(a, [])
                    for a in compatible_arches
                ),
                [],
            )
            to_include = set(mmd.get_rpm_artifacts().get())
            for rpm_obj in available_rpms:
                if rpm_obj.nevra in to_include:
                    packages.add((rpm_obj, None))

        return packages, groups
