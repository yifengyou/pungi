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

from .source_comps import GatherSourceComps
from .source_json import GatherSourceJson
from .source_module import GatherSourceModule
from .source_none import GatherSourceNone

ALL_SOURCES = {
    "comps": GatherSourceComps,
    "json": GatherSourceJson,
    "module": GatherSourceModule,
    "none": GatherSourceNone,
}
