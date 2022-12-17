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
import hashlib
import json

from kobo.shortcuts import force_list
from kobo.threads import ThreadPool, WorkerThread
import productmd.treeinfo
from productmd.extra_files import ExtraFiles

from pungi import createiso
from pungi import metadata
from pungi.phases.base import ConfigGuardedPhase, PhaseBase, PhaseLoggerMixin
from pungi.phases.createiso import (
    add_iso_to_metadata,
    copy_boot_images,
    run_createiso_command,
    load_and_tweak_treeinfo,
    compare_packages,
    OldFileLinker,
    get_iso_level_config,
)
from pungi.util import (
    failable,
    get_format_substs,
    get_variant_data,
    get_volid,
    read_json_file,
)
from pungi.wrappers import iso
from pungi.wrappers.scm import get_dir_from_scm, get_file_from_scm


class ExtraIsosPhase(PhaseLoggerMixin, ConfigGuardedPhase, PhaseBase):
    name = "extra_isos"

    def __init__(self, compose, buildinstall_phase):
        super(ExtraIsosPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.bi = buildinstall_phase

    def validate(self):
        for variant in self.compose.get_variants(types=["variant"]):
            for config in get_variant_data(self.compose.conf, self.name, variant):
                extra_arches = set(config.get("arches", [])) - set(variant.arches)
                if extra_arches:
                    self.compose.log_warning(
                        "Extra iso config for %s mentions non-existing arches: %s"
                        % (variant, ", ".join(sorted(extra_arches)))
                    )

    def run(self):
        commands = []

        for variant in self.compose.get_variants(types=["variant"]):
            for config in get_variant_data(self.compose.conf, self.name, variant):
                arches = set(variant.arches)
                if config.get("arches"):
                    arches &= set(config["arches"])
                if not config["skip_src"]:
                    arches.add("src")
                for arch in sorted(arches):
                    commands.append((config, variant, arch))

        for (config, variant, arch) in commands:
            self.pool.add(ExtraIsosThread(self.pool, self.bi))
            self.pool.queue_put((self.compose, config, variant, arch))

        self.pool.start()


class ExtraIsosThread(WorkerThread):
    def __init__(self, pool, buildinstall_phase):
        super(ExtraIsosThread, self).__init__(pool)
        self.bi = buildinstall_phase

    def process(self, item, num):
        self.num = num
        compose, config, variant, arch = item
        can_fail = arch in config.get("failable_arches", [])
        with failable(
            compose, can_fail, variant, arch, "extra_iso", logger=self.pool._logger
        ):
            self.worker(compose, config, variant, arch)

    def worker(self, compose, config, variant, arch):
        filename = get_filename(compose, variant, arch, config.get("filename"))
        volid = get_volume_id(compose, variant, arch, config.get("volid", []))
        iso_dir = compose.paths.compose.iso_dir(arch, variant)
        iso_path = os.path.join(iso_dir, filename)

        prepare_media_metadata(compose, variant, arch)

        msg = "Creating ISO (arch: %s, variant: %s): %s" % (arch, variant, filename)
        self.pool.log_info("[BEGIN] %s" % msg)

        get_extra_files(compose, variant, arch, config.get("extra_files", []))

        bootable = arch != "src" and bool(compose.conf.get("buildinstall_method"))

        graft_points = get_iso_contents(
            compose,
            variant,
            arch,
            config["include_variants"],
            filename,
            bootable=bootable,
            inherit_extra_files=config.get("inherit_extra_files", False),
        )

        opts = createiso.CreateIsoOpts(
            output_dir=iso_dir,
            iso_name=filename,
            volid=volid,
            graft_points=graft_points,
            arch=arch,
            supported=compose.supported,
            hfs_compat=compose.conf["iso_hfs_ppc64le_compatible"],
            use_xorrisofs=compose.conf.get("createiso_use_xorrisofs"),
            iso_level=get_iso_level_config(compose, variant, arch),
        )
        os_tree = compose.paths.compose.os_tree(arch, variant)
        if compose.conf["create_jigdo"]:
            jigdo_dir = compose.paths.compose.jigdo_dir(arch, variant)
            opts = opts._replace(jigdo_dir=jigdo_dir, os_tree=os_tree)

        if bootable:
            opts = opts._replace(
                buildinstall_method=compose.conf["buildinstall_method"],
                boot_iso=os.path.join(os_tree, "images", "boot.iso"),
            )

        # Check if it can be reused.
        hash = hashlib.sha256()
        hash.update(json.dumps(config, sort_keys=True).encode("utf-8"))
        config_hash = hash.hexdigest()

        if not self.try_reuse(compose, variant, arch, config_hash, opts):
            script_dir = compose.paths.work.tmp_dir(arch, variant)
            opts = opts._replace(script_dir=script_dir)
            script_file = os.path.join(script_dir, "extraiso-%s.sh" % filename)
            with open(script_file, "w") as f:
                createiso.write_script(opts, f)

            run_createiso_command(
                self.num,
                compose,
                bootable,
                arch,
                ["bash", script_file],
                [compose.topdir],
                log_file=compose.paths.log.log_file(
                    arch, "extraiso-%s" % os.path.basename(iso_path)
                ),
            )

        img = add_iso_to_metadata(
            compose,
            variant,
            arch,
            iso_path,
            bootable,
            additional_variants=config["include_variants"],
        )
        img._max_size = config.get("max_size")

        save_reuse_metadata(compose, variant, arch, config_hash, opts, iso_path)

        self.pool.log_info("[DONE ] %s" % msg)

    def try_reuse(self, compose, variant, arch, config_hash, opts):
        # Check explicit config
        if not compose.conf["extraiso_allow_reuse"]:
            return

        log_msg = "Cannot reuse ISO for %s.%s" % (variant, arch)

        if opts.buildinstall_method and not self.bi.reused(variant, arch):
            # If buildinstall phase was not reused for some reason, we can not
            # reuse any bootable image. If a package change caused rebuild of
            # boot.iso, we would catch it here too, but there could be a
            # configuration change in lorax template which would remain
            # undetected.
            self.pool.log_info("%s - boot configuration changed", log_msg)
            return False

        # Check old compose configuration: extra_files and product_ids can be
        # reflected on ISO.
        old_config = compose.load_old_compose_config()
        if not old_config:
            self.pool.log_info("%s - no config for old compose", log_msg)
            return False
        # Convert current configuration to JSON and back to encode it similarly
        # to the old one
        config = json.loads(json.dumps(compose.conf))
        for opt in compose.conf:
            # Skip a selection of options: these affect what packages can be
            # included, which we explicitly check later on.
            config_whitelist = set(
                [
                    "gather_lookaside_repos",
                    "pkgset_koji_builds",
                    "pkgset_koji_scratch_tasks",
                    "pkgset_koji_module_builds",
                ]
            )
            # Skip irrelevant options
            config_whitelist.update(["osbs", "osbuild"])
            if opt in config_whitelist:
                continue

            if old_config.get(opt) != config.get(opt):
                self.pool.log_info("%s - option %s differs", log_msg, opt)
                return False

        old_metadata = load_old_metadata(compose, variant, arch, config_hash)
        if not old_metadata:
            self.pool.log_info("%s - no old metadata found", log_msg)
            return False

        # Test if volume ID matches - volid can be generated dynamically based on
        # other values, and could change even if nothing else is different.
        if opts.volid != old_metadata["opts"]["volid"]:
            self.pool.log_info("%s - volume ID differs", log_msg)
            return False

        # Compare packages on the ISO.
        if compare_packages(
            old_metadata["opts"]["graft_points"],
            opts.graft_points,
        ):
            self.pool.log_info("%s - packages differ", log_msg)
            return False

        try:
            self.perform_reuse(
                compose,
                variant,
                arch,
                opts,
                old_metadata["opts"]["output_dir"],
                old_metadata["opts"]["iso_name"],
            )
            return True
        except Exception as exc:
            self.pool.log_error(
                "Error while reusing ISO for %s.%s: %s", variant, arch, exc
            )
            compose.traceback("extraiso-reuse-%s-%s-%s" % (variant, arch, config_hash))
            return False

    def perform_reuse(self, compose, variant, arch, opts, old_iso_dir, old_file_name):
        """
        Copy all related files from old compose to the new one. As a last step
        add the new image to metadata.
        """
        linker = OldFileLinker(self.pool._logger)
        old_iso_path = os.path.join(old_iso_dir, old_file_name)
        iso_path = os.path.join(opts.output_dir, opts.iso_name)
        try:
            # Hardlink ISO and manifest
            for suffix in ("", ".manifest"):
                linker.link(old_iso_path + suffix, iso_path + suffix)
            # Copy log files
            # The log file name includes filename of the image, so we need to
            # find old file with the old name, and rename it to the new name.
            log_file = compose.paths.log.log_file(arch, "extraiso-%s" % opts.iso_name)
            old_log_file = compose.paths.old_compose_path(
                compose.paths.log.log_file(arch, "extraiso-%s" % old_file_name)
            )
            linker.link(old_log_file, log_file)
            # Copy jigdo files
            if opts.jigdo_dir:
                old_jigdo_dir = compose.paths.old_compose_path(opts.jigdo_dir)
                for suffix in (".template", ".jigdo"):
                    linker.link(
                        os.path.join(old_jigdo_dir, old_file_name) + suffix,
                        os.path.join(opts.jigdo_dir, opts.iso_name) + suffix,
                    )
        except Exception:
            # A problem happened while linking some file, let's clean up
            # everything.
            linker.abort()
            raise


def save_reuse_metadata(compose, variant, arch, config_hash, opts, iso_path):
    """
    Save metadata for possible reuse of this image. The file name is determined
    from the hash of a configuration snippet for this image. Any change in that
    configuration in next compose will change the hash and thus reuse will be
    blocked.
    """
    metadata = {"opts": opts._asdict()}
    metadata_path = compose.paths.log.log_file(
        arch,
        "extraiso-reuse-%s-%s-%s" % (variant.uid, arch, config_hash),
        ext="json",
    )
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)


def load_old_metadata(compose, variant, arch, config_hash):
    metadata_path = compose.paths.log.log_file(
        arch,
        "extraiso-reuse-%s-%s-%s" % (variant.uid, arch, config_hash),
        ext="json",
    )
    old_path = compose.paths.old_compose_path(metadata_path)
    try:
        return read_json_file(old_path)
    except Exception:
        return None


def get_extra_files(compose, variant, arch, extra_files):
    """Clone the configured files into a directory from where they can be
    included in the ISO.
    """
    extra_files_dir = compose.paths.work.extra_iso_extra_files_dir(arch, variant)
    filelist = []
    for scm_dict in extra_files:
        getter = get_file_from_scm if "file" in scm_dict else get_dir_from_scm
        target = scm_dict.get("target", "").lstrip("/")
        target_path = os.path.join(extra_files_dir, target).rstrip("/")
        filelist.extend(
            os.path.join(target, f)
            for f in getter(scm_dict, target_path, compose=compose)
        )

    if filelist:
        metadata.populate_extra_files_metadata(
            ExtraFiles(),
            variant,
            arch,
            extra_files_dir,
            filelist,
            compose.conf["media_checksums"],
        )


def get_iso_contents(
    compose, variant, arch, include_variants, filename, bootable, inherit_extra_files
):
    """Find all files that should be on the ISO. For bootable image we start
    with the boot configuration. Then for each variant we add packages,
    repodata and extra files. Finally we add top-level extra files.
    """
    iso_dir = compose.paths.work.iso_dir(arch, filename)

    files = {}
    if bootable:
        buildinstall_dir = compose.paths.work.buildinstall_dir(arch, create_dir=False)
        if compose.conf["buildinstall_method"] == "lorax":
            buildinstall_dir = os.path.join(buildinstall_dir, variant.uid)

        copy_boot_images(buildinstall_dir, iso_dir)
        files = iso.get_graft_points(
            compose.paths.compose.topdir(), [buildinstall_dir, iso_dir]
        )

        # We need to point efiboot.img to compose/ tree, because it was
        # modified in buildinstall phase and the file in work/ has different
        # checksum to what is in the .treeinfo.
        if "images/efiboot.img" in files:
            files["images/efiboot.img"] = os.path.join(
                compose.paths.compose.os_tree(arch, variant), "images/efiboot.img"
            )

    variants = [variant.uid] + include_variants
    for variant_uid in variants:
        var = compose.all_variants[variant_uid]

        # Get packages...
        package_dir = compose.paths.compose.packages(arch, var)
        for k, v in iso.get_graft_points(
            compose.paths.compose.topdir(), [package_dir]
        ).items():
            files[os.path.join(var.uid, "Packages", k)] = v

        # Get repodata...
        tree_dir = compose.paths.compose.repository(arch, var)
        repo_dir = os.path.join(tree_dir, "repodata")
        for k, v in iso.get_graft_points(
            compose.paths.compose.topdir(), [repo_dir]
        ).items():
            files[os.path.join(var.uid, "repodata", k)] = v

        if inherit_extra_files:
            # Get extra files...
            extra_files_dir = compose.paths.work.extra_files_dir(arch, var)
            for k, v in iso.get_graft_points(
                compose.paths.compose.topdir(), [extra_files_dir]
            ).items():
                files[os.path.join(var.uid, k)] = v

    extra_files_dir = compose.paths.work.extra_iso_extra_files_dir(arch, variant)

    original_treeinfo = os.path.join(
        compose.paths.compose.os_tree(arch=arch, variant=variant), ".treeinfo"
    )
    tweak_treeinfo(
        compose,
        include_variants,
        original_treeinfo,
        os.path.join(extra_files_dir, ".treeinfo"),
    )

    # Add extra files specific for the ISO
    files.update(
        iso.get_graft_points(compose.paths.compose.topdir(), [extra_files_dir])
    )

    gp = "%s-graft-points" % iso_dir
    iso.write_graft_points(gp, files, exclude=["*/lost+found", "*/boot.iso"])
    return gp


def tweak_treeinfo(compose, include_variants, source_file, dest_file):
    ti = load_and_tweak_treeinfo(source_file)
    for variant_uid in include_variants:
        variant = compose.all_variants[variant_uid]
        var = productmd.treeinfo.Variant(ti)
        var.id = variant.id
        var.uid = variant.uid
        var.name = variant.name
        var.type = variant.type
        ti.variants.add(var)

    for variant_id in ti.variants:
        var = ti.variants[variant_id]
        var.paths.packages = os.path.join(var.uid, "Packages")
        var.paths.repository = var.uid

    ti.dump(dest_file)


def get_filename(compose, variant, arch, format):
    disc_type = compose.conf["disc_types"].get("dvd", "dvd")
    base_filename = compose.get_image_name(
        arch, variant, disc_type=disc_type, disc_num=1
    )
    if not format:
        return base_filename
    kwargs = {
        "arch": arch,
        "disc_type": disc_type,
        "disc_num": 1,
        "suffix": ".iso",
        "filename": base_filename,
        "variant": variant,
    }
    args = get_format_substs(compose, **kwargs)
    try:
        return (format % args).format(**args)
    except KeyError as err:
        raise RuntimeError(
            "Failed to create image name: unknown format element: %s" % err
        )


def get_volume_id(compose, variant, arch, formats):
    disc_type = compose.conf["disc_types"].get("dvd", "dvd")
    # Get volume ID for regular ISO so that we can substitute it in.
    volid = get_volid(compose, arch, variant, disc_type=disc_type)
    return get_volid(
        compose,
        arch,
        variant,
        disc_type=disc_type,
        formats=force_list(formats),
        volid=volid,
    )


def prepare_media_metadata(compose, variant, arch):
    """Write a .discinfo and media.repo files to a directory that will be
    included on the ISO. It's possible to overwrite the files by using extra
    files.
    """
    md_dir = compose.paths.work.extra_iso_extra_files_dir(arch, variant)
    description = metadata.get_description(compose, variant, arch)
    metadata.create_media_repo(
        os.path.join(md_dir, "media.repo"), description, timestamp=None
    )
    metadata.create_discinfo(os.path.join(md_dir, ".discinfo"), description, arch)
