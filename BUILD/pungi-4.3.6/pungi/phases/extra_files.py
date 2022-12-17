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
import copy
import fnmatch

from productmd.extra_files import ExtraFiles

from pungi.util import get_arch_variant_data, pkg_is_rpm, copy_all
from pungi.arch import split_name_arch
from pungi.wrappers.scm import get_file_from_scm, get_dir_from_scm
from pungi.phases.base import ConfigGuardedPhase
from pungi import metadata


class ExtraFilesPhase(ConfigGuardedPhase):
    """EXTRA_FILES"""

    name = "extra_files"

    def __init__(self, compose, pkgset_phase):
        super(ExtraFilesPhase, self).__init__(compose)
        # pkgset_phase provides package_sets
        self.pkgset_phase = pkgset_phase
        # Prepare metadata
        self.metadata = ExtraFiles()
        self.metadata.compose.id = self.compose.compose_id
        self.metadata.compose.type = self.compose.compose_type
        self.metadata.compose.date = self.compose.compose_date
        self.metadata.compose.respin = self.compose.compose_respin

    def run(self):
        for variant in self.compose.get_variants():
            if variant.is_empty:
                continue
            for arch in variant.arches + ["src"]:
                cfg = get_arch_variant_data(self.compose.conf, self.name, arch, variant)
                if cfg:
                    copy_extra_files(
                        self.compose,
                        cfg,
                        arch,
                        variant,
                        self.pkgset_phase.package_sets,
                        self.metadata,
                    )
                else:
                    self.compose.log_info(
                        "[SKIP ] No extra files (arch: %s, variant: %s)"
                        % (arch, variant.uid)
                    )

        metadata_path = self.compose.paths.compose.metadata("extra_files.json")
        self.compose.log_info("Writing global extra files metadata: %s" % metadata_path)
        self.metadata.dump(metadata_path)


def copy_extra_files(
    compose, cfg, arch, variant, package_sets, extra_metadata, checksum_type=None
):
    checksum_type = checksum_type or compose.conf["media_checksums"]
    var_dict = {
        "arch": arch,
        "variant_id": variant.id,
        "variant_id_lower": variant.id.lower(),
        "variant_uid": variant.uid,
        "variant_uid_lower": variant.uid.lower(),
    }

    msg = "Getting extra files (arch: %s, variant: %s)" % (arch, variant)
    compose.log_info("[BEGIN] %s" % msg)

    os_tree = compose.paths.compose.os_tree(arch, variant)
    extra_files_dir = compose.paths.work.extra_files_dir(arch, variant)

    for scm_dict in cfg:
        scm_dict = copy.deepcopy(scm_dict)
        # if scm is "rpm" and repo contains only a package name, find the
        # package(s) in package set
        if scm_dict["scm"] == "rpm" and not _is_external(scm_dict["repo"]):
            rpms = []
            pattern = scm_dict["repo"] % var_dict
            pkg_name, pkg_arch = split_name_arch(pattern)
            for package_set in package_sets:
                for pkgset_file in package_set[arch]:
                    pkg_obj = package_set[arch][pkgset_file]
                    if pkg_is_rpm(pkg_obj) and _pkg_matches(
                        pkg_obj, pkg_name, pkg_arch
                    ):
                        rpms.append(pkg_obj.file_path)
            if not rpms:
                raise RuntimeError(
                    "No package matching %s in the package set." % pattern
                )
            scm_dict["repo"] = rpms

        getter = get_file_from_scm if "file" in scm_dict else get_dir_from_scm
        target_path = os.path.join(
            extra_files_dir, scm_dict.get("target", "").lstrip("/")
        )
        getter(scm_dict, target_path, compose=compose)

    if os.listdir(extra_files_dir):
        metadata.populate_extra_files_metadata(
            extra_metadata,
            variant,
            arch,
            os_tree,
            copy_all(extra_files_dir, os_tree),
            compose.conf["media_checksums"],
            relative_root=compose.paths.compose.topdir(),
        )

    compose.log_info("[DONE ] %s" % msg)


def _pkg_matches(pkg_obj, name_glob, arch):
    """Check if `pkg_obj` matches name and arch."""
    return fnmatch.fnmatch(pkg_obj.name, name_glob) and (
        arch is None or arch == pkg_obj.arch
    )


def _is_external(rpm):
    """Check if path to rpm points outside of the compose: i.e. it is an
    absolute path or a URL."""
    return rpm.startswith("/") or "://" in rpm
