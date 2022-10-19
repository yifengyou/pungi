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


import collections
import os
import shutil

from kobo.shortcuts import run
from kobo.threads import run_in_threads

from pungi.phases.base import PhaseBase
from pungi.phases.gather import write_prepopulate_file
from pungi.util import temp_dir, iter_module_defaults
from pungi.wrappers.comps import CompsWrapper
from pungi.wrappers.createrepo import CreaterepoWrapper
from pungi.wrappers.scm import get_dir_from_scm, get_file_from_scm


class InitPhase(PhaseBase):
    """INIT is a mandatory phase"""
    name = "init"

    def skip(self):
        # INIT must never be skipped,
        # because it generates data for LIVEIMAGES
        return False

    def run(self):
        if self.compose.has_comps:
            # write global comps and arch comps, create comps repos
            global_comps = write_global_comps(self.compose)
            validate_comps(global_comps)
            num_workers = self.compose.conf['createrepo_num_threads']
            run_in_threads(
                _arch_worker,
                [(self.compose, arch) for arch in self.compose.get_arches()],
                threads=num_workers,
            )

            # write variant comps
            run_in_threads(
                _variant_worker,
                [
                    (self.compose, arch, variant)
                    for variant in self.compose.get_variants()
                    for arch in variant.arches
                ],
                threads=num_workers,
            )

        # download variants.xml / product.xml?

        # download module defaults
        if self.compose.has_module_defaults:
            write_module_defaults(self.compose)
            validate_module_defaults(
                self.compose.paths.work.module_defaults_dir(create_dir=False)
            )

        # write prepopulate file
        write_prepopulate_file(self.compose)


def _arch_worker(_, args, num):
    compose, arch = args
    write_arch_comps(compose, arch)
    create_comps_repo(compose, arch, None)


def _variant_worker(_, args, num):
    compose, arch, variant = args
    write_variant_comps(compose, arch, variant)
    create_comps_repo(compose, arch, variant)


def write_global_comps(compose):
    comps_file_global = compose.paths.work.comps(arch="global")
    msg = "Writing global comps file: %s" % comps_file_global

    if compose.DEBUG and os.path.isfile(comps_file_global):
        compose.log_warning("[SKIP ] %s" % msg)
    else:
        scm_dict = compose.conf["comps_file"]
        if isinstance(scm_dict, dict):
            comps_name = os.path.basename(scm_dict["file"])
            if scm_dict["scm"] == "file":
                scm_dict["file"] = os.path.join(compose.config_dir, scm_dict["file"])
        else:
            comps_name = os.path.basename(scm_dict)
            scm_dict = os.path.join(compose.config_dir, scm_dict)

        compose.log_debug(msg)
        tmp_dir = compose.mkdtemp(prefix="comps_")
        get_file_from_scm(scm_dict, tmp_dir, logger=compose._logger)
        shutil.copy2(os.path.join(tmp_dir, comps_name), comps_file_global)
        shutil.rmtree(tmp_dir)

    return comps_file_global


def write_arch_comps(compose, arch):
    comps_file_arch = compose.paths.work.comps(arch=arch)
    msg = "Writing comps file for arch '%s': %s" % (arch, comps_file_arch)

    if compose.DEBUG and os.path.isfile(comps_file_arch):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_debug(msg)
    run(["comps_filter", "--arch=%s" % arch, "--no-cleanup",
         "--output=%s" % comps_file_arch,
         compose.paths.work.comps(arch="global")])


UNMATCHED_GROUP_MSG = 'Variant %s.%s requires comps group %s which does not match anything in input comps file'


def get_lookaside_groups(compose, variant):
    """Find all groups listed in parent variant."""
    groups = set()
    if variant.parent:
        groups.update(g["name"] for g in variant.parent.groups)

    for var, lookaside in compose.conf.get("variant_as_lookaside", []):
        if var == variant.uid:
            lookaside_variant = compose.all_variants[lookaside]
            groups.update(g["name"] for g in lookaside_variant.groups)
    return groups


def write_variant_comps(compose, arch, variant):
    comps_file = compose.paths.work.comps(arch=arch, variant=variant)
    msg = "Writing comps file (arch: %s, variant: %s): %s" % (arch, variant, comps_file)

    if compose.DEBUG and os.path.isfile(comps_file):
        # read display_order and groups for environments (needed for live images)
        comps = CompsWrapper(comps_file)
        # groups = variant.groups
        comps.filter_groups(variant.groups)
        if compose.conf["comps_filter_environments"]:
            comps.filter_environments(variant.environments)

        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_debug(msg)
    cmd = [
        "comps_filter",
        "--arch=%s" % arch,
        "--keep-empty-group=conflicts",
        "--keep-empty-group=conflicts-%s" % variant.uid.lower(),
        "--variant=%s" % variant.uid,
        "--output=%s" % comps_file,
        compose.paths.work.comps(arch="global")
    ]
    for group in get_lookaside_groups(compose, variant):
        cmd.append("--lookaside-group=%s" % group)
    run(cmd)

    comps = CompsWrapper(comps_file)
    if variant.groups or variant.modules is not None or variant.type != 'variant':
        # Filter groups if the variant has some, or it's a modular variant, or
        # is not a base variant.
        unmatched = comps.filter_groups(variant.groups)
        for grp in unmatched:
            compose.log_warning(UNMATCHED_GROUP_MSG % (variant.uid, arch, grp))
    contains_all = not variant.groups and not variant.environments
    if compose.conf["comps_filter_environments"] and not contains_all:
        # We only want to filter environments if it's enabled by configuration
        # and it's a variant with some groups and environements defined. If
        # there are none, all packages should go in there and also all
        # environments should be preserved.
        comps.filter_environments(variant.environments)
    comps.write_comps()


def create_comps_repo(compose, arch, variant):
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    comps_repo = compose.paths.work.comps_repo(arch=arch, variant=variant)
    comps_path = compose.paths.work.comps(arch=arch, variant=variant)
    msg = "Creating comps repo for arch '%s' variant '%s'" % (arch, variant.uid if variant else None)
    if compose.DEBUG and os.path.isdir(os.path.join(comps_repo, "repodata")):
        compose.log_warning("[SKIP ] %s" % msg)
    else:
        compose.log_info("[BEGIN] %s" % msg)
        cmd = repo.get_createrepo_cmd(comps_repo, database=False,
                                      outputdir=comps_repo, groupfile=comps_path,
                                      checksum=createrepo_checksum)
        logfile = 'comps_repo-%s' % variant if variant else 'comps_repo'
        run(cmd, logfile=compose.paths.log.log_file(arch, logfile),
            show_cmd=True)
        compose.log_info("[DONE ] %s" % msg)


def write_module_defaults(compose):
    scm_dict = compose.conf["module_defaults_dir"]
    if isinstance(scm_dict, dict):
        if scm_dict["scm"] == "file":
            scm_dict["dir"] = os.path.join(compose.config_dir, scm_dict["dir"])
    else:
        scm_dict = os.path.join(compose.config_dir, scm_dict)

    with temp_dir(prefix="moduledefaults_") as tmp_dir:
        get_dir_from_scm(scm_dict, tmp_dir, logger=compose._logger)
        compose.log_debug("Writing module defaults")
        shutil.copytree(tmp_dir, compose.paths.work.module_defaults_dir(create_dir=False))


def validate_module_defaults(path):
    """Make sure there are no conflicting defaults. Each module name can only
    have one default stream.

    :param str path: directory with cloned module defaults
    """
    seen_defaults = collections.defaultdict(set)

    for mmddef in iter_module_defaults(path):
        seen_defaults[mmddef.peek_module_name()].add(mmddef.peek_default_stream())

    errors = []
    for module_name, defaults in seen_defaults.items():
        if len(defaults) > 1:
            errors.append(
                "Module %s has multiple defaults: %s"
                % (module_name, ", ".join(sorted(defaults)))
            )

    if errors:
        raise RuntimeError(
            "There are duplicated module defaults:\n%s" % "\n".join(errors)
        )


def validate_comps(path):
    """Check that there are whitespace issues in comps."""
    wrapper = CompsWrapper(path)
    wrapper.validate()
