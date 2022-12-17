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
Get a package list based on a JSON mapping.

Input format:
{
    variant: {
        tree_arch: {
            rpm_name: [rpm_arch, rpm_arch, ... (or None for any/best arch)],
        }
    }
}

Output:
set([(rpm_name, rpm_arch or None)])
"""


import json
import os

import pungi.phases.gather.source


class GatherSourceJson(pungi.phases.gather.source.GatherSourceBase):
    def __call__(self, arch, variant):
        json_path = self.compose.conf.get("gather_source_mapping")
        if not json_path:
            return set(), set()
        with open(os.path.join(self.compose.config_dir, json_path), "r") as f:
            mapping = json.load(f)

        packages = set()
        if variant is None:
            # get all packages for all variants
            for variant_uid in mapping:
                for pkg_name, pkg_arches in mapping[variant_uid].get(arch, {}).items():
                    for pkg_arch in pkg_arches:
                        packages.add((pkg_name, pkg_arch))
        else:
            # get packages for a particular variant
            for pkg_name, pkg_arches in (
                mapping.get(variant.uid, {}).get(arch, {}).items()
            ):
                for pkg_arch in pkg_arches:
                    packages.add((pkg_name, pkg_arch))
        return packages, set()
