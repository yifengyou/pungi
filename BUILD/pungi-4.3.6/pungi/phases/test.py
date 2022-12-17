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

from pungi.phases.base import PhaseBase
from pungi.util import failable, get_arch_variant_data
import productmd.compose


class TestPhase(PhaseBase):
    name = "test"

    def run(self):
        check_image_sanity(self.compose)
        check_image_metadata(self.compose)


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


def check_image_metadata(compose):
    """
    Check the images metadata for entries that cannot be serialized.
    Often caused by isos with duplicate metadata.
    Accessing the `images` attribute will raise an exception if there's a problem
    """
    if compose.im.images:
        compose = productmd.compose.Compose(compose.paths.compose.topdir())
        return compose.images


def check_sanity(compose, variant, arch, image):
    path = os.path.join(compose.paths.compose.topdir(), image.path)
    deliverable = getattr(image, "deliverable")
    can_fail = getattr(image, "can_fail", False)
    with failable(
        compose, can_fail, variant, arch, deliverable, subvariant=image.subvariant
    ):
        with open(path, "rb") as f:
            iso = is_iso(f)
            if image.format == "iso" and not iso:
                raise RuntimeError("%s does not look like an ISO file" % path)
            if (
                image.arch in ("x86_64", "i386")
                and image.bootable
                and not has_mbr(f)
                and not has_gpt(f)
                and not (iso and has_eltorito(f))
            ):
                raise RuntimeError(
                    "%s is supposed to be bootable, but does not have MBR nor "
                    "GPT nor is it a bootable ISO" % path
                )
    # If exception is raised above, failable may catch it, in which case
    # nothing else will happen.


def _check_magic(f, offset, bytes):
    """Check that the file has correct magic number at correct offset."""
    f.seek(offset)
    return f.read(len(bytes)) == bytes


def is_iso(f):
    return _check_magic(f, 0x8001, b"CD001")


def has_mbr(f):
    return _check_magic(f, 0x1FE, b"\x55\xAA")


def has_gpt(f):
    return _check_magic(f, 0x200, b"EFI PART")


def has_eltorito(f):
    return _check_magic(f, 0x8801, b"CD001\1EL TORITO SPECIFICATION")


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
        is_strict = get_arch_variant_data(
            compose.conf, "createiso_max_size_is_strict", arch, variant
        )
        msg = "ISO %s is too big. Expected max %dB, got %dB" % (
            img.path,
            limit,
            img.size,
        )
        if any(is_strict):
            raise RuntimeError(msg)
        else:
            compose.log_warning(msg)
