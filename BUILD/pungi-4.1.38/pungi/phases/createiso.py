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
import random
import shutil
import stat

import productmd.treeinfo
from productmd.images import Image
from kobo.threads import ThreadPool, WorkerThread
from kobo.shortcuts import run, relative_path
from six.moves import shlex_quote

from pungi.wrappers import iso
from pungi.wrappers.createrepo import CreaterepoWrapper
from pungi.wrappers import kojiwrapper
from pungi.phases.base import PhaseBase, PhaseLoggerMixin
from pungi.util import (makedirs, get_volid, get_arch_variant_data, failable,
                        get_file_size, get_mtime)
from pungi.media_split import MediaSplitter, convert_media_size
from pungi.compose_metadata.discinfo import read_discinfo, write_discinfo
from pungi.runroot import Runroot

from .. import createiso


class CreateisoPhase(PhaseLoggerMixin, PhaseBase):
    name = "createiso"

    def __init__(self, compose, buildinstall_phase):
        super(CreateisoPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.bi = buildinstall_phase

    def _find_rpms(self, path):
        """Check if there are some RPMs in the path."""
        for _, _, files in os.walk(path):
            for fn in files:
                if fn.endswith(".rpm"):
                    return True
        return False

    def _is_bootable(self, variant, arch):
        if arch == "src":
            return False
        if variant.type != "variant":
            return False
        skip = get_arch_variant_data(self.compose.conf, "buildinstall_skip", arch, variant)
        if skip == [True]:
            # Buildinstall is skipped for this tree. Can't create a bootable ISO.
            return False
        return self.compose.conf["bootable"]

    def run(self):
        symlink_isos_to = self.compose.conf.get("symlink_isos_to")
        disc_type = self.compose.conf['disc_types'].get('dvd', 'dvd')
        deliverables = []

        commands = []
        for variant in self.compose.get_variants(types=["variant", "layered-product", "optional"]):
            if variant.is_empty:
                continue
            for arch in variant.arches + ["src"]:
                skip_iso = get_arch_variant_data(self.compose.conf, "createiso_skip", arch, variant)
                if skip_iso == [True]:
                    self.logger.info("Skipping createiso for %s.%s due to config option" % (variant, arch))
                    continue

                volid = get_volid(self.compose, arch, variant, disc_type=disc_type)
                os_tree = self.compose.paths.compose.os_tree(arch, variant)

                iso_dir = self.compose.paths.compose.iso_dir(arch, variant, symlink_to=symlink_isos_to)
                if not iso_dir:
                    continue

                if not self._find_rpms(os_tree):
                    self.logger.warn("No RPMs found for %s.%s, skipping ISO"
                                     % (variant.uid, arch))
                    continue

                bootable = self._is_bootable(variant, arch)

                if bootable and not self.bi.succeeded(variant, arch):
                    self.logger.warning(
                        'ISO should be bootable, but buildinstall failed. Skipping for %s.%s'
                        % (variant, arch))
                    continue

                split_iso_data = split_iso(self.compose, arch, variant, no_split=bootable,
                                           logger=self.logger)
                disc_count = len(split_iso_data)

                for disc_num, iso_data in enumerate(split_iso_data):
                    disc_num += 1

                    filename = self.compose.get_image_name(
                        arch, variant, disc_type=disc_type, disc_num=disc_num)
                    iso_path = self.compose.paths.compose.iso_path(
                        arch, variant, filename, symlink_to=symlink_isos_to)
                    if os.path.isfile(iso_path):
                        self.logger.warn("Skipping mkisofs, image already exists: %s" % iso_path)
                        continue
                    deliverables.append(iso_path)

                    graft_points = prepare_iso(self.compose, arch, variant,
                                               disc_num=disc_num, disc_count=disc_count,
                                               split_iso_data=iso_data)

                    cmd = {
                        "iso_path": iso_path,
                        "bootable": bootable,
                        "cmd": [],
                        "label": "",  # currently not used
                        "disc_num": disc_num,
                        "disc_count": disc_count,
                    }

                    if os.path.islink(iso_dir):
                        cmd["mount"] = os.path.abspath(os.path.join(os.path.dirname(iso_dir),
                                                                    os.readlink(iso_dir)))

                    opts = createiso.CreateIsoOpts(
                        output_dir=iso_dir,
                        iso_name=filename,
                        volid=volid,
                        graft_points=graft_points,
                        arch=arch,
                        supported=self.compose.supported,
                        hfs_compat=self.compose.conf["iso_hfs_ppc64le_compatible"],
                    )

                    if bootable:
                        opts = opts._replace(buildinstall_method=self.compose.conf['buildinstall_method'])

                    if self.compose.conf['create_jigdo']:
                        jigdo_dir = self.compose.paths.compose.jigdo_dir(arch, variant)
                        opts = opts._replace(jigdo_dir=jigdo_dir, os_tree=os_tree)

                    script_file = os.path.join(self.compose.paths.work.tmp_dir(arch, variant),
                                               'createiso-%s.sh' % filename)
                    with open(script_file, 'w') as f:
                        createiso.write_script(opts, f)
                    cmd['cmd'] = ['bash', script_file]
                    commands.append((cmd, variant, arch))

        if self.compose.notifier:
            self.compose.notifier.send('createiso-targets', deliverables=deliverables)

        for (cmd, variant, arch) in commands:
            self.pool.add(CreateIsoThread(self.pool))
            self.pool.queue_put((self.compose, cmd, variant, arch))

        self.pool.start()


class CreateIsoThread(WorkerThread):
    def fail(self, compose, cmd, variant, arch):
        self.pool.log_error("CreateISO failed, removing ISO: %s" % cmd["iso_path"])
        try:
            # remove incomplete ISO
            os.unlink(cmd["iso_path"])
            # TODO: remove jigdo & template
        except OSError:
            pass
        if compose.notifier:
            compose.notifier.send('createiso-imagefail',
                                  file=cmd['iso_path'],
                                  arch=arch,
                                  variant=str(variant))

    def process(self, item, num):
        compose, cmd, variant, arch = item
        can_fail = compose.can_fail(variant, arch, 'iso')
        with failable(compose, can_fail, variant, arch, 'iso', logger=self.pool._logger):
            self.worker(compose, cmd, variant, arch, num)

    def worker(self, compose, cmd, variant, arch, num):
        mounts = [compose.topdir]
        if "mount" in cmd:
            mounts.append(cmd["mount"])

        bootable = cmd['bootable']
        log_file = compose.paths.log.log_file(
            arch, "createiso-%s" % os.path.basename(cmd["iso_path"]))

        msg = "Creating ISO (arch: %s, variant: %s): %s" % (
            arch, variant, os.path.basename(cmd["iso_path"]))
        self.pool.log_info("[BEGIN] %s" % msg)

        try:
            run_createiso_command(num, compose, bootable, arch,
                                  cmd['cmd'], mounts, log_file)
        except Exception:
            self.fail(compose, cmd, variant, arch)
            raise

        add_iso_to_metadata(compose, variant, arch, cmd["iso_path"],
                            cmd["bootable"], cmd["disc_num"], cmd["disc_count"])

        # Delete staging directory if present.
        staging_dir = compose.paths.work.iso_staging_dir(
            arch, variant, filename=os.path.basename(cmd["iso_path"])
        )
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)

        self.pool.log_info("[DONE ] %s" % msg)
        if compose.notifier:
            compose.notifier.send('createiso-imagedone',
                                  file=cmd['iso_path'],
                                  arch=arch,
                                  variant=str(variant))


def add_iso_to_metadata(
    compose,
    variant,
    arch,
    iso_path,
    bootable,
    disc_num=1,
    disc_count=1,
    additional_variants=None,
):
    img = Image(compose.im)
    img.path = iso_path.replace(compose.paths.compose.topdir(), '').lstrip('/')
    img.mtime = get_mtime(iso_path)
    img.size = get_file_size(iso_path)
    img.arch = arch
    # XXX: HARDCODED
    img.type = "dvd"
    img.format = "iso"
    img.disc_number = disc_num
    img.disc_count = disc_count
    img.bootable = bootable
    img.subvariant = variant.uid
    img.implant_md5 = iso.get_implanted_md5(iso_path, logger=compose._logger)
    if additional_variants:
        img.unified = True
        img.additional_variants = additional_variants
    setattr(img, 'can_fail', compose.can_fail(variant, arch, 'iso'))
    setattr(img, 'deliverable', 'iso')
    try:
        img.volume_id = iso.get_volume_id(iso_path)
    except RuntimeError:
        pass
    if arch == "src":
        for variant_arch in variant.arches:
            compose.im.add(variant.uid, variant_arch, img)
    else:
        compose.im.add(variant.uid, arch, img)
    return img


def run_createiso_command(num, compose, bootable, arch, cmd, mounts,
                          log_file, with_jigdo=True):
    packages = ["coreutils", "genisoimage", "isomd5sum"]
    if with_jigdo and compose.conf['create_jigdo']:
        packages.append('jigdo')
    if bootable:
        extra_packages = {
            'lorax': ['lorax', 'which'],
            'buildinstall': ['anaconda'],
        }
        packages.extend(extra_packages[compose.conf["buildinstall_method"]])

    runroot = Runroot(compose)

    build_arch = arch
    if runroot.runroot_method == "koji" and not bootable:
        runroot_tag = compose.conf["runroot_tag"]
        koji_wrapper = kojiwrapper.KojiWrapper(compose.conf["koji_profile"])
        koji_proxy = koji_wrapper.koji_proxy
        tag_info = koji_proxy.getTag(runroot_tag)
        if not tag_info:
            raise RuntimeError('Tag "%s" does not exist.' % runroot_tag)
        tag_arches = tag_info["arches"].split(" ")

        if "x86_64" in tag_arches:
            # assign non-bootable images to x86_64 if possible
            build_arch = "x86_64"
        elif build_arch == "src":
            # pick random arch from available runroot tag arches
            build_arch = random.choice(tag_arches)

    runroot.run(
        cmd, log_file=log_file, arch=build_arch, packages=packages, mounts=mounts,
        weight=compose.conf['runroot_weights'].get('createiso'))


def split_iso(compose, arch, variant, no_split=False, logger=None):
    """
    Split contents of the os/ directory for given tree into chunks fitting on ISO.

    All files from the directory are taken except for possible boot.iso image.
    Files added in extra_files phase are put on all disks.

    If `no_split` is set, we will pretend that the media is practically
    infinite so that everything goes on single disc. A warning is printed if
    the size is bigger than configured.
    """
    if not logger:
        logger = compose._logger
    media_size = compose.conf['iso_size']
    media_reserve = compose.conf['split_iso_reserve']
    split_size = convert_media_size(media_size) - convert_media_size(media_reserve)
    real_size = None if no_split else split_size

    ms = MediaSplitter(real_size, compose, logger=logger)

    os_tree = compose.paths.compose.os_tree(arch, variant)
    extra_files_dir = compose.paths.work.extra_files_dir(arch, variant)

    # scan extra files to mark them "sticky" -> they'll be on all media after split
    extra_files = set()
    for root, dirs, files in os.walk(extra_files_dir):
        for fn in files:
            path = os.path.join(root, fn)
            rel_path = relative_path(path, extra_files_dir.rstrip("/") + "/")
            extra_files.add(rel_path)

    packages = []
    all_files = []
    all_files_ignore = []

    ti = productmd.treeinfo.TreeInfo()
    ti.load(os.path.join(os_tree, ".treeinfo"))
    boot_iso_rpath = ti.images.images.get(arch, {}).get("boot.iso", None)
    if boot_iso_rpath:
        all_files_ignore.append(boot_iso_rpath)
    if all_files_ignore:
        logger.debug("split_iso all_files_ignore = %s" % ", ".join(all_files_ignore))

    for root, dirs, files in os.walk(os_tree):
        for dn in dirs[:]:
            repo_dir = os.path.join(root, dn)
            if repo_dir == os.path.join(compose.paths.compose.repository(arch, variant), "repodata"):
                dirs.remove(dn)

        for fn in files:
            path = os.path.join(root, fn)
            rel_path = relative_path(path, os_tree.rstrip("/") + "/")
            sticky = rel_path in extra_files
            if rel_path in all_files_ignore:
                logger.info("split_iso: Skipping %s" % rel_path)
                continue
            if root.startswith(compose.paths.compose.packages(arch, variant)):
                packages.append((path, os.path.getsize(path), sticky))
            else:
                all_files.append((path, os.path.getsize(path), sticky))

    for path, size, sticky in all_files + packages:
        ms.add_file(path, size, sticky)

    logger.debug('Splitting media for %s.%s:' % (variant.uid, arch))
    result = ms.split()
    if no_split and result[0]['size'] > split_size:
        logger.warn('ISO for %s.%s does not fit on single media! '
                    'It is %s bytes too big. (Total size: %s B)'
                    % (variant.uid, arch,
                       result[0]['size'] - split_size,
                       result[0]['size']))
    return result


def prepare_iso(compose, arch, variant, disc_num=1, disc_count=None, split_iso_data=None):
    tree_dir = compose.paths.compose.os_tree(arch, variant)
    filename = compose.get_image_name(arch, variant, disc_num=disc_num)
    iso_dir = compose.paths.work.iso_dir(arch, filename)

    # modify treeinfo
    ti_path = os.path.join(tree_dir, ".treeinfo")
    ti = load_and_tweak_treeinfo(ti_path, disc_num, disc_count)

    copy_boot_images(tree_dir, iso_dir)

    if disc_count > 1:
        # remove repodata/repomd.xml from checksums, create a new one later
        if "repodata/repomd.xml" in ti.checksums.checksums:
            del ti.checksums.checksums["repodata/repomd.xml"]

        # rebuild repodata
        createrepo_c = compose.conf["createrepo_c"]
        createrepo_checksum = compose.conf["createrepo_checksum"]
        repo = CreaterepoWrapper(createrepo_c=createrepo_c)

        file_list = "%s-file-list" % iso_dir
        packages_dir = compose.paths.compose.packages(arch, variant)
        file_list_content = []
        for i in split_iso_data["files"]:
            if not i.endswith(".rpm"):
                continue
            if not i.startswith(packages_dir):
                continue
            rel_path = relative_path(i, tree_dir.rstrip("/") + "/")
            file_list_content.append(rel_path)

        if file_list_content:
            # write modified repodata only if there are packages available
            run("cp -a %s/repodata %s/" % (shlex_quote(tree_dir), shlex_quote(iso_dir)))
            with open(file_list, "w") as f:
                f.write("\n".join(file_list_content))
            cmd = repo.get_createrepo_cmd(
                tree_dir,
                update=True,
                database=True,
                skip_stat=True,
                pkglist=file_list,
                outputdir=iso_dir,
                workers=compose.conf["createrepo_num_workers"],
                checksum=createrepo_checksum,
            )
            run(cmd)
            # add repodata/repomd.xml back to checksums
            ti.checksums.add("repodata/repomd.xml", "sha256", root_dir=iso_dir)

    new_ti_path = os.path.join(iso_dir, ".treeinfo")
    ti.dump(new_ti_path)

    # modify discinfo
    di_path = os.path.join(tree_dir, ".discinfo")
    data = read_discinfo(di_path)
    data["disc_numbers"] = [disc_num]
    new_di_path = os.path.join(iso_dir, ".discinfo")
    write_discinfo(new_di_path, **data)

    if not disc_count or disc_count == 1:
        data = iso.get_graft_points([tree_dir, iso_dir])
    else:
        data = iso.get_graft_points([iso._paths_from_list(tree_dir, split_iso_data["files"]), iso_dir])

    if compose.conf["createiso_break_hardlinks"]:
        compose.log_debug(
            "Breaking hardlinks for ISO %s for %s.%s" % (filename, variant, arch)
        )
        break_hardlinks(
            data, compose.paths.work.iso_staging_dir(arch, variant, filename)
        )
        # Create hardlinks for files with duplicate contents.
        compose.log_debug(
            "Creating hardlinks for ISO %s for %s.%s" % (filename, variant, arch)
        )
        create_hardlinks(
            compose.paths.work.iso_staging_dir(arch, variant, filename),
            log_file=compose.paths.log.log_file(arch, "iso-hardlink-%s.log" % variant.uid),
        )

    # TODO: /content /graft-points
    gp = "%s-graft-points" % iso_dir
    iso.write_graft_points(gp, data, exclude=["*/lost+found", "*/boot.iso"])
    return gp


def load_and_tweak_treeinfo(ti_path, disc_num=1, disc_count=1):
    """Treeinfo on the media should not contain any reference to boot.iso and
    it should also have a valid [media] section.
    """
    ti = productmd.treeinfo.TreeInfo()
    ti.load(ti_path)
    ti.media.totaldiscs = disc_count or 1
    ti.media.discnum = disc_num

    # remove boot.iso from all sections
    paths = set()
    for platform in ti.images.images:
        if "boot.iso" in ti.images.images[platform]:
            paths.add(ti.images.images[platform].pop("boot.iso"))

    # remove boot.iso from checksums
    for i in paths:
        if i in ti.checksums.checksums.keys():
            del ti.checksums.checksums[i]

    return ti


def copy_boot_images(src, dest):
    """When mkisofs is called it tries to modify isolinux/isolinux.bin and
    images/boot.img. Therefore we need to make copies of them.
    """
    for i in ("isolinux/isolinux.bin", "images/boot.img"):
        src_path = os.path.join(src, i)
        dst_path = os.path.join(dest, i)
        if os.path.exists(src_path):
            makedirs(os.path.dirname(dst_path))
            shutil.copy2(src_path, dst_path)


def break_hardlinks(graft_points, staging_dir):
    """Iterate over graft points and copy any file that has more than 1
    hardlink into the staging directory. Replace the entry in the dict.
    """
    for f in graft_points:
        info = os.stat(graft_points[f])
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            dest_path = os.path.join(staging_dir, graft_points[f].lstrip("/"))
            makedirs(os.path.dirname(dest_path))
            shutil.copy2(graft_points[f], dest_path)
            graft_points[f] = dest_path


def create_hardlinks(staging_dir, log_file):
    """Create hardlinks within the staging directory.
    Should happen after break_hardlinks()
    """
    cmd = ["/usr/sbin/hardlink", "-c", "-vv", staging_dir]
    run(cmd, logfile=log_file, show_cmd=True)
