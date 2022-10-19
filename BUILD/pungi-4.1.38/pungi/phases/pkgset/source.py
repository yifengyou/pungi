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


import kobo.plugins


class PkgsetSourceBase(kobo.plugins.Plugin):
    def __init__(self, compose):
        self.compose = compose


class PkgsetSourceContainer(kobo.plugins.PluginContainer):
    @classmethod
    def normalize_name(cls, name):
        return name.lower()
