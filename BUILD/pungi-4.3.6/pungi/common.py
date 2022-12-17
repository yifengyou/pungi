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


class OptionsBase(object):
    def __init__(self, **kwargs):
        """
        inherit and initialize attributes
        call self.merge_options(**kwargs) at the end
        """
        pass

    def merge_options(self, **kwargs):
        """
        override defaults with user defined values
        """
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise ValueError(
                    "Invalid option in %s: %s" % (self.__class__.__name__, key)
                )
            setattr(self, key, value)
