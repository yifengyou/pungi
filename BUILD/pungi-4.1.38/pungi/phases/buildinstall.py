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


import errno
import os
import time
import shutil
import re

from kobo.threads import ThreadPool, WorkerThread
from kobo.shortcuts import run
from productmd.images import Image
from six.moves import shlex_quote

from pungi.arch import get_valid_arches
from pungi.util import get_volid, get_arch_variant_data
from pungi.util import get_file_size, get_mtime, failable, makedirs
from pungi.util import copy_all, translate_path
from pungi.wrappers.lorax import LoraxWrapper
from pungi.wrappers import iso
from pungi.wrappers.scm import get_file_from_scm
from pungi.phases.base import PhaseBase
from pungi.runroot import Runroot


class BuildinstallPhase(PhaseBase):
    name = "buildinstall"

    def __init__(self, compose):
        PhaseBase.__init__(self, compose)
        self.pool = ThreadPool(logger=self.compose._logger)
        # A set of (variant_uid, arch) pairs that completed successfully. This
        # is needed to skip copying files for failed tasks.
        self.pool.finished_tasks = set()
        self.buildinstall_method = self.compose.conf.get("buildinstall_method")
        self.used_lorax = self.buildinstall_method == 'lorax'

        self.warned_skipped = False

    def skip(self):
        if PhaseBase.skip(self):
            return True
        if not self.compose.conf.get("bootable"):
            if not self.warned_skipped:
                msg = "Not a bootable product. Skipping buildinstall."
                self.compose.log_debug(msg)
                self.warned_skipped = True
            return True
        return False

    def _get_lorax_cmd(self, repo_baseurl, output_dir, variant, arch, buildarch, volid, final_output_dir):
        noupgrade = True
        bugurl = None
        nomacboot = True
        add_template = []
        add_arch_template = []
        add_template_var = []
        add_arch_template_var = []
        rootfs_size = None
        version = self.compose.conf["release_version"]
        for data in get_arch_variant_data(self.compose.conf, 'lorax_options', arch, variant):
            if not data.get('noupgrade', True):
                noupgrade = False
            if data.get('bugurl'):
                bugurl = data.get('bugurl')
            if not data.get('nomacboot', True):
                nomacboot = False
            if "rootfs_size" in data:
                rootfs_size = data.get("rootfs_size")
            add_template.extend(data.get('add_template', []))
            add_arch_template.extend(data.get('add_arch_template', []))
            add_template_var.extend(data.get('add_template_var', []))
            add_arch_template_var.extend(data.get('add_arch_template_var', []))
            if "version" in data:
                version = data["version"]
        output_dir = os.path.join(output_dir, variant.uid)
        output_topdir = output_dir

        # The paths module will modify the filename (by inserting arch). But we
        # only care about the directory anyway.
        log_dir = _get_log_dir(self.compose, variant, arch)

        # If the buildinstall_topdir is set, it means Koji is used for
        # buildinstall phase and the filesystem with Koji is read-only.
        # In that case, we have to write logs to buildinstall_topdir and
        # later copy them back to our local log directory.
        if self.compose.conf.get("buildinstall_topdir", None):
            output_dir = os.path.join(output_dir, "results")

        repos = [repo_baseurl] + get_arch_variant_data(self.compose.conf,
                                                       'lorax_extra_sources', arch, variant)
        if self.compose.has_comps:
            comps_repo = self.compose.paths.work.comps_repo(arch, variant)
            if final_output_dir != output_dir:
                comps_repo = translate_path(self.compose, comps_repo)
            repos.append(comps_repo)

        lorax = LoraxWrapper()
        lorax_cmd = lorax.get_lorax_cmd(self.compose.conf["release_name"],
                                        version,
                                        version,
                                        repos,
                                        output_dir,
                                        variant=variant.uid,
                                        buildinstallpackages=variant.buildinstallpackages,
                                        is_final=self.compose.supported,
                                        buildarch=buildarch,
                                        volid=volid,
                                        nomacboot=nomacboot,
                                        bugurl=bugurl,
                                        add_template=add_template,
                                        add_arch_template=add_arch_template,
                                        add_template_var=add_template_var,
                                        add_arch_template_var=add_arch_template_var,
                                        noupgrade=noupgrade,
                                        rootfs_size=rootfs_size,
                                        log_dir=log_dir)
        return 'rm -rf %s && %s' % (shlex_quote(output_topdir),
                                    ' '.join([shlex_quote(x) for x in lorax_cmd]))

    def run(self):
        lorax = LoraxWrapper()
        product = self.compose.conf["release_name"]
        version = self.compose.conf["release_version"]
        release = self.compose.conf["release_version"]
        disc_type = self.compose.conf['disc_types'].get('dvd', 'dvd')

        # Prepare kickstart file for final images.
        self.pool.kickstart_file = get_kickstart_file(self.compose)

        for arch in self.compose.get_arches():
            commands = []

            output_dir = self.compose.paths.work.buildinstall_dir(arch, allow_topdir_override=True)
            final_output_dir = self.compose.paths.work.buildinstall_dir(arch, allow_topdir_override=False)
            makedirs(final_output_dir)
            repo_baseurl = self.compose.paths.work.arch_repo(arch)
            if final_output_dir != output_dir:
                repo_baseurl = translate_path(self.compose, repo_baseurl)

            if self.buildinstall_method == "lorax":

                buildarch = get_valid_arches(arch)[0]
                for variant in self.compose.get_variants(arch=arch, types=['variant']):
                    if variant.is_empty:
                        continue

                    skip = get_arch_variant_data(self.compose.conf, "buildinstall_skip", arch, variant)
                    if skip == [True]:
                        self.compose.log_info(
                            'Skipping buildinstall for %s.%s due to config option' % (variant, arch))
                        continue

                    volid = get_volid(self.compose, arch, variant=variant, disc_type=disc_type)
                    commands.append(
                        (variant,
                         self._get_lorax_cmd(repo_baseurl, output_dir, variant, arch, buildarch, volid, final_output_dir))
                    )
            elif self.buildinstall_method == "buildinstall":
                volid = get_volid(self.compose, arch, disc_type=disc_type)
                commands.append(
                    (None,
                     lorax.get_buildinstall_cmd(product,
                                                version,
                                                release,
                                                repo_baseurl,
                                                output_dir,
                                                is_final=self.compose.supported,
                                                buildarch=arch,
                                                volid=volid))
                )
            else:
                raise ValueError("Unsupported buildinstall method: %s" % self.buildinstall_method)

            for (variant, cmd) in commands:
                self.pool.add(BuildinstallThread(self.pool))
                self.pool.queue_put((self.compose, arch, variant, cmd))

        self.pool.start()

    def succeeded(self, variant, arch):
        # If the phase is skipped, we can treat it as successful. Either there
        # will be no output, or it's a debug run of compose where anything can
        # happen.
        return (super(BuildinstallPhase, self).skip()
                or (variant.uid if self.used_lorax else None, arch) in self.pool.finished_tasks)


def get_kickstart_file(compose):
    scm_dict = compose.conf.get("buildinstall_kickstart")
    if not scm_dict:
        compose.log_debug("Path to ks.cfg (buildinstall_kickstart) not specified.")
        return

    msg = "Getting ks.cfg"
    kickstart_path = os.path.join(compose.paths.work.topdir(arch="global"), "ks.cfg")
    if os.path.exists(kickstart_path):
        compose.log_warning("[SKIP ] %s" % msg)
        return kickstart_path

    compose.log_info("[BEGIN] %s" % msg)
    if isinstance(scm_dict, dict):
        kickstart_name = os.path.basename(scm_dict["file"])
        if scm_dict["scm"] == "file":
            scm_dict["file"] = os.path.join(compose.config_dir, scm_dict["file"])
    else:
        kickstart_name = os.path.basename(scm_dict)
        scm_dict = os.path.join(compose.config_dir, scm_dict)

    tmp_dir = compose.mkdtemp(prefix="buildinstall_kickstart_")
    get_file_from_scm(scm_dict, tmp_dir, logger=compose._logger)
    src = os.path.join(tmp_dir, kickstart_name)
    shutil.copy2(src, kickstart_path)
    compose.log_info("[DONE ] %s" % msg)
    return kickstart_path


BOOT_CONFIGS = [
    "isolinux/isolinux.cfg",
    "etc/yaboot.conf",
    "ppc/ppc64/yaboot.conf",
    "EFI/BOOT/BOOTX64.conf",
    "EFI/BOOT/grub.cfg",
]


def tweak_configs(path, volid, ks_file, configs=BOOT_CONFIGS):
    volid_escaped = volid.replace(" ", r"\x20").replace("\\", "\\\\")
    volid_escaped_2 = volid_escaped.replace("\\", "\\\\")
    found_configs = []
    for config in configs:
        config_path = os.path.join(path, config)
        if not os.path.exists(config_path):
            continue
        found_configs.append(config)

        with open(config_path, "r") as f:
            data = f.read()
        os.unlink(config_path)  # break hadlink by removing file writing a new one

        # double-escape volid in yaboot.conf
        new_volid = volid_escaped_2 if 'yaboot' in config else volid_escaped

        ks = (" ks=hd:LABEL=%s:/ks.cfg" % new_volid) if ks_file else ""

        # pre-f18
        data = re.sub(r":CDLABEL=[^ \n]*", r":CDLABEL=%s%s" % (new_volid, ks), data)
        # f18+
        data = re.sub(r":LABEL=[^ \n]*", r":LABEL=%s%s" % (new_volid, ks), data)
        data = re.sub(r"(search .* -l) '[^'\n]*'", r"\1 '%s'" % volid, data)

        with open(config_path, "w") as f:
            f.write(data)

    return found_configs


# HACK: this is a hack!
# * it's quite trivial to replace volids
# * it's not easy to replace menu titles
# * we probably need to get this into lorax
def tweak_buildinstall(compose, src, dst, arch, variant, label, volid, kickstart_file=None):
    tmp_dir = compose.mkdtemp(prefix="tweak_buildinstall_")

    # verify src
    if not os.path.isdir(src):
        raise OSError(errno.ENOENT, "Directory does not exist: %s" % src)

    # create dst
    try:
        os.makedirs(dst)
    except OSError as ex:
        if ex.errno != errno.EEXIST:
            raise

    # copy src to temp
    # TODO: place temp on the same device as buildinstall dir so we can hardlink
    cmd = "cp -dRv --preserve=mode,links,timestamps --remove-destination %s/* %s/" % (
        shlex_quote(src), shlex_quote(tmp_dir)
    )
    run(cmd)

    found_configs = tweak_configs(tmp_dir, volid, kickstart_file)
    if kickstart_file and found_configs:
        shutil.copy2(kickstart_file, os.path.join(dst, "ks.cfg"))

    images = [
        os.path.join(tmp_dir, "images", "efiboot.img"),
    ]
    for image in images:
        if not os.path.isfile(image):
            continue

        with iso.mount(image, logger=compose._logger,
                       use_guestmount=compose.conf.get("buildinstall_use_guestmount")
                       ) as mount_tmp_dir:
            for config in BOOT_CONFIGS:
                config_path = os.path.join(tmp_dir, config)
                config_in_image = os.path.join(mount_tmp_dir, config)

                if os.path.isfile(config_in_image):
                    cmd = ["cp", "-v", "--remove-destination", config_path, config_in_image]
                    run(cmd)

    # HACK: make buildinstall files world readable
    run("chmod -R a+rX %s" % shlex_quote(tmp_dir))

    # copy temp to dst
    cmd = "cp -dRv --preserve=mode,links,timestamps --remove-destination %s/* %s/" % (
        shlex_quote(tmp_dir), shlex_quote(dst)
    )
    run(cmd)

    shutil.rmtree(tmp_dir)


def link_boot_iso(compose, arch, variant, can_fail):
    if arch == "src":
        return

    disc_type = compose.conf['disc_types'].get('boot', 'boot')

    symlink_isos_to = compose.conf.get("symlink_isos_to")
    os_tree = compose.paths.compose.os_tree(arch, variant)
    # TODO: find in treeinfo?
    boot_iso_path = os.path.join(os_tree, "images", "boot.iso")
    if not os.path.isfile(boot_iso_path):
        return

    msg = "Linking boot.iso (arch: %s, variant: %s)" % (arch, variant)
    filename = compose.get_image_name(arch, variant, disc_type=disc_type,
                                      disc_num=None, suffix=".iso")
    new_boot_iso_path = compose.paths.compose.iso_path(arch, variant, filename,
                                                       symlink_to=symlink_isos_to)
    new_boot_iso_relative_path = compose.paths.compose.iso_path(arch,
                                                                variant,
                                                                filename,
                                                                relative=True)
    if os.path.exists(new_boot_iso_path):
        # TODO: log
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)
    # Try to hardlink, and copy if that fails
    try:
        os.link(boot_iso_path, new_boot_iso_path)
    except OSError:
        shutil.copy2(boot_iso_path, new_boot_iso_path)

    implant_md5 = iso.get_implanted_md5(new_boot_iso_path)
    iso_name = os.path.basename(new_boot_iso_path)
    iso_dir = os.path.dirname(new_boot_iso_path)

    # create iso manifest
    run(iso.get_manifest_cmd(iso_name), workdir=iso_dir)

    img = Image(compose.im)
    img.path = new_boot_iso_relative_path
    img.mtime = get_mtime(new_boot_iso_path)
    img.size = get_file_size(new_boot_iso_path)
    img.arch = arch
    img.type = "boot"
    img.format = "iso"
    img.disc_number = 1
    img.disc_count = 1
    img.bootable = True
    img.subvariant = variant.uid
    img.implant_md5 = implant_md5
    setattr(img, 'can_fail', can_fail)
    setattr(img, 'deliverable', 'buildinstall')
    try:
        img.volume_id = iso.get_volume_id(new_boot_iso_path)
    except RuntimeError:
        pass
    compose.im.add(variant.uid, arch, img)
    compose.log_info("[DONE ] %s" % msg)


class BuildinstallThread(WorkerThread):
    def process(self, item, num):
        # The variant is None unless lorax is used as buildinstall method.
        compose, arch, variant, cmd = item
        can_fail = compose.can_fail(variant, arch, 'buildinstall')
        with failable(compose, can_fail, variant, arch, 'buildinstall'):
            self.worker(compose, arch, variant, cmd, num)

    def worker(self, compose, arch, variant, cmd, num):
        buildinstall_method = compose.conf["buildinstall_method"]
        log_filename = ('buildinstall-%s' % variant.uid) if variant else 'buildinstall'
        log_file = compose.paths.log.log_file(arch, log_filename)

        msg = "Running buildinstall for arch %s, variant %s" % (arch, variant)

        output_dir = compose.paths.work.buildinstall_dir(
            arch, allow_topdir_override=True, variant=variant)
        final_output_dir = compose.paths.work.buildinstall_dir(
            arch, variant=variant)

        if (os.path.isdir(output_dir) and os.listdir(output_dir) or
                os.path.isdir(final_output_dir) and os.listdir(final_output_dir)):
            # output dir is *not* empty -> SKIP
            self.pool.log_warning(
                '[SKIP ] Buildinstall for arch %s, variant %s' % (arch, variant))
            return

        self.pool.log_info("[BEGIN] %s" % msg)

        # Get list of packages which are neded in runroot.
        packages = []
        chown_paths = [output_dir]
        if buildinstall_method == "lorax":
            packages += ["lorax"]
            chown_paths.append(_get_log_dir(compose, variant, arch))
        elif buildinstall_method == "buildinstall":
            packages += ["anaconda"]

        # This should avoid a possible race condition with multiple processes
        # trying to get a kerberos ticket at the same time.
        # Kerberos authentication failed: Permission denied in replay cache code (-1765328215)
        time.sleep(num * 3)

        # Start the runroot task.
        runroot = Runroot(compose)
        runroot.run(
            cmd, log_file=log_file, arch=arch, packages=packages,
            mounts=[compose.topdir],
            weight=compose.conf['runroot_weights'].get('buildinstall'),
            chown_paths=chown_paths,
        )

        if final_output_dir != output_dir:
            if not os.path.exists(final_output_dir):
                makedirs(final_output_dir)
            results_dir = os.path.join(output_dir, "results")
            copy_all(results_dir, final_output_dir)

            # Get the log_dir into which we should copy the resulting log files.
            log_fname = 'buildinstall-%s-logs/dummy' % variant.uid
            final_log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname))
            if not os.path.exists(final_log_dir):
                makedirs(final_log_dir)
            log_dir = os.path.join(output_dir, "logs")
            copy_all(log_dir, final_log_dir)

        log_file = compose.paths.log.log_file(arch, log_filename + '-RPMs')
        rpms = runroot.get_buildroot_rpms()
        with open(log_file, "w") as f:
            f.write("\n".join(rpms))

        self.pool.finished_tasks.add((variant.uid if variant else None, arch))

        self.copy_files(compose, variant, arch)

        self.pool.log_info("[DONE ] %s" % msg)

    def copy_files(self, compose, variant, arch):
        disc_type = compose.conf['disc_types'].get('dvd', 'dvd')

        buildinstall_dir = compose.paths.work.buildinstall_dir(arch)

        # Lorax runs per-variant, so we need to tweak the source path
        # to include variant.
        if variant:
            buildinstall_dir = os.path.join(buildinstall_dir, variant.uid)

        # Find all relevant variants if lorax is not used.
        variants = [variant] if variant else compose.get_variants(arch=arch, types=["self", "variant"])
        for var in variants:
            os_tree = compose.paths.compose.os_tree(arch, var)
            # TODO: label is not used
            label = ""
            volid = get_volid(compose, arch, var, disc_type=disc_type)
            can_fail = compose.can_fail(var, arch, 'buildinstall')
            tweak_buildinstall(
                compose,
                buildinstall_dir,
                os_tree,
                arch,
                var.uid,
                label,
                volid,
                self.pool.kickstart_file,
            )
            link_boot_iso(compose, arch, var, can_fail)


def _get_log_dir(compose, variant, arch):
    """Find directory where to store lorax logs in. If it's inside the compose,
    create the directory.
    """
    if compose.conf.get("buildinstall_topdir"):
        log_dir = compose.paths.work.buildinstall_dir(
            arch, allow_topdir_override=True, variant=variant
        )
        return os.path.join(log_dir, "logs")

    # The paths module will modify the filename (by inserting arch). But we
    # only care about the directory anyway.
    log_filename = 'buildinstall-%s-logs/dummy' % variant.uid
    log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_filename))
    makedirs(log_dir)
    return log_dir
