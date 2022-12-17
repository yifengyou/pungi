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
Get a package list based on comps.xml.

Input format:
see comps.dtd

Output:
set([(rpm_name, rpm_arch or None)])
"""


from pungi.wrappers.comps import CompsWrapper
import pungi.phases.gather.source


class GatherSourceComps(pungi.phases.gather.source.GatherSourceBase):
    def __call__(self, arch, variant):
        groups = set()
        if not self.compose.conf.get("comps_file"):
            return set(), set()

        comps = CompsWrapper(self.compose.paths.work.comps(arch=arch, variant=variant))

        for i in comps.get_comps_groups():
            groups.add(i)
        return set(), groups
