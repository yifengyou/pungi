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

from multilib import multilib


class Multilib(object):
    """This class decides whether a package should be multilib.

    To use it, create an instance and call the ``is_multilib`` method on it.
    The blacklist and whitelist in constructor should be sets of package names.

    It may be more convenient to create the instance with the ``from_globs``
    method that accepts a DNF sach and an iterable of globs that will be used
    to find package names.
    """
    def __init__(self, methods, blacklist, whitelist):
        self.methods = {}
        self.blacklist = blacklist
        self.whitelist = whitelist

        self.all_methods = {
            'none': multilib.NoMultilibMethod(None),
            'all': multilib.AllMultilibMethod(None),
            'devel': multilib.DevelMultilibMethod(None),
            'runtime': multilib.RuntimeMultilibMethod(None),
        }

        for method in methods:
            self.methods[method] = self.all_methods[method]

    @classmethod
    def from_globs(cls, sack, methods, blacklist=None, whitelist=None):
        """Create a Multilib instance with expanded blacklist and whitelist."""
        return cls(methods,
                   _expand_list(sack, blacklist or []),
                   _expand_list(sack, whitelist or []))

    def is_multilib(self, pkg):
        if pkg.name in self.blacklist:
            return False
        if pkg.name in self.whitelist:
            return 'whitelist'
        for method, cls in self.methods.items():
            if cls.select(pkg):
                return method
        return False


def _expand_list(sack, patterns):
    """Find all package names that match any of the provided patterns."""
    return set(pkg.name for pkg in sack.query().filter(name__glob=list(patterns)))
