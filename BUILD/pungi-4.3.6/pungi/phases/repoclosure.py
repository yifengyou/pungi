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


import glob
import os
import shutil

from kobo.shortcuts import run

from pungi.wrappers import repoclosure
from pungi.arch import get_valid_arches
from pungi.phases.base import PhaseBase
from pungi.phases.gather import get_lookaside_repos, get_gather_methods
from pungi.util import is_arch_multilib, temp_dir, get_arch_variant_data


class RepoclosurePhase(PhaseBase):
    name = "repoclosure"

    def run(self):
        run_repoclosure(self.compose)


def run_repoclosure(compose):
    msg = "Running repoclosure"
    compose.log_info("[BEGIN] %s" % msg)

    # Variant repos
    for arch in compose.get_arches():
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib)
        for variant in compose.get_variants(arch=arch):
            if variant.is_empty:
                continue

            conf = get_arch_variant_data(
                compose.conf, "repoclosure_strictness", arch, variant
            )
            if conf and conf[-1] == "off":
                continue

            prefix = "%s-repoclosure" % compose.compose_id
            lookaside = {}
            if variant.parent:
                repo_id = "%s-%s.%s" % (prefix, variant.parent.uid, arch)
                repo_dir = compose.paths.compose.repository(
                    arch=arch, variant=variant.parent
                )
                lookaside[repo_id] = repo_dir

            repos = {}
            repo_id = "%s-%s.%s" % (prefix, variant.uid, arch)
            repo_dir = compose.paths.compose.repository(arch=arch, variant=variant)
            repos[repo_id] = repo_dir

            for i, lookaside_url in enumerate(
                get_lookaside_repos(compose, arch, variant)
            ):
                lookaside[
                    "%s-lookaside-%s.%s-%s" % (compose.compose_id, variant.uid, arch, i)
                ] = lookaside_url

            logfile = compose.paths.log.log_file(arch, "repoclosure-%s" % variant)

            try:
                _, methods = get_gather_methods(compose, variant)
                if methods == "hybrid":
                    # Using hybrid solver, no repoclosure command is available.
                    pattern = compose.paths.log.log_file(
                        arch, "hybrid-depsolver-%s-iter-*" % variant
                    )
                    fus_logs = sorted(glob.glob(pattern))
                    repoclosure.extract_from_fus_logs(fus_logs, logfile)
                else:
                    _run_repoclosure_cmd(compose, repos, lookaside, arches, logfile)
            except RuntimeError as exc:
                if conf and conf[-1] == "fatal":
                    raise
                else:
                    compose.log_warning(
                        "Repoclosure failed for %s.%s\n%s" % (variant.uid, arch, exc)
                    )
            finally:
                if methods != "hybrid":
                    _delete_repoclosure_cache_dirs(compose)

    compose.log_info("[DONE ] %s" % msg)


def _delete_repoclosure_cache_dirs(compose):
    if "dnf" == compose.conf["repoclosure_backend"]:
        from dnf.const import SYSTEM_CACHEDIR
        from dnf.util import am_i_root
        from dnf.yum.misc import getCacheDir

        if am_i_root():
            top_cache_dir = SYSTEM_CACHEDIR
        else:
            top_cache_dir = getCacheDir()
    else:
        from yum.misc import getCacheDir

        top_cache_dir = getCacheDir()

    for name in os.listdir(top_cache_dir):
        if name.startswith(compose.compose_id):
            cache_path = os.path.join(top_cache_dir, name)
            if os.path.isdir(cache_path):
                shutil.rmtree(cache_path)
            else:
                os.remove(cache_path)


def _run_repoclosure_cmd(compose, repos, lookaside, arches, logfile):
    cmd = repoclosure.get_repoclosure_cmd(
        backend=compose.conf["repoclosure_backend"],
        repos=repos,
        lookaside=lookaside,
        arch=arches,
    )
    # Use temp working directory directory as workaround for
    # https://bugzilla.redhat.com/show_bug.cgi?id=795137
    with temp_dir(prefix="repoclosure_") as tmp_dir:
        run(cmd, logfile=logfile, workdir=tmp_dir, show_cmd=True)
