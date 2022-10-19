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


import fnmatch


def head_tail_split(name):
    name_split = name.strip("/").split("/", 1)
    if len(name_split) == 2:
        head = name_split[0]
        tail = name_split[1].strip("/")
    else:
        head, tail = name_split[0], None
    return head, tail


class PathMatch(object):
    def __init__(self, parent=None, desc=None):
        self._patterns = {}
        self._final_patterns = {}
        self._values = []

    def __setitem__(self, name, value):
        head, tail = head_tail_split(name)

        if tail is not None:
            # recursion
            if head not in self._patterns:
                self._patterns[head] = PathMatch(parent=self, desc=head)
            self._patterns[head][tail] = value
        else:
            if head not in self._final_patterns:
                self._final_patterns[head] = PathMatch(parent=self, desc=head)
            if value not in self._final_patterns[head]._values:
                self._final_patterns[head]._values.append(value)

    def __getitem__(self, name):
        result = []
        head, tail = head_tail_split(name)
        for pattern in self._patterns:
            if fnmatch.fnmatch(head, pattern):
                if tail is None:
                    values = self._patterns[pattern]._values
                else:
                    values = self._patterns[pattern][tail]
                for value in values:
                    if value not in result:
                        result.append(value)

        for pattern in self._final_patterns:
            if tail is None:
                x = head
            else:
                x = "%s/%s" % (head, tail)
            if fnmatch.fnmatch(x, pattern):
                values = self._final_patterns[pattern]._values
                for value in values:
                    if value not in result:
                        result.append(value)
        return result
