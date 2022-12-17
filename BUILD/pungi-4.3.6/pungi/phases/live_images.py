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
import sys
import time
import shutil

from kobo.threads import ThreadPool, WorkerThread
from kobo.shortcuts import run, save_to_file, force_list
from productmd.images import Image
from six.moves import shlex_quote

from pungi.wrappers.kojiwrapper import KojiWrapper
from pungi.wrappers import iso
from pungi.phases import base
from pungi.util import makedirs, get_mtime, get_file_size, failable
from pungi.util import get_repo_urls


# HACK: define cmp in python3
if sys.version_info[0] == 3:

    def cmp(a, b):
        return (a > b) - (a < b)


class LiveImagesPhase(
    base.PhaseLoggerMixin, base.ImageConfigMixin, base.ConfigGuardedPhase
):
    name = "live_images"

    def __init__(self, compose):
        super(LiveImagesPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def _get_repos(self, arch, variant, data):
        repos = []
        if not variant.is_empty:
            repos.append(variant.uid)
        repos.extend(force_list(data.get("repo", [])))
        return get_repo_urls(self.compose, repos, arch=arch)

    def run(self):
        symlink_isos_to = self.compose.conf.get("symlink_isos_to")
        commands = []

        for variant in self.compose.all_variants.values():
            for arch in variant.arches + ["src"]:
                for data in self.get_config_block(variant, arch):
                    subvariant = data.get("subvariant", variant.uid)
                    type = data.get("type", "live")

                    if type == "live":
                        dest_dir = self.compose.paths.compose.iso_dir(
                            arch, variant, symlink_to=symlink_isos_to
                        )
                    elif type == "appliance":
                        dest_dir = self.compose.paths.compose.image_dir(
                            variant, symlink_to=symlink_isos_to
                        )
                        dest_dir = dest_dir % {"arch": arch}
                        makedirs(dest_dir)
                    else:
                        raise RuntimeError("Unknown live image type %s" % type)
                    if not dest_dir:
                        continue

                    cmd = {
                        "name": data.get("name"),
                        "version": self.get_version(data),
                        "release": self.get_release(data),
                        "dest_dir": dest_dir,
                        "build_arch": arch,
                        "ks_file": data["kickstart"],
                        "ksurl": self.get_ksurl(data),
                        # Used for images wrapped in RPM
                        "specfile": data.get("specfile", None),
                        # Scratch (only taken in consideration if specfile
                        # specified) For images wrapped in rpm is scratch
                        # disabled by default For other images is scratch
                        # always on
                        "scratch": data.get("scratch", False),
                        "sign": False,
                        "type": type,
                        "label": "",  # currently not used
                        "subvariant": subvariant,
                        "failable_arches": data.get("failable", []),
                        # First see if live_target is specified, then fall back
                        # to regular setup of local, phase and global setting.
                        "target": self.compose.conf.get("live_target")
                        or self.get_config(data, "target"),
                    }

                    cmd["repos"] = self._get_repos(arch, variant, data)

                    # Signing of the rpm wrapped image
                    if not cmd["scratch"] and data.get("sign"):
                        cmd["sign"] = True

                    cmd["filename"] = self._get_file_name(
                        arch, variant, cmd["name"], cmd["version"]
                    )

                    commands.append((cmd, variant, arch))

        for (cmd, variant, arch) in commands:
            self.pool.add(CreateLiveImageThread(self.pool))
            self.pool.queue_put((self.compose, cmd, variant, arch))

        self.pool.start()

    def _get_file_name(self, arch, variant, name=None, version=None):
        if self.compose.conf["live_images_no_rename"]:
            return None

        disc_type = self.compose.conf["disc_types"].get("live", "live")

        format = (
            "%(compose_id)s-%(variant)s-%(arch)s-%(disc_type)s%(disc_num)s%(suffix)s"
        )
        # Custom name (prefix)
        if name:
            custom_iso_name = name
            if version:
                custom_iso_name += "-%s" % version
            format = (
                custom_iso_name
                + "-%(variant)s-%(arch)s-%(disc_type)s%(disc_num)s%(suffix)s"
            )

        # XXX: hardcoded disc_num
        return self.compose.get_image_name(
            arch, variant, disc_type=disc_type, disc_num=None, format=format
        )


class CreateLiveImageThread(WorkerThread):
    EXTS = (".iso", ".raw.xz")

    def process(self, item, num):
        compose, cmd, variant, arch = item
        self.failable_arches = cmd.get("failable_arches", [])
        self.can_fail = bool(self.failable_arches)
        with failable(
            compose,
            self.can_fail,
            variant,
            arch,
            "live",
            cmd.get("subvariant"),
            logger=self.pool._logger,
        ):
            self.worker(compose, cmd, variant, arch, num)

    def worker(self, compose, cmd, variant, arch, num):
        self.basename = "%(name)s-%(version)s-%(release)s" % cmd
        log_file = compose.paths.log.log_file(arch, "liveimage-%s" % self.basename)

        subvariant = cmd.pop("subvariant")

        imgname = "%s-%s-%s-%s" % (
            compose.ci_base.release.short,
            subvariant,
            "Live" if cmd["type"] == "live" else "Disk",
            arch,
        )

        msg = "Creating ISO (arch: %s, variant: %s): %s" % (
            arch,
            variant,
            self.basename,
        )
        self.pool.log_info("[BEGIN] %s" % msg)

        koji_wrapper = KojiWrapper(compose)
        _, version = compose.compose_id.rsplit("-", 1)
        name = cmd["name"] or imgname
        version = cmd["version"] or version
        archive = False
        if cmd["specfile"] and not cmd["scratch"]:
            # Non scratch build are allowed only for rpm wrapped images
            archive = True
        koji_cmd = koji_wrapper.get_create_image_cmd(
            name,
            version,
            cmd["target"],
            cmd["build_arch"],
            cmd["ks_file"],
            cmd["repos"],
            image_type=cmd["type"],
            wait=True,
            archive=archive,
            specfile=cmd["specfile"],
            release=cmd["release"],
            ksurl=cmd["ksurl"],
        )

        # avoid race conditions?
        # Kerberos authentication failed:
        #   Permission denied in replay cache code (-1765328215)
        time.sleep(num * 3)

        output = koji_wrapper.run_blocking_cmd(koji_cmd, log_file=log_file)
        if output["retcode"] != 0:
            raise RuntimeError(
                "LiveImage task failed: %s. See %s for more details."
                % (output["task_id"], log_file)
            )

        # copy finished image to isos/
        image_path = [
            path
            for path in koji_wrapper.get_image_path(output["task_id"])
            if self._is_image(path)
        ]
        if len(image_path) != 1:
            raise RuntimeError(
                "Got %d images from task %d, expected 1."
                % (len(image_path), output["task_id"])
            )
        image_path = image_path[0]
        filename = cmd.get("filename") or os.path.basename(image_path)
        destination = os.path.join(cmd["dest_dir"], filename)
        shutil.copy2(image_path, destination)

        # copy finished rpm to isos/ (if rpm wrapped ISO was built)
        if cmd["specfile"]:
            rpm_paths = koji_wrapper.get_wrapped_rpm_path(output["task_id"])

            if cmd["sign"]:
                # Sign the rpm wrapped images and get their paths
                self.pool.log_info(
                    "Signing rpm wrapped images in task_id: %s (expected key ID: %s)"
                    % (output["task_id"], compose.conf.get("signing_key_id"))
                )
                signed_rpm_paths = self._sign_image(
                    koji_wrapper, compose, cmd, output["task_id"]
                )
                if signed_rpm_paths:
                    rpm_paths = signed_rpm_paths

            for rpm_path in rpm_paths:
                shutil.copy2(rpm_path, cmd["dest_dir"])

        if cmd["type"] == "live":
            # ISO manifest only makes sense for live images
            self._write_manifest(destination)

        self._add_to_images(
            compose,
            variant,
            subvariant,
            arch,
            cmd["type"],
            self._get_format(image_path),
            destination,
        )

        self.pool.log_info("[DONE ] %s (task id: %s)" % (msg, output["task_id"]))

    def _add_to_images(self, compose, variant, subvariant, arch, type, format, path):
        """Adds the image to images.json"""
        img = Image(compose.im)
        img.type = "raw-xz" if type == "appliance" else type
        img.format = format
        img.path = os.path.relpath(path, compose.paths.compose.topdir())
        img.mtime = get_mtime(path)
        img.size = get_file_size(path)
        img.arch = arch
        img.disc_number = 1  # We don't expect multiple disks
        img.disc_count = 1
        img.bootable = True
        img.subvariant = subvariant
        setattr(img, "can_fail", self.can_fail)
        setattr(img, "deliverable", "live")
        compose.im.add(variant=variant.uid, arch=arch, image=img)

    def _is_image(self, path):
        for ext in self.EXTS:
            if path.endswith(ext):
                return True
        return False

    def _get_format(self, path):
        """Get format based on extension."""
        for ext in self.EXTS:
            if path.endswith(ext):
                return ext[1:]
        raise RuntimeError("Getting format for unknown image %s" % path)

    def _write_manifest(self, iso_path):
        """Generate manifest for ISO at given path.

        :param iso_path: (str) absolute path to the ISO
        """
        dir, filename = os.path.split(iso_path)
        run("cd %s && %s" % (shlex_quote(dir), iso.get_manifest_cmd(filename)))

    def _sign_image(self, koji_wrapper, compose, cmd, koji_task_id):
        signing_key_id = compose.conf.get("signing_key_id")
        signing_command = compose.conf.get("signing_command")

        if not signing_key_id:
            self.pool.log_warning(
                "Signing is enabled but signing_key_id is not specified"
            )
            self.pool.log_warning("Signing skipped")
            return None
        if not signing_command:
            self.pool.log_warning(
                "Signing is enabled but signing_command is not specified"
            )
            self.pool.log_warning("Signing skipped")
            return None

        # Prepare signing log file
        signing_log_file = compose.paths.log.log_file(
            cmd["build_arch"], "live_images-signing-%s" % self.basename
        )

        # Sign the rpm wrapped images
        try:
            sign_builds_in_task(
                koji_wrapper,
                koji_task_id,
                signing_command,
                log_file=signing_log_file,
                signing_key_password=compose.conf.get("signing_key_password"),
            )
        except RuntimeError:
            self.pool.log_error(
                "Error while signing rpm wrapped images. See log: %s" % signing_log_file
            )
            raise

        # Get pats to the signed rpms
        signing_key_id = signing_key_id.lower()  # Koji uses lowercase in paths
        rpm_paths = koji_wrapper.get_signed_wrapped_rpms_paths(
            koji_task_id, signing_key_id
        )

        # Wait until files are available
        if wait_paths(rpm_paths, 60 * 15):
            # Files are ready
            return rpm_paths

        # Signed RPMs are not available
        self.pool.log_warning("Signed files are not available: %s" % rpm_paths)
        self.pool.log_warning("Unsigned files will be used")
        return None


def wait_paths(paths, timeout=60):
    started = time.time()
    remaining = paths[:]
    while True:
        for path in remaining[:]:
            if os.path.exists(path):
                remaining.remove(path)
        if not remaining:
            break
        time.sleep(1)
        if timeout >= 0 and (time.time() - started) > timeout:
            return False
    return True


def sign_builds_in_task(
    koji_wrapper, task_id, signing_command, log_file=None, signing_key_password=None
):
    # Get list of nvrs that should be signed
    nvrs = koji_wrapper.get_build_nvrs(task_id)
    if not nvrs:
        # No builds are available (scratch build, etc.?)
        return

    # Append builds to sign_cmd
    for nvr in nvrs:
        signing_command += " '%s'" % nvr

    # Log signing command before password is filled in it
    if log_file:
        save_to_file(log_file, signing_command, append=True)

    # Fill password into the signing command
    if signing_key_password:
        signing_command = signing_command % {
            "signing_key_password": signing_key_password
        }

    # Sign the builds
    run(signing_command, can_fail=False, show_cmd=False, logfile=log_file)
