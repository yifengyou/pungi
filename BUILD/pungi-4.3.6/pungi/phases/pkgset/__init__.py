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


from pungi.phases.base import PhaseBase


class PkgsetPhase(PhaseBase):
    """PKGSET"""

    name = "pkgset"

    def __init__(self, compose, *args, **kwargs):
        super(PkgsetPhase, self).__init__(compose, *args, **kwargs)
        self.compose = compose
        self.package_sets = []
        self.path_prefix = None

    def run(self):
        from . import sources

        SourceClass = sources.ALL_SOURCES[self.compose.conf["pkgset_source"].lower()]

        self.package_sets, self.path_prefix = SourceClass(self.compose)()

    def validate(self):
        extra_tasks = self.compose.conf.get("pkgset_koji_scratch_tasks", None)
        sigkeys = tuple(self.compose.conf["sigkeys"] or [None])
        if extra_tasks is not None and None not in sigkeys and "" not in sigkeys:
            raise ValueError(
                "Unsigned packages must be allowed to use the "
                '"pkgset_koji_scratch_tasks" option'
            )
