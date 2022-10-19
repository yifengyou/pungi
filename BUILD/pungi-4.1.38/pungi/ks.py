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
Pungi adds several new sections to kickstarts.


FULLTREE EXCLUDES
-----------------
Fulltree excludes allow us to define SRPM names
we don't want to be part of fulltree processing.

Syntax:
%fulltree-excludes
<srpm_name>
<srpm_name>
...
%end


MULTILIB BLACKLIST
------------------
List of RPMs which are prevented from becoming multilib.

Syntax:
%multilib-blacklist
<rpm_name>
<rpm_name>
...
%end


MULTILIB WHITELIST
------------------
List of RPMs which will become multilib (but only if native package is pulled in).

Syntax:
%multilib-whitelist
<rpm_name>
<rpm_name>
...
%end


PREPOPULATE
-----------
To make sure no package is left behind between 2 composes,
we can explicitly add <name>.<arch> records to the %prepopulate section.
These will be added to the input list and marked with 'prepopulate' flag.

Syntax:
%prepopulate
<rpm_name>.<rpm_arch>
<rpm_name>.<rpm_arch>
...
%end
"""


import pykickstart.parser
import pykickstart.sections
from pykickstart.constants import GROUP_REQUIRED, GROUP_DEFAULT


class FulltreeExcludesSection(pykickstart.sections.Section):
    sectionOpen = "%fulltree-excludes"

    def handleLine(self, line):
        if not self.handler:
            return

        (h, s, t) = line.partition('#')
        line = h.rstrip()

        self.handler.fulltree_excludes.add(line)


class MultilibBlacklistSection(pykickstart.sections.Section):
    sectionOpen = "%multilib-blacklist"

    def handleLine(self, line):
        if not self.handler:
            return

        (h, s, t) = line.partition('#')
        line = h.rstrip()

        self.handler.multilib_blacklist.add(line)


class MultilibWhitelistSection(pykickstart.sections.Section):
    sectionOpen = "%multilib-whitelist"

    def handleLine(self, line):
        if not self.handler:
            return

        (h, s, t) = line.partition('#')
        line = h.rstrip()

        self.handler.multilib_whitelist.add(line)


class PrepopulateSection(pykickstart.sections.Section):
    sectionOpen = "%prepopulate"

    def handleLine(self, line):
        if not self.handler:
            return

        (h, s, t) = line.partition('#')
        line = h.rstrip()

        self.handler.prepopulate.add(line)


class PackageWhitelistSection(pykickstart.sections.Section):
    sectionOpen = "%package-whitelist"

    def handleLine(self, line):
        if not self.handler:
            return

        (h, s, t) = line.partition('#')
        line = h.rstrip()

        self.handler.package_whitelist.add(line)


class KickstartParser(pykickstart.parser.KickstartParser):
    def setupSections(self):
        pykickstart.parser.KickstartParser.setupSections(self)
        self.registerSection(FulltreeExcludesSection(self.handler))
        self.registerSection(MultilibBlacklistSection(self.handler))
        self.registerSection(MultilibWhitelistSection(self.handler))
        self.registerSection(PrepopulateSection(self.handler))
        self.registerSection(PackageWhitelistSection(self.handler))

    def get_packages(self, dnf_obj):
        packages = set()
        conditional_packages = []

        packages.update(self.handler.packages.packageList)

        for ks_group in self.handler.packages.groupList:
            group_id = ks_group.name

            if ks_group.include == GROUP_REQUIRED:
                include_default = False
                include_optional = False
            elif ks_group.include == GROUP_DEFAULT:
                include_default = True
                include_optional = False
            else:
                include_default = True
                include_optional = True

            group_packages, group_conditional_packages = dnf_obj.comps_wrapper.get_packages_from_group(group_id, include_default=include_default, include_optional=include_optional, include_conditional=True)
            packages.update(group_packages)
            for i in group_conditional_packages:
                if i not in conditional_packages:
                    conditional_packages.append(i)

        return packages, conditional_packages

    def get_excluded_packages(self, dnf_obj):
        excluded = set()
        excluded.update(self.handler.packages.excludedList)

        for ks_group in self.handler.packages.excludedGroupList:
            group_id = ks_group.name
            include_default = False
            include_optional = False

            if ks_group.include == 1:
                include_default = True

            if ks_group.include == 2:
                include_default = True
                include_optional = True

            group_packages, group_conditional_packages = dnf_obj.comps_wrapper.get_packages_from_group(group_id, include_default=include_default, include_optional=include_optional, include_conditional=False)
            excluded.update(group_packages)

        return excluded


HandlerClass = pykickstart.version.returnClassForVersion()


class PungiHandler(HandlerClass):
    def __init__(self, *args, **kwargs):
        HandlerClass.__init__(self, *args, **kwargs)
        self.fulltree_excludes = set()
        self.multilib_blacklist = set()
        self.multilib_whitelist = set()
        self.prepopulate = set()
        self.package_whitelist = set()


def get_ksparser(ks_path=None):
    """
    Return a kickstart parser instance.
    Read kickstart if ks_path provided.
    """
    ksparser = KickstartParser(PungiHandler())
    if ks_path:
        ksparser.readKickstart(ks_path)
    return ksparser
