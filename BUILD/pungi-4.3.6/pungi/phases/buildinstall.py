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
from six.moves import cPickle as pickle
from copy import copy

from kobo.threads import ThreadPool, WorkerThread
from kobo.shortcuts import run, force_list
import kobo.rpmlib
from productmd.images import Image
from six.moves import shlex_quote

from pungi.arch import get_valid_arches
from pungi.util import get_volid, get_arch_variant_data
from pungi.util import get_file_size, get_mtime, failable, makedirs
from pungi.util import copy_all, translate_path, move_all
from pungi.wrappers.lorax import LoraxWrapper
from pungi.wrappers import iso
from pungi.wrappers.scm import get_file
from pungi.wrappers.scm import get_file_from_scm
from pungi.wrappers import kojiwrapper
from pungi.phases.base import PhaseBase
from pungi.runroot import Runroot


class BuildinstallPhase(PhaseBase):
    name = "buildinstall"

    def __init__(self, compose, pkgset_phase=None):
        PhaseBase.__init__(self, compose)
        self.pool = ThreadPool(logger=self.compose._logger)
        # A set of (variant_uid, arch) pairs that completed successfully. This
        # is needed to skip copying files for failed tasks.
        self.pool.finished_tasks = set()
        # A set of (variant_uid, arch) pairs that were reused from previous
        # compose.
        self.pool.reused_tasks = set()
        self.buildinstall_method = self.compose.conf.get("buildinstall_method")
        self.lorax_use_koji_plugin = self.compose.conf.get("lorax_use_koji_plugin")
        self.used_lorax = self.buildinstall_method == "lorax"
        self.pkgset_phase = pkgset_phase

        self.warned_skipped = False

    def skip(self):
        if PhaseBase.skip(self):
            return True
        if not self.compose.conf.get("buildinstall_method"):
            if not self.warned_skipped:
                msg = "Not a bootable product. Skipping buildinstall."
                self.compose.log_debug(msg)
                self.warned_skipped = True
            return True
        return False

    def _get_lorax_cmd(
        self,
        repo_baseurl,
        output_dir,
        variant,
        arch,
        buildarch,
        volid,
        final_output_dir,
    ):
        noupgrade = True
        bugurl = None
        nomacboot = True
        add_template = []
        add_arch_template = []
        add_template_var = []
        add_arch_template_var = []
        dracut_args = []
        rootfs_size = None
        skip_branding = False
        squashfs_only = False
        configuration_file = None
        configuration_file_source = None
        version = self.compose.conf.get(
            "treeinfo_version", self.compose.conf["release_version"]
        )
        for data in get_arch_variant_data(
            self.compose.conf, "lorax_options", arch, variant
        ):
            if not data.get("noupgrade", True):
                noupgrade = False
            if data.get("bugurl"):
                bugurl = data.get("bugurl")
            if not data.get("nomacboot", True):
                nomacboot = False
            if "rootfs_size" in data:
                rootfs_size = data.get("rootfs_size")
            add_template.extend(data.get("add_template", []))
            add_arch_template.extend(data.get("add_arch_template", []))
            add_template_var.extend(data.get("add_template_var", []))
            add_arch_template_var.extend(data.get("add_arch_template_var", []))
            dracut_args.extend(data.get("dracut_args", []))
            skip_branding = data.get("skip_branding", False)
            configuration_file_source = data.get("configuration_file")
            squashfs_only = data.get("squashfs_only", False)
            if "version" in data:
                version = data["version"]
        output_dir = os.path.join(output_dir, variant.uid)
        output_topdir = output_dir

        # The paths module will modify the filename (by inserting arch). But we
        # only care about the directory anyway.
        log_dir = _get_log_dir(self.compose, variant, arch)
        # Place the lorax.conf as specified by
        # the configuration_file parameter of lorax_options to the log directory.
        if configuration_file_source:
            configuration_file_destination = os.path.join(log_dir, "lorax.conf")
            # Obtain lorax.conf for the buildInstall phase
            get_file(
                configuration_file_source,
                configuration_file_destination,
                compose=self.compose,
            )
            configuration_file = configuration_file_destination

        repos = repo_baseurl[:]
        repos.extend(
            get_arch_variant_data(
                self.compose.conf, "lorax_extra_sources", arch, variant
            )
        )
        if self.compose.has_comps:
            comps_repo = self.compose.paths.work.comps_repo(arch, variant)
            if final_output_dir != output_dir:
                comps_repo = translate_path(self.compose, comps_repo)
            repos.append(comps_repo)

        if self.lorax_use_koji_plugin:
            return {
                "product": self.compose.conf["release_name"],
                "version": version,
                "release": version,
                "sources": force_list(repos),
                "variant": variant.uid,
                "installpkgs": variant.buildinstallpackages,
                "isfinal": self.compose.supported,
                "buildarch": buildarch,
                "volid": volid,
                "nomacboot": nomacboot,
                "bugurl": bugurl,
                "add-template": add_template,
                "add-arch-template": add_arch_template,
                "add-template-var": add_template_var,
                "add-arch-template-var": add_arch_template_var,
                "noupgrade": noupgrade,
                "rootfs-size": rootfs_size,
                "dracut-args": dracut_args,
                "skip_branding": skip_branding,
                "outputdir": output_dir,
                "squashfs_only": squashfs_only,
                "configuration_file": configuration_file,
            }
        else:
            # If the buildinstall_topdir is set, it means Koji is used for
            # buildinstall phase and the filesystem with Koji is read-only.
            # In that case, we have to write logs to buildinstall_topdir and
            # later copy them back to our local log directory.
            if self.compose.conf.get("buildinstall_topdir", None):
                output_dir = os.path.join(output_dir, "results")

            lorax = LoraxWrapper()
            lorax_cmd = lorax.get_lorax_cmd(
                self.compose.conf["release_name"],
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
                log_dir=log_dir,
                dracut_args=dracut_args,
                skip_branding=skip_branding,
                squashfs_only=squashfs_only,
                configuration_file=configuration_file,
            )
            return "rm -rf %s && %s" % (
                shlex_quote(output_topdir),
                " ".join([shlex_quote(x) for x in lorax_cmd]),
            )

    def get_repos(self, arch):
        repos = []
        for pkgset in self.pkgset_phase.package_sets:
            repos.append(pkgset.paths[arch])
        return repos

    def run(self):
        lorax = LoraxWrapper()
        product = self.compose.conf["release_name"]
        version = self.compose.conf["release_version"]
        release = self.compose.conf["release_version"]
        disc_type = self.compose.conf["disc_types"].get("dvd", "dvd")

        # Prepare kickstart file for final images.
        self.pool.kickstart_file = get_kickstart_file(self.compose)

        for arch in self.compose.get_arches():
            commands = []

            output_dir = self.compose.paths.work.buildinstall_dir(
                arch, allow_topdir_override=True
            )
            final_output_dir = self.compose.paths.work.buildinstall_dir(
                arch, allow_topdir_override=False
            )
            makedirs(final_output_dir)
            repo_baseurls = self.get_repos(arch)
            if final_output_dir != output_dir:
                repo_baseurls = [translate_path(self.compose, r) for r in repo_baseurls]

            if self.buildinstall_method == "lorax":
                buildarch = get_valid_arches(arch)[0]
                for variant in self.compose.get_variants(arch=arch, types=["variant"]):
                    if variant.is_empty:
                        continue

                    skip = get_arch_variant_data(
                        self.compose.conf, "buildinstall_skip", arch, variant
                    )
                    if skip == [True]:
                        self.compose.log_info(
                            "Skipping buildinstall for %s.%s due to config option"
                            % (variant, arch)
                        )
                        continue

                    volid = get_volid(
                        self.compose, arch, variant=variant, disc_type=disc_type
                    )
                    commands.append(
                        (
                            variant,
                            self._get_lorax_cmd(
                                repo_baseurls,
                                output_dir,
                                variant,
                                arch,
                                buildarch,
                                volid,
                                final_output_dir,
                            ),
                        )
                    )
            elif self.buildinstall_method == "buildinstall":
                volid = get_volid(self.compose, arch, disc_type=disc_type)
                commands.append(
                    (
                        None,
                        lorax.get_buildinstall_cmd(
                            product,
                            version,
                            release,
                            repo_baseurls,
                            output_dir,
                            is_final=self.compose.supported,
                            buildarch=arch,
                            volid=volid,
                        ),
                    )
                )
            else:
                raise ValueError(
                    "Unsupported buildinstall method: %s" % self.buildinstall_method
                )

            for (variant, cmd) in commands:
                self.pool.add(BuildinstallThread(self.pool))
                self.pool.queue_put(
                    (self.compose, arch, variant, cmd, self.pkgset_phase)
                )

        self.pool.start()

    def succeeded(self, variant, arch):
        # If the phase is skipped, we can treat it as successful. Either there
        # will be no output, or it's a debug run of compose where anything can
        # happen.
        return (
            super(BuildinstallPhase, self).skip()
            or (variant.uid if self.used_lorax else None, arch)
            in self.pool.finished_tasks
        )

    def reused(self, variant, arch):
        """
        Check if buildinstall phase reused previous results for given variant
        and arch. If the phase is skipped, the results will be considered
        reused as well.
        """
        return (
            super(BuildinstallPhase, self).skip()
            or (variant.uid if self.used_lorax else None, arch)
            in self.pool.reused_tasks
        )


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
    get_file_from_scm(scm_dict, tmp_dir, compose=compose)
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


def tweak_configs(path, volid, ks_file, configs=BOOT_CONFIGS, logger=None):
    volid_escaped = volid.replace(" ", r"\x20").replace("\\", "\\\\")
    volid_escaped_2 = volid_escaped.replace("\\", "\\\\")
    found_configs = []
    for config in configs:
        config_path = os.path.join(path, config)
        if not os.path.exists(config_path):
            continue
        found_configs.append(config)

        with open(config_path, "r") as f:
            data = original_data = f.read()
        os.unlink(config_path)  # break hadlink by removing file writing a new one

        # double-escape volid in yaboot.conf
        new_volid = volid_escaped_2 if "yaboot" in config else volid_escaped

        ks = (" inst.ks=hd:LABEL=%s:/ks.cfg" % new_volid) if ks_file else ""

        # pre-f18
        data = re.sub(r":CDLABEL=[^ \n]*", r":CDLABEL=%s%s" % (new_volid, ks), data)
        # f18+
        data = re.sub(r":LABEL=[^ \n]*", r":LABEL=%s%s" % (new_volid, ks), data)
        data = re.sub(r"(search .* -l) '[^'\n]*'", r"\1 '%s'" % volid, data)

        with open(config_path, "w") as f:
            f.write(data)

        if logger and data != original_data:
            logger.info("Boot config %s changed" % config_path)

    return found_configs


# HACK: this is a hack!
# * it's quite trivial to replace volids
# * it's not easy to replace menu titles
# * we probably need to get this into lorax
def tweak_buildinstall(
    compose, src, dst, arch, variant, label, volid, kickstart_file=None
):
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
        shlex_quote(src),
        shlex_quote(tmp_dir),
    )
    run(cmd)

    found_configs = tweak_configs(
        tmp_dir, volid, kickstart_file, logger=compose._logger
    )
    if kickstart_file and found_configs:
        shutil.copy2(kickstart_file, os.path.join(dst, "ks.cfg"))

    images = [
        os.path.join(tmp_dir, "images", "efiboot.img"),
    ]
    for image in images:
        if not os.path.isfile(image):
            continue

        with iso.mount(
            image,
            logger=compose._logger,
            use_guestmount=compose.conf.get("buildinstall_use_guestmount"),
        ) as mount_tmp_dir:
            for config in BOOT_CONFIGS:
                config_path = os.path.join(tmp_dir, config)
                config_in_image = os.path.join(mount_tmp_dir, config)

                if os.path.isfile(config_in_image):
                    cmd = [
                        "cp",
                        "-v",
                        "--remove-destination",
                        config_path,
                        config_in_image,
                    ]
                    run(cmd)

    # HACK: make buildinstall files world readable
    run("chmod -R a+rX %s" % shlex_quote(tmp_dir))

    # copy temp to dst
    cmd = "cp -dRv --preserve=mode,links,timestamps --remove-destination %s/* %s/" % (
        shlex_quote(tmp_dir),
        shlex_quote(dst),
    )
    run(cmd)

    shutil.rmtree(tmp_dir)


def link_boot_iso(compose, arch, variant, can_fail):
    if arch == "src":
        return

    disc_type = compose.conf["disc_types"].get("boot", "boot")

    symlink_isos_to = compose.conf.get("symlink_isos_to")
    os_tree = compose.paths.compose.os_tree(arch, variant)
    # TODO: find in treeinfo?
    boot_iso_path = os.path.join(os_tree, "images", "boot.iso")
    if not os.path.isfile(boot_iso_path):
        return

    msg = "Linking boot.iso (arch: %s, variant: %s)" % (arch, variant)
    filename = compose.get_image_name(
        arch, variant, disc_type=disc_type, disc_num=None, suffix=".iso"
    )
    new_boot_iso_path = compose.paths.compose.iso_path(
        arch, variant, filename, symlink_to=symlink_isos_to
    )
    new_boot_iso_relative_path = compose.paths.compose.iso_path(
        arch, variant, filename, relative=True
    )
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
    setattr(img, "can_fail", can_fail)
    setattr(img, "deliverable", "buildinstall")
    try:
        img.volume_id = iso.get_volume_id(new_boot_iso_path)
    except RuntimeError:
        pass
    compose.im.add(variant.uid, arch, img)
    compose.log_info("[DONE ] %s" % msg)


class BuildinstallThread(WorkerThread):
    def process(self, item, num):
        # The variant is None unless lorax is used as buildinstall method.
        compose, arch, variant, cmd, pkgset_phase = item
        can_fail = compose.can_fail(variant, arch, "buildinstall")
        with failable(compose, can_fail, variant, arch, "buildinstall"):
            try:
                self.worker(compose, arch, variant, cmd, pkgset_phase, num)
            except RuntimeError:
                self._print_depsolve_error(compose, arch, variant)
                raise

    def _print_depsolve_error(self, compose, arch, variant):
        try:
            log_file = os.path.join(_get_log_dir(compose, variant, arch), "pylorax.log")
            with open(log_file) as f:
                matched = False
                for line in f:
                    if re.match("Dependency check failed", line):
                        matched = True
                    if matched:
                        compose.log_error(line.rstrip())
        except Exception:
            pass

    def _generate_buildinstall_metadata(
        self, compose, arch, variant, cmd, buildroot_rpms, pkgset_phase
    ):
        """
        Generate buildinstall.metadata dict.

        :param Compose compose: Current compose.
        :param str arch: Current architecture.
        :param Variant variant: Compose variant.
        :param list cmd: List of command line arguments passed to buildinstall task.
        :param list buildroot_rpms: List of NVRAs of all RPMs installed in the
            buildinstall task's buildroot.
        :param PkgsetPhase pkgset_phase: Package set phase instance.
        :return: The buildinstall.metadata dict.
        """
        # Load the list of packages installed in the boot.iso.
        # The list of installed packages is logged by Lorax in the "pkglists"
        # directory. There is one file for each installed RPM and the name
        # of the file is the name of the RPM.
        # We need to resolve the name of each RPM back to its NVRA.
        installed_rpms = []
        log_fname = "buildinstall-%s-logs/dummy" % variant.uid
        log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname, False))
        pkglists_dir = os.path.join(log_dir, "pkglists")
        if os.path.exists(pkglists_dir):
            for pkg_name in os.listdir(pkglists_dir):
                for pkgset in pkgset_phase.package_sets:
                    global_pkgset = pkgset["global"]
                    # We actually do not care from which package_set the RPM
                    # came from or if there are multiple versions/release of
                    # the single RPM in more packages sets. We simply include
                    # all RPMs with this name in the metadata.
                    # Later when deciding if the buildinstall phase results
                    # can be reused, we check that all the RPMs with this name
                    # are still the same in old/new compose.
                    for rpm_path, rpm_obj in global_pkgset.file_cache.items():
                        if rpm_obj.name == pkg_name:
                            installed_rpms.append(rpm_path)

        # Store the metadata in `buildinstall.metadata`.
        metadata = {
            "cmd": cmd,
            "buildroot_rpms": sorted(buildroot_rpms),
            "installed_rpms": sorted(installed_rpms),
        }
        return metadata

    def _write_buildinstall_metadata(
        self, compose, arch, variant, cmd, buildroot_rpms, pkgset_phase
    ):
        """
        Write buildinstall.metadata file containing all the information about
        buildinstall phase input and environment.

        This file is later used to decide whether old buildinstall results can
        be reused instead of generating them again.

        :param Compose compose: Current compose.
        :param str arch: Current architecture.
        :param Variant variant: Compose variant.
        :param list cmd: List of command line arguments passed to buildinstall task.
        :param list buildroot_rpms: List of NVRAs of all RPMs installed in the
            buildinstall task's buildroot.
        :param PkgsetPhase pkgset_phase: Package set phase instance.
        """
        # Generate the list of `*-RPMs` log file.
        log_filename = ("buildinstall-%s" % variant.uid) if variant else "buildinstall"
        log_file = compose.paths.log.log_file(arch, log_filename + "-RPMs")
        with open(log_file, "w") as f:
            f.write("\n".join(buildroot_rpms))

        # Write buildinstall.metadata only if particular variant is defined.
        # The `variant` is `None` only if old "buildinstall" method is used.
        if not variant:
            return

        metadata = self._generate_buildinstall_metadata(
            compose, arch, variant, cmd, buildroot_rpms, pkgset_phase
        )

        log_fname = "buildinstall-%s-logs/dummy" % variant.uid
        log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname))
        metadata_path = os.path.join(log_dir, "buildinstall.metadata")
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)

    def _load_old_buildinstall_metadata(self, compose, arch, variant):
        """
        Helper method to load "buildinstall.metadata" from old compose.

        :param Compose compose: Current compose.
        :param str arch: Current architecture.
        :param Variant variant: Compose variant.
        """
        if not variant:
            return None

        log_fname = "buildinstall-%s-logs/dummy" % variant.uid
        metadata = os.path.join(
            os.path.dirname(compose.paths.log.log_file(arch, log_fname)),
            "buildinstall.metadata",
        )
        old_metadata = compose.paths.old_compose_path(metadata)
        if not old_metadata:
            return None

        compose.log_info("Loading old BUILDINSTALL phase metadata: %s", old_metadata)
        try:
            with open(old_metadata, "rb") as f:
                old_result = pickle.load(f)
                return old_result
        except Exception as e:
            compose.log_debug(
                "Failed to load old BUILDINSTALL phase metadata %s : %s"
                % (old_metadata, str(e))
            )
            return None

    def _reuse_old_buildinstall_result(self, compose, arch, variant, cmd, pkgset_phase):
        """
        Try to reuse old buildinstall results.

        :param Compose compose: Current compose.
        :param str arch: Current architecture.
        :param Variant variant: Compose variant.
        :param list cmd: List of command line arguments passed to buildinstall task.
        :param list buildroot_rpms: List of NVRAs of all RPMs installed in the
            buildinstall task's buildroot.
        :param PkgsetPhase pkgset_phase: Package set phase instance.
        :return: True if old buildinstall phase results have been reused.
        """
        log_msg = "Cannot reuse old BUILDINSTALL phase results - %s"

        if not compose.conf["buildinstall_allow_reuse"]:
            compose.log_info(log_msg % "reuse of old buildinstall results is disabled.")
            return

        # Load the old buildinstall.metadata.
        old_metadata = self._load_old_buildinstall_metadata(compose, arch, variant)
        if old_metadata is None:
            compose.log_info(log_msg % "no old BUILDINSTALL metadata.")
            return

        # For now try to reuse only if pungi_buildinstall plugin is used.
        # This is the easiest approach, because we later need to filter out
        # some parts of `cmd` and for pungi_buildinstall, the `cmd` is a dict
        # which makes this easy.
        if not isinstance(old_metadata["cmd"], dict) or not isinstance(cmd, dict):
            compose.log_info(log_msg % "pungi_buildinstall plugin is not used.")
            return

        # Filter out "outputdir" and "sources" because they change every time.
        # The "sources" are not important, because we check the buildinstall
        # input on RPM level.
        cmd_copy = copy(cmd)
        for key in ["outputdir", "sources"]:
            del cmd_copy[key]
            del old_metadata["cmd"][key]

        # Do not reuse if command line arguments are not the same.
        if old_metadata["cmd"] != cmd_copy:
            compose.log_info(log_msg % "lorax command line arguments differ.")
            return

        # Check that the RPMs installed in the old boot.iso exists in the very
        # same versions/releases in this compose.
        for rpm_path in old_metadata["installed_rpms"]:
            found = False
            for pkgset in pkgset_phase.package_sets:
                global_pkgset = pkgset["global"]
                if rpm_path in global_pkgset.file_cache:
                    found = True
                    break
            if not found:
                compose.log_info(
                    log_msg % "RPM %s does not exist in new compose." % rpm_path
                )
                return

        # Ask Koji for all the RPMs in the `runroot_tag` and check that
        # those installed in the old buildinstall buildroot are still in the
        # very same versions/releases.
        koji_wrapper = kojiwrapper.KojiWrapper(compose)
        rpms = koji_wrapper.koji_proxy.listTaggedRPMS(
            compose.conf.get("runroot_tag"), inherit=True, latest=True
        )[0]
        rpm_nvras = set()
        for rpm in rpms:
            rpm_nvras.add(kobo.rpmlib.make_nvra(rpm, add_rpm=False, force_epoch=False))
        for old_nvra in old_metadata["buildroot_rpms"]:
            if old_nvra not in rpm_nvras:
                compose.log_info(
                    log_msg % "RPM %s does not exist in new buildroot." % old_nvra
                )
                return

        # We can reuse the old buildinstall results!
        compose.log_info("Reusing old BUILDINSTALL phase output")

        # Copy old buildinstall output to this this compose.
        final_output_dir = compose.paths.work.buildinstall_dir(arch, variant=variant)
        old_final_output_dir = compose.paths.old_compose_path(final_output_dir)
        copy_all(old_final_output_dir, final_output_dir)

        # Copy old buildinstall logs to this compose.
        log_fname = "buildinstall-%s-logs/dummy" % variant.uid
        final_log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname))
        old_final_log_dir = compose.paths.old_compose_path(final_log_dir)
        if not os.path.exists(final_log_dir):
            makedirs(final_log_dir)
        copy_all(old_final_log_dir, final_log_dir)

        # Write the buildinstall metadata so next compose can reuse this compose.
        self._write_buildinstall_metadata(
            compose, arch, variant, cmd, old_metadata["buildroot_rpms"], pkgset_phase
        )

        return True

    def worker(self, compose, arch, variant, cmd, pkgset_phase, num):
        buildinstall_method = compose.conf["buildinstall_method"]
        lorax_use_koji_plugin = compose.conf["lorax_use_koji_plugin"]
        log_filename = ("buildinstall-%s" % variant.uid) if variant else "buildinstall"
        log_file = compose.paths.log.log_file(arch, log_filename)

        msg = "Running buildinstall for arch %s, variant %s" % (arch, variant)

        output_dir = compose.paths.work.buildinstall_dir(
            arch, allow_topdir_override=True, variant=variant
        )
        final_output_dir = compose.paths.work.buildinstall_dir(arch, variant=variant)

        if (
            os.path.isdir(output_dir)
            and os.listdir(output_dir)
            or os.path.isdir(final_output_dir)
            and os.listdir(final_output_dir)
        ):
            # output dir is *not* empty -> SKIP
            self.pool.log_warning(
                "[SKIP ] Buildinstall for arch %s, variant %s" % (arch, variant)
            )
            return

        self.pool.log_info("[BEGIN] %s" % msg)

        # Get list of packages which are needed in runroot.
        packages = []
        chown_paths = [output_dir]
        if buildinstall_method == "lorax":
            packages += ["lorax"]
            chown_paths.append(_get_log_dir(compose, variant, arch))
        elif buildinstall_method == "buildinstall":
            packages += ["anaconda"]
        packages += get_arch_variant_data(
            compose.conf, "buildinstall_packages", arch, variant
        )
        if self._reuse_old_buildinstall_result(
            compose, arch, variant, cmd, pkgset_phase
        ):
            self.copy_files(compose, variant, arch)
            self.pool.finished_tasks.add((variant.uid if variant else None, arch))
            self.pool.reused_tasks.add((variant.uid if variant else None, arch))
            self.pool.log_info("[DONE ] %s" % msg)
            return

        # This should avoid a possible race condition with multiple processes
        # trying to get a kerberos ticket at the same time.
        # Kerberos authentication failed:
        #   Permission denied in replay cache code (-1765328215)
        time.sleep(num * 3)

        # Start the runroot task.
        runroot = Runroot(compose, phase="buildinstall")
        if buildinstall_method == "lorax" and lorax_use_koji_plugin:
            runroot.run_pungi_buildinstall(
                cmd,
                log_file=log_file,
                arch=arch,
                packages=packages,
                mounts=[compose.topdir],
                weight=compose.conf["runroot_weights"].get("buildinstall"),
            )
        else:
            try:
                lorax_log_dir = _get_log_dir(compose, variant, arch)
            except Exception:
                lorax_log_dir = None
            runroot.run(
                cmd,
                log_file=log_file,
                arch=arch,
                packages=packages,
                mounts=[compose.topdir],
                weight=compose.conf["runroot_weights"].get("buildinstall"),
                chown_paths=chown_paths,
                log_dir=lorax_log_dir,
            )

        if final_output_dir != output_dir:
            if not os.path.exists(final_output_dir):
                makedirs(final_output_dir)
            results_dir = os.path.join(output_dir, "results")
            copy_all(results_dir, final_output_dir)

            # Get the log_dir into which we should copy the resulting log files.
            log_fname = "buildinstall-%s-logs/dummy" % variant.uid
            final_log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname))
            if not os.path.exists(final_log_dir):
                makedirs(final_log_dir)
            log_dir = os.path.join(output_dir, "logs")
            copy_all(log_dir, final_log_dir)
        elif lorax_use_koji_plugin:
            # If Koji pungi-buildinstall is used, then the buildinstall results are
            # not stored directly in `output_dir` dir, but in "results" and "logs"
            # subdirectories. We need to move them to final_output_dir.
            results_dir = os.path.join(output_dir, "results")
            move_all(results_dir, final_output_dir, rm_src_dir=True)

            # Get the log_dir into which we should copy the resulting log files.
            log_fname = "buildinstall-%s-logs/dummy" % variant.uid
            final_log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_fname))
            if not os.path.exists(final_log_dir):
                makedirs(final_log_dir)
            log_dir = os.path.join(output_dir, "logs")
            move_all(log_dir, final_log_dir, rm_src_dir=True)

        rpms = runroot.get_buildroot_rpms()
        self._write_buildinstall_metadata(
            compose, arch, variant, cmd, rpms, pkgset_phase
        )

        self.copy_files(compose, variant, arch)

        self.pool.finished_tasks.add((variant.uid if variant else None, arch))

        self.pool.log_info("[DONE ] %s" % msg)

    def copy_files(self, compose, variant, arch):
        disc_type = compose.conf["disc_types"].get("dvd", "dvd")

        buildinstall_dir = compose.paths.work.buildinstall_dir(arch)

        # Lorax runs per-variant, so we need to tweak the source path
        # to include variant.
        if variant:
            buildinstall_dir = os.path.join(buildinstall_dir, variant.uid)

        # Find all relevant variants if lorax is not used.
        variants = (
            [variant]
            if variant
            else compose.get_variants(arch=arch, types=["self", "variant"])
        )
        for var in variants:
            os_tree = compose.paths.compose.os_tree(arch, var)
            # TODO: label is not used
            label = ""
            volid = get_volid(compose, arch, var, disc_type=disc_type)
            can_fail = compose.can_fail(var, arch, "buildinstall")
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
    log_filename = "buildinstall-%s-logs/dummy" % variant.uid
    log_dir = os.path.dirname(compose.paths.log.log_file(arch, log_filename))
    makedirs(log_dir)
    return log_dir
