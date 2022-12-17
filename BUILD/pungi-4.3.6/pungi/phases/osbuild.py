# -*- coding: utf-8 -*-

import os
from kobo.threads import ThreadPool, WorkerThread
from kobo import shortcuts
from productmd.images import Image

from . import base
from .. import util
from ..linker import Linker
from ..wrappers import kojiwrapper
from .image_build import EXTENSIONS


class OSBuildPhase(
    base.PhaseLoggerMixin, base.ImageConfigMixin, base.ConfigGuardedPhase
):
    name = "osbuild"

    def __init__(self, compose):
        super(OSBuildPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def _get_arches(self, image_conf, arches):
        """Get an intersection of arches in the config dict and the given ones."""
        if "arches" in image_conf:
            arches = set(image_conf["arches"]) & arches
        return sorted(arches)

    def _get_repo(self, image_conf, variant):
        """
        Get a list of repos. First included are those explicitly listed in
        config, followed by by repo for current variant if it's not included in
        the list already.
        """
        repos = shortcuts.force_list(image_conf.get("repo", []))

        if not variant.is_empty and variant.uid not in repos:
            repos.append(variant.uid)

        return util.get_repo_urls(self.compose, repos, arch="$arch")

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != "src"])

            for image_conf in self.get_config_block(variant):
                build_arches = self._get_arches(image_conf, arches)
                if not build_arches:
                    self.log_debug("skip: no arches")
                    continue

                release = self.get_release(image_conf)
                version = self.get_version(image_conf)
                target = self.get_config(image_conf, "target")

                repo = self._get_repo(image_conf, variant)

                can_fail = image_conf.pop("failable", [])
                if can_fail == ["*"]:
                    can_fail = image_conf["arches"]
                if can_fail:
                    can_fail = sorted(can_fail)

                self.pool.add(RunOSBuildThread(self.pool))
                self.pool.queue_put(
                    (
                        self.compose,
                        variant,
                        image_conf,
                        build_arches,
                        version,
                        release,
                        target,
                        repo,
                        can_fail,
                    )
                )

        self.pool.start()


class RunOSBuildThread(WorkerThread):
    def process(self, item, num):
        (
            compose,
            variant,
            config,
            arches,
            version,
            release,
            target,
            repo,
            can_fail,
        ) = item
        self.can_fail = can_fail
        self.num = num
        with util.failable(
            compose,
            can_fail,
            variant,
            "*",
            "osbuild",
            logger=self.pool._logger,
        ):
            self.worker(
                compose, variant, config, arches, version, release, target, repo
            )

    def worker(self, compose, variant, config, arches, version, release, target, repo):
        msg = "OSBuild task for variant %s" % variant.uid
        self.pool.log_info("[BEGIN] %s" % msg)
        koji = kojiwrapper.KojiWrapper(compose)
        koji.login()

        ostree = {}
        if config.get("ostree_url"):
            ostree["url"] = config["ostree_url"]
        if config.get("ostree_ref"):
            ostree["ref"] = config["ostree_ref"]
        if config.get("ostree_parent"):
            ostree["parent"] = config["ostree_parent"]

        # Start task
        opts = {"repo": repo}
        if ostree:
            opts["ostree"] = ostree

        if release:
            opts["release"] = release
        task_id = koji.koji_proxy.osbuildImage(
            config["name"],
            version,
            config["distro"],
            config["image_types"],
            target,
            arches,
            opts=opts,
        )

        koji.save_task_id(task_id)

        # Wait for it to finish and capture the output into log file.
        log_dir = os.path.join(compose.paths.log.topdir(), "osbuild")
        util.makedirs(log_dir)
        log_file = os.path.join(
            log_dir, "%s-%s-watch-task.log" % (variant.uid, self.num)
        )
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError(
                "OSBuild: task %s failed: see %s for details" % (task_id, log_file)
            )

        # Refresh koji session which may have timed out while the task was
        # running. Watching is done via a subprocess, so the session is
        # inactive.
        koji = kojiwrapper.KojiWrapper(compose)

        # Get build id via the task's result json data
        result = koji.koji_proxy.getTaskResult(task_id)
        build_id = result["koji"]["build"]

        linker = Linker(logger=self.pool._logger)

        # Process all images in the build. There should be one for each
        # architecture, but we don't verify that.
        build_info = koji.koji_proxy.getBuild(build_id)
        for archive in koji.koji_proxy.listArchives(buildID=build_id):
            if archive["type_name"] not in EXTENSIONS:
                # Ignore values that are not of required types.
                continue

            # Get architecture of the image from extra data.
            try:
                arch = archive["extra"]["image"]["arch"]
            except KeyError:
                raise RuntimeError("Image doesn't have any architecture!")

            # image_dir is absolute path to which the image should be copied.
            # We also need the same path as relative to compose directory for
            # including in the metadata.
            image_dir = compose.paths.compose.image_dir(variant) % {"arch": arch}
            rel_image_dir = compose.paths.compose.image_dir(variant, relative=True) % {
                "arch": arch
            }
            util.makedirs(image_dir)

            image_dest = os.path.join(image_dir, archive["filename"])

            src_file = os.path.join(
                koji.koji_module.pathinfo.imagebuild(build_info), archive["filename"]
            )

            linker.link(src_file, image_dest, link_type=compose.conf["link_type"])

            for suffix in EXTENSIONS[archive["type_name"]]:
                if archive["filename"].endswith(suffix):
                    break
            else:
                # No suffix matched.
                raise RuntimeError(
                    "Failed to generate metadata. Format %s doesn't match type %s"
                    % (suffix, archive["type_name"])
                )

            # Update image manifest
            img = Image(compose.im)
            img.type = archive["type_name"]
            img.format = suffix
            img.path = os.path.join(rel_image_dir, archive["filename"])
            img.mtime = util.get_mtime(image_dest)
            img.size = util.get_file_size(image_dest)
            img.arch = arch
            img.disc_number = 1  # We don't expect multiple disks
            img.disc_count = 1
            img.bootable = False
            img.subvariant = config.get("subvariant", variant.uid)
            setattr(img, "can_fail", self.can_fail)
            setattr(img, "deliverable", "image-build")
            compose.im.add(variant=variant.uid, arch=arch, image=img)

        self.pool.log_info("[DONE ] %s (task id: %s)" % (msg, task_id))
