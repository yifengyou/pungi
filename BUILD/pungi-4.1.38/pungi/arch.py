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

from .arch_utils import arches as ALL_ARCHES
from .arch_utils import getBaseArch, getMultiArchInfo, getArchList

TREE_ARCH_YUM_ARCH_MAP = {
    "i386": "i686",
    "sparc": "sparc64v",
    "arm": "armv7l",
    "armhfp": "armv7hnl",
}


def tree_arch_to_yum_arch(tree_arch):
    # this is basically an opposite to pungi.arch_utils.getBaseArch()
    yum_arch = TREE_ARCH_YUM_ARCH_MAP.get(tree_arch, tree_arch)
    return yum_arch


def get_multilib_arch(yum_arch):
    arch_info = getMultiArchInfo(yum_arch)
    if arch_info is None:
        return None
    return arch_info[0]


def get_valid_multilib_arches(tree_arch):
    yum_arch = tree_arch_to_yum_arch(tree_arch)
    multilib_arch = get_multilib_arch(yum_arch)
    if not multilib_arch:
        return []
    return [i for i in getArchList(multilib_arch) if i not in ("noarch", "src")]


def get_valid_arches(tree_arch, multilib=True, add_noarch=True, add_src=False):
    result = []

    yum_arch = tree_arch_to_yum_arch(tree_arch)
    for arch in getArchList(yum_arch):
        if arch not in result:
            result.append(arch)

    if not multilib:
        for i in get_valid_multilib_arches(tree_arch):
            while i in result:
                result.remove(i)

    if add_noarch and "noarch" not in result:
        result.append("noarch")

    if add_src and "src" not in result:
        result.append("src")

    return result


def get_compatible_arches(arch, multilib=False):
    tree_arch = getBaseArch(arch)
    compatible_arches = get_valid_arches(tree_arch, multilib=multilib)
    return compatible_arches


def is_valid_arch(arch):
    if arch in ("noarch", "src", "nosrc"):
        return True
    if arch in ALL_ARCHES:
        return True
    return False


def split_name_arch(name_arch):
    if "." in name_arch:
        name, arch = name_arch.rsplit(".", 1)
        if not is_valid_arch(arch):
            name, arch = name_arch, None
    else:
        name, arch = name_arch, None
    return name, arch


def is_excluded(package, arches, logger=None):
    """Check if package is excluded from given architectures."""
    if (package.excludearch and set(package.excludearch) & set(arches)):
        if logger:
            logger.debug("Excluding (EXCLUDEARCH: %s): %s"
                         % (sorted(set(package.excludearch)), package.file_name))
        return True
    if (package.exclusivearch and not (set(package.exclusivearch) & set(arches))):
        if logger:
            logger.debug("Excluding (EXCLUSIVEARCH: %s): %s"
                         % (sorted(set(package.exclusivearch)), package.file_name))
        return True
    return False
