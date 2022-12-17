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
import sys
import time

from ConfigParser import SafeConfigParser

from .arch_utils import getBaseArch

# In development, `here` will point to the bin/ directory with scripts.
here = sys.path[0]
MULTILIBCONF = (
    os.path.join(os.path.dirname(__file__), "..", "share", "multilib")
    if here != "/usr/bin"
    else "/usr/share/pungi/multilib"
)


class Config(SafeConfigParser):
    def __init__(self, pungirc=None):
        SafeConfigParser.__init__(self)

        self.add_section("pungi")
        self.add_section("lorax")

        self.set("pungi", "osdir", "os")
        self.set("pungi", "sourcedir", "source")
        self.set("pungi", "debugdir", "debug")
        self.set("pungi", "isodir", "iso")
        self.set("pungi", "multilibconf", MULTILIBCONF)
        self.set(
            "pungi", "relnotefilere", "LICENSE README-BURNING-ISOS-en_US.txt ^RPM-GPG"
        )
        self.set("pungi", "relnotedirre", "")
        self.set(
            "pungi", "relnotepkgs", "fedora-repos fedora-release fedora-release-notes"
        )
        self.set("pungi", "product_path", "Packages")
        self.set("pungi", "cachedir", "/var/cache/pungi")
        self.set("pungi", "compress_type", "xz")
        self.set("pungi", "arch", getBaseArch())
        self.set("pungi", "family", "Fedora")
        self.set("pungi", "iso_basename", "Fedora")
        self.set("pungi", "version", time.strftime("%Y%m%d", time.localtime()))
        self.set("pungi", "variant", "")
        self.set("pungi", "destdir", os.getcwd())
        self.set("pungi", "workdirbase", "/work")
        self.set("pungi", "bugurl", "https://bugzilla.redhat.com")
        self.set("pungi", "cdsize", "695.0")
        self.set("pungi", "debuginfo", "True")
        self.set("pungi", "alldeps", "True")
        self.set("pungi", "isfinal", "False")
        self.set("pungi", "nohash", "False")
        self.set("pungi", "full_archlist", "False")
        self.set("pungi", "multilib", "")
        self.set("pungi", "lookaside_repos", "")
        self.set("pungi", "resolve_deps", "True")
        self.set("pungi", "no_dvd", "False")
        self.set("pungi", "nomacboot", "False")
        self.set("pungi", "rootfs_size", "False")

        # if missing, self.read() is a noop, else change 'defaults'
        if pungirc:
            self.read(os.path.expanduser(pungirc))
