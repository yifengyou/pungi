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
Expected product.img paths
==========================

RHEL 6
------
installclasses/$variant.py
locale/$lang/LC_MESSAGES/comps.mo

RHEL 7
------
run/install/product/installclasses/$variant.py
run/install/product/locale/$lang/LC_MESSAGES/comps.mo

Compatibility symlinks
----------------------
installclasses -> run/install/product/installclasses
locale -> run/install/product/locale
run/install/product/pyanaconda/installclasses -> ../installclasses
"""


import os
import fnmatch
import shutil
from six.moves import shlex_quote

from kobo.shortcuts import run

from pungi.arch import split_name_arch
from pungi.util import makedirs, pkg_is_rpm
from pungi.phases.base import PhaseBase
from pungi.wrappers import iso
from pungi.wrappers.scm import get_file_from_scm, get_dir_from_scm


class ProductimgPhase(PhaseBase):
    """PRODUCTIMG"""
    name = "productimg"

    def __init__(self, compose, pkgset_phase):
        PhaseBase.__init__(self, compose)
        # pkgset_phase provides package_sets and path_prefix
        self.pkgset_phase = pkgset_phase

    def skip(self):
        if PhaseBase.skip(self):
            return True
        if not self.compose.conf["productimg"]:
            msg = "Config option 'productimg' not set. Skipping creating product images."
            self.compose.log_debug(msg)
            return True
        if not self.compose.conf["bootable"]:
            msg = "Not a bootable product. Skipping creating product images."
            self.compose.log_debug(msg)
            return True
        return False

    def run(self):
        # create PRODUCT.IMG
        for variant in self.compose.get_variants():
            if variant.type != "variant" or variant.is_empty:
                continue
            create_product_img(self.compose, "global", variant)

        # copy PRODUCT.IMG
        for arch in self.compose.get_arches():
            for variant in self.compose.get_variants(arch=arch):
                if variant.type != "variant" or variant.is_empty:
                    continue
                image = self.compose.paths.work.product_img(variant)
                os_tree = self.compose.paths.compose.os_tree(arch, variant)
                target_dir = os.path.join(os_tree, "images")
                target_path = os.path.join(target_dir, "product.img")
                if not os.path.isfile(target_path):
                    makedirs(target_dir)
                    shutil.copy2(image, target_path)

        for arch in self.compose.get_arches():
            for variant in self.compose.get_variants(arch=arch):
                if variant.type != "variant" or variant.is_empty:
                    continue
                rebuild_boot_iso(self.compose, arch, variant, self.pkgset_phase.package_sets)


def create_product_img(compose, arch, variant):
    # product.img is noarch (at least on rhel6 and rhel7)
    arch = "global"

    msg = "Creating product.img (arch: %s, variant: %s)" % (arch, variant)
    image = compose.paths.work.product_img(variant)
    if os.path.exists(image):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)

    product_tmp = compose.mkdtemp(prefix="product_img_")
    install_class = compose.conf["productimg_install_class"].copy()
    install_class["file"] = install_class["file"] % {"variant_id": variant.id.lower()}
    install_dir = os.path.join(product_tmp, "installclasses")
    makedirs(install_dir)
    get_file_from_scm(install_class, target_path=install_dir, logger=None)

    po_files = compose.conf["productimg_po_files"]
    po_tmp = compose.mkdtemp(prefix="pofiles_")
    get_dir_from_scm(po_files, po_tmp, logger=compose._logger)
    for po_file in os.listdir(po_tmp):
        if not po_file.endswith(".po"):
            continue
        lang = po_file[:-3]
        target_dir = os.path.join(product_tmp, "locale", lang, "LC_MESSAGES")
        makedirs(target_dir)
        run(["msgfmt", "--output-file", os.path.join(target_dir, "comps.mo"), os.path.join(po_tmp, po_file)])

    shutil.rmtree(po_tmp)

    ret, __ = run(["which", "guestmount"], can_fail=True)
    guestmount_available = not bool(ret)  # return code 0 means that guestmount is available

    mount_tmp = compose.mkdtemp(prefix="product_img_mount_")
    cmds = [
        # allocate image
        "dd if=/dev/zero of=%s bs=1k count=5760" % shlex_quote(image),
        # create file system
        "mke2fs -F %s" % shlex_quote(image),
        # use guestmount to mount the image, which doesn't require root privileges
        # LIBGUESTFS_BACKEND=direct: running qemu directly without libvirt
        "LIBGUESTFS_BACKEND=direct guestmount -a %s -m /dev/sda %s" % (shlex_quote(image), shlex_quote(mount_tmp)) if guestmount_available
        else "mount -o loop %s %s" % (shlex_quote(image), shlex_quote(mount_tmp)),
        "mkdir -p %s/run/install/product" % shlex_quote(mount_tmp),
        "cp -rp %s/* %s/run/install/product/" % (shlex_quote(product_tmp), shlex_quote(mount_tmp)),
        "mkdir -p %s/run/install/product/pyanaconda" % shlex_quote(mount_tmp),
        # compat symlink: installclasses -> run/install/product/installclasses
        "ln -s run/install/product/installclasses %s" % shlex_quote(mount_tmp),
        # compat symlink: locale -> run/install/product/locale
        "ln -s run/install/product/locale %s" % shlex_quote(mount_tmp),
        # compat symlink: run/install/product/pyanaconda/installclasses -> ../installclasses
        "ln -s ../installclasses %s/run/install/product/pyanaconda/installclasses" % shlex_quote(mount_tmp),
        "fusermount -u %s" % shlex_quote(mount_tmp) if guestmount_available
        else "umount %s" % shlex_quote(mount_tmp),
        # tweak last mount path written in the image
        "tune2fs -M /run/install/product %s" % shlex_quote(image),
    ]
    run(" && ".join(cmds))
    shutil.rmtree(mount_tmp)

    shutil.rmtree(product_tmp)

    compose.log_info("[DONE ] %s" % msg)


def rebuild_boot_iso(compose, arch, variant, package_sets):
    os_tree = compose.paths.compose.os_tree(arch, variant)
    buildinstall_dir = compose.paths.work.buildinstall_dir(arch)
    boot_iso = os.path.join(os_tree, "images", "boot.iso")
    product_img = compose.paths.work.product_img(variant)
    buildinstall_boot_iso = os.path.join(buildinstall_dir, "images", "boot.iso")
    buildinstall_method = compose.conf["buildinstall_method"]
    log_file = compose.paths.log.log_file(arch, "rebuild_boot_iso-%s.%s" % (variant, arch))

    msg = "Rebuilding boot.iso (arch: %s, variant: %s)" % (arch, variant)

    if not os.path.isfile(boot_iso):
        # nothing to do
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)

    # read the original volume id
    volume_id = iso.get_volume_id(boot_iso)

    # remove the original boot.iso (created during buildinstall) from the os dir
    os.remove(boot_iso)

    tmp_dir = compose.mkdtemp(prefix="boot_iso_")
    mount_dir = compose.mkdtemp(prefix="boot_iso_mount_")

    cmd = "mount -o loop %s %s" % (shlex_quote(buildinstall_boot_iso), shlex_quote(mount_dir))
    run(cmd, logfile=log_file, show_cmd=True)

    images_dir = os.path.join(tmp_dir, "images")
    os.makedirs(images_dir)
    shutil.copy2(product_img, os.path.join(images_dir, "product.img"))

    if os.path.isfile(os.path.join(mount_dir, "isolinux", "isolinux.bin")):
        os.makedirs(os.path.join(tmp_dir, "isolinux"))
        shutil.copy2(os.path.join(mount_dir, "isolinux", "isolinux.bin"), os.path.join(tmp_dir, "isolinux"))

    graft_points = iso.get_graft_points([mount_dir, tmp_dir])
    graft_points_path = os.path.join(compose.paths.work.topdir(arch=arch), "boot-%s.%s.iso-graft-points" % (variant, arch))
    iso.write_graft_points(graft_points_path, graft_points, exclude=["*/TRANS.TBL", "*/boot.cat"])

    mkisofs_kwargs = {}
    boot_files = None
    if buildinstall_method == "lorax":
        # TODO: $arch instead of ppc
        mkisofs_kwargs["boot_args"] = iso.get_boot_options(arch, "/usr/share/lorax/config_files/ppc")
    elif buildinstall_method == "buildinstall":
        boot_files = explode_anaconda(compose, arch, variant, package_sets)
        mkisofs_kwargs["boot_args"] = iso.get_boot_options(arch, boot_files)

    # ppc(64) doesn't seem to support utf-8
    if arch in ("ppc", "ppc64"):
        mkisofs_kwargs["input_charset"] = None

    mkisofs_cmd = iso.get_mkisofs_cmd(boot_iso, None, volid=volume_id, exclude=["./lost+found"], graft_points=graft_points_path, **mkisofs_kwargs)
    run(mkisofs_cmd, logfile=log_file, show_cmd=True)

    cmd = "umount %s" % shlex_quote(mount_dir)
    run(cmd, logfile=log_file, show_cmd=True)

    if arch == "x86_64":
        isohybrid_cmd = "isohybrid --uefi %s" % shlex_quote(boot_iso)
        run(isohybrid_cmd, logfile=log_file, show_cmd=True)
    elif arch == "i386":
        isohybrid_cmd = "isohybrid %s" % shlex_quote(boot_iso)
        run(isohybrid_cmd, logfile=log_file, show_cmd=True)

    # implant MD5SUM to iso
    isomd5sum_cmd = iso.get_implantisomd5_cmd(boot_iso, compose.supported)
    isomd5sum_cmd = " ".join([shlex_quote(i) for i in isomd5sum_cmd])
    run(isomd5sum_cmd, logfile=log_file, show_cmd=True)

    if boot_files:
        shutil.rmtree(boot_files)
    shutil.rmtree(tmp_dir)
    shutil.rmtree(mount_dir)

    compose.log_info("[DONE ] %s" % msg)


def explode_anaconda(compose, arch, variant, package_sets):
    tmp_dir = compose.mkdtemp(prefix="anaconda_")
    scm_dict = {
        "scm": "rpm",
        "repo": "anaconda.%s" % arch,
        "file": [
            "/usr/lib/anaconda-runtime/boot/*",
        ]
    }
    # if scm is "rpm" and repo contains a package name, find the package(s) in package set
    if scm_dict["scm"] == "rpm" and not (scm_dict["repo"].startswith("/") or "://" in scm_dict["repo"]):
        rpms = []
        for pkgset_file in package_sets[arch]:
            pkg_obj = package_sets[arch][pkgset_file]
            if not pkg_is_rpm(pkg_obj):
                continue
            pkg_name, pkg_arch = split_name_arch(scm_dict["repo"])
            if fnmatch.fnmatch(pkg_obj.name, pkg_name) and (pkg_arch is None or pkg_arch == pkg_obj.arch):
                compose.log_critical("%s %s %s" % (pkg_obj.name, pkg_name, pkg_arch))
                rpms.append(pkg_obj.file_path)
        scm_dict["repo"] = rpms

        if not rpms:
            return None
    get_file_from_scm(scm_dict, tmp_dir, logger=compose._logger)
    return tmp_dir
