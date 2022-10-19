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

from kobo.shortcuts import run

from pungi.wrappers import repoclosure
from pungi.arch import get_valid_arches
from pungi.phases.base import PhaseBase
from pungi.phases.gather import get_lookaside_repos, get_gather_methods
from pungi.util import is_arch_multilib, failable, temp_dir, get_arch_variant_data


class TestPhase(PhaseBase):
    name = "test"

    def run(self):
        run_repoclosure(self.compose)
        check_image_sanity(self.compose)


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

            conf = get_arch_variant_data(compose.conf, 'repoclosure_strictness', arch, variant)
            if conf and conf[-1] == 'off':
                continue

            lookaside = {}
            if variant.parent:
                repo_id = "repoclosure-%s.%s" % (variant.parent.uid, arch)
                repo_dir = compose.paths.compose.repository(arch=arch, variant=variant.parent)
                lookaside[repo_id] = repo_dir

            repos = {}
            repo_id = "repoclosure-%s.%s" % (variant.uid, arch)
            repo_dir = compose.paths.compose.repository(arch=arch, variant=variant)
            repos[repo_id] = repo_dir

            for i, lookaside_url in enumerate(get_lookaside_repos(compose, arch, variant)):
                lookaside["lookaside-%s.%s-%s" % (variant.uid, arch, i)] = lookaside_url

            logfile = compose.paths.log.log_file(arch, "repoclosure-%s" % variant)

            try:
                _, methods = get_gather_methods(compose, variant)
                if methods == "hybrid":
                    # Using hybrid solver, no repoclosure command is available.
                    pattern = compose.paths.log.log_file(
                        arch, "hybrid-depsolver-%s-iter-*" % variant
                    )
                    fus_log = sorted(glob.glob(pattern))[-1]
                    repoclosure.extract_from_fus_log(fus_log, logfile)
                else:
                    _run_repoclosure_cmd(compose, repos, lookaside, arches, logfile)
            except RuntimeError as exc:
                if conf and conf[-1] == 'fatal':
                    raise
                else:
                    compose.log_warning('Repoclosure failed for %s.%s\n%s'
                                        % (variant.uid, arch, exc))

    compose.log_info("[DONE ] %s" % msg)


def _run_repoclosure_cmd(compose, repos, lookaside, arches, logfile):
    cmd = repoclosure.get_repoclosure_cmd(backend=compose.conf["repoclosure_backend"],
                                          repos=repos, lookaside=lookaside, arch=arches)
    # Use temp working directory directory as workaround for
    # https://bugzilla.redhat.com/show_bug.cgi?id=795137
    with temp_dir(prefix="repoclosure_") as tmp_dir:
        # Ideally we would want show_cmd=True here to include the
        # command in the logfile, but due to a bug in Kobo that would
        # cause any error to be printed directly to stderr.
        #  https://github.com/release-engineering/kobo/pull/26
        run(cmd, logfile=logfile, workdir=tmp_dir, show_cmd=True)


def check_image_sanity(compose):
    """
    Go through all images in manifest and make basic sanity tests on them. If
    any check fails for a failable deliverable, a message will be printed and
    logged. Otherwise the compose will be aborted.
    """
    im = compose.im
    for variant in compose.get_variants():
        if variant.uid not in im.images:
            continue
        for arch in variant.arches:
            if arch not in im.images[variant.uid]:
                continue
            for img in im.images[variant.uid][arch]:
                check_sanity(compose, variant, arch, img)
                check_size_limit(compose, variant, arch, img)


def check_sanity(compose, variant, arch, image):
    path = os.path.join(compose.paths.compose.topdir(), image.path)
    deliverable = getattr(image, 'deliverable')
    can_fail = getattr(image, 'can_fail', False)
    with failable(compose, can_fail, variant, arch, deliverable,
                  subvariant=image.subvariant):
        with open(path, 'rb') as f:
            iso = is_iso(f)
            if image.format == 'iso' and not iso:
                raise RuntimeError('%s does not look like an ISO file' % path)
            if (image.arch in ('x86_64', 'i386') and
                    image.bootable and
                    not has_mbr(f) and
                    not has_gpt(f) and
                    not (iso and has_eltorito(f))):
                raise RuntimeError(
                    '%s is supposed to be bootable, but does not have MBR nor '
                    'GPT nor is it a bootable ISO' % path)
    # If exception is raised above, failable may catch it, in which case
    # nothing else will happen.


def _check_magic(f, offset, bytes):
    """Check that the file has correct magic number at correct offset."""
    f.seek(offset)
    return f.read(len(bytes)) == bytes


def is_iso(f):
    return _check_magic(f, 0x8001, b'CD001')


def has_mbr(f):
    return _check_magic(f, 0x1fe, b'\x55\xAA')


def has_gpt(f):
    return _check_magic(f, 0x200, b'EFI PART')


def has_eltorito(f):
    return _check_magic(f, 0x8801, b'CD001\1EL TORITO SPECIFICATION')


def check_size_limit(compose, variant, arch, img):
    """If a size of the ISO image is over the configured limit, report a
    warning. Do nothing for other types of images.
    """
    if img.format != "iso":
        return
    limits = get_arch_variant_data(compose.conf, "createiso_max_size", arch, variant)
    if not limits and not getattr(img, "_max_size", None):
        return
    # For ISOs created in extra_isos phase we add an attribute with the limit,
    # and there is a global option otherwise.
    limit = getattr(img, "_max_size", None) or limits[0]

    if img.size > limit:
        compose.log_warning(
            "ISO %s is too big. Expected max %dB, got %dB" % (img.path, limit, img.size)
        )
