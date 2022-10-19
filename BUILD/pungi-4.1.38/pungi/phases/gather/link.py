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

import kobo.rpmlib

from pungi.linker import LinkerPool


# TODO: global Linker instance - to keep hardlinks on dest?
# DONE: show overall progress, not each file
#   TODO: (these should be logged separately)

def _get_src_nevra(compose, pkg_obj, srpm_map):
    """Return source N-E:V-R.A.rpm; guess if necessary."""
    result = srpm_map.get(pkg_obj.sourcerpm, None)
    if not result:
        nvra = kobo.rpmlib.parse_nvra(pkg_obj.sourcerpm)
        nvra["epoch"] = pkg_obj.epoch
        result = kobo.rpmlib.make_nvra(nvra, add_rpm=True, force_epoch=True)
        compose.log_warning("Package %s has no SRPM available, guessing epoch: %s" % (pkg_obj.nevra, result))
    return result


def get_package_path(filename, hashed_directory=False):
    """Get path for filename. If ``hashed_directory`` is ``True``, the path
    will include a prefix based on the initial letter.

    >>> get_package_path('my-package.rpm')
    'my-package.rpm'
    >>> get_package_path('my-package.rpm', True)
    'm/my-package.rpm'
    >>> get_package_path('My-Package.rpm', True)
    'm/My-Package.rpm'
    """
    if hashed_directory:
        prefix = filename[0].lower()
        return os.path.join(prefix, filename)
    return filename


def link_files(compose, arch, variant, pkg_map, pkg_sets, manifest, srpm_map={}):
    # srpm_map instance is shared between link_files() runs
    pkg_set = pkg_sets[arch]

    msg = "Linking packages (arch: %s, variant: %s)" % (arch, variant)
    compose.log_info("[BEGIN] %s" % msg)
    link_type = compose.conf["link_type"]

    pool = LinkerPool.with_workers(10, link_type, logger=compose._logger)

    hashed_directories = compose.conf["hashed_directories"]

    packages_dir = compose.paths.compose.packages("src", variant)
    packages_dir_relpath = compose.paths.compose.packages("src", variant, relative=True)
    for pkg in pkg_map["srpm"]:
        if "lookaside" in pkg["flags"]:
            continue
        dst = os.path.join(packages_dir, get_package_path(os.path.basename(pkg["path"]), hashed_directories))
        dst_relpath = os.path.join(packages_dir_relpath, get_package_path(os.path.basename(pkg["path"]), hashed_directories))

        # link file
        pool.queue_put((pkg["path"], dst))

        # update rpm manifest
        pkg_obj = pkg_set[pkg["path"]]
        nevra = pkg_obj.nevra
        manifest.add(variant.uid, arch, nevra, path=dst_relpath, sigkey=pkg_obj.signature, category="source")

        # update srpm_map
        srpm_map.setdefault(pkg_obj.file_name, nevra)

    packages_dir = compose.paths.compose.packages(arch, variant)
    packages_dir_relpath = compose.paths.compose.packages(arch, variant, relative=True)
    for pkg in pkg_map["rpm"]:
        if "lookaside" in pkg["flags"]:
            continue
        dst = os.path.join(packages_dir, get_package_path(os.path.basename(pkg["path"]), hashed_directories))
        dst_relpath = os.path.join(packages_dir_relpath, get_package_path(os.path.basename(pkg["path"]), hashed_directories))

        # link file
        pool.queue_put((pkg["path"], dst))

        # update rpm manifest
        pkg_obj = pkg_set[pkg["path"]]
        nevra = pkg_obj.nevra
        src_nevra = _get_src_nevra(compose, pkg_obj, srpm_map)
        manifest.add(variant.uid, arch, nevra, path=dst_relpath, sigkey=pkg_obj.signature, category="binary", srpm_nevra=src_nevra)

    packages_dir = compose.paths.compose.debug_packages(arch, variant)
    packages_dir_relpath = compose.paths.compose.debug_packages(arch, variant, relative=True)
    for pkg in pkg_map["debuginfo"]:
        if "lookaside" in pkg["flags"]:
            continue
        dst = os.path.join(packages_dir, get_package_path(os.path.basename(pkg["path"]), hashed_directories))
        dst_relpath = os.path.join(packages_dir_relpath, get_package_path(os.path.basename(pkg["path"]), hashed_directories))

        # link file
        pool.queue_put((pkg["path"], dst))

        # update rpm manifest
        pkg_obj = pkg_set[pkg["path"]]
        nevra = pkg_obj.nevra
        src_nevra = _get_src_nevra(compose, pkg_obj, srpm_map)
        manifest.add(variant.uid, arch, nevra, path=dst_relpath, sigkey=pkg_obj.signature, category="debug", srpm_nevra=src_nevra)

    pool.start()
    pool.stop()
    compose.log_info("[DONE ] %s" % msg)
