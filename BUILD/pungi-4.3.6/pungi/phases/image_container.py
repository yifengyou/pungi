# -*- coding: utf-8 -*-

import os
import re
from kobo.threads import ThreadPool, WorkerThread

from .base import ConfigGuardedPhase, PhaseLoggerMixin
from .. import util
from ..wrappers import kojiwrapper
from ..phases.osbs import add_metadata


class ImageContainerPhase(PhaseLoggerMixin, ConfigGuardedPhase):
    name = "image_container"

    def __init__(self, compose):
        super(ImageContainerPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.pool.metadata = {}

    def run(self):
        for variant in self.compose.get_variants():
            for conf in self.get_config_block(variant):
                self.pool.add(ImageContainerThread(self.pool))
                self.pool.queue_put((self.compose, variant, conf))

        self.pool.start()


class ImageContainerThread(WorkerThread):
    def process(self, item, num):
        compose, variant, config = item
        self.num = num
        with util.failable(
            compose,
            bool(config.pop("failable", None)),
            variant,
            "*",
            "osbs",
            logger=self.pool._logger,
        ):
            self.worker(compose, variant, config)

    def worker(self, compose, variant, config):
        msg = "Image container task for variant %s" % variant.uid
        self.pool.log_info("[BEGIN] %s" % msg)

        source = config.pop("url")
        target = config.pop("target")
        priority = config.pop("priority", None)

        config["yum_repourls"] = [
            self._get_repo(
                compose,
                variant,
                config.get("arch_override", "").split(),
                config.pop("image_spec"),
            )
        ]

        # Start task
        koji = kojiwrapper.KojiWrapper(compose)
        koji.login()
        task_id = koji.koji_proxy.buildContainer(
            source, target, config, priority=priority
        )

        koji.save_task_id(task_id)

        # Wait for it to finish and capture the output into log file (even
        # though there is not much there).
        log_dir = os.path.join(compose.paths.log.topdir(), "image_container")
        util.makedirs(log_dir)
        log_file = os.path.join(
            log_dir, "%s-%s-watch-task.log" % (variant.uid, self.num)
        )
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError(
                "ImageContainer: task %s failed: see %s for details"
                % (task_id, log_file)
            )

        add_metadata(variant, task_id, compose, config.get("scratch", False))

        self.pool.log_info("[DONE ] %s" % msg)

    def _get_repo(self, compose, variant, arches, image_spec):
        """
        Return a repo file that points baseurl to the image specified by
        image_spec.
        """
        image_paths = set()

        for arch in arches or compose.im.images[variant.uid].keys():
            for image in compose.im.images[variant.uid].get(arch, []):
                for key, value in image_spec.items():
                    if not re.match(value, getattr(image, key)):
                        break
                else:
                    image_paths.add(image.path.replace(arch, "$basearch"))

        if len(image_paths) != 1:
            raise RuntimeError(
                "%d images matched specification. Only one was expected."
                % len(image_paths)
            )

        image_path = image_paths.pop()
        absolute_path = os.path.join(compose.paths.compose.topdir(), image_path)

        repo_file = os.path.join(
            compose.paths.work.tmp_dir(None, variant),
            "image-container-%s-%s.repo" % (variant, self.num),
        )
        with open(repo_file, "w") as f:
            f.write("[image-to-include]\n")
            f.write("name=Location of image to embed\n")
            f.write("baseurl=%s\n" % util.translate_path(compose, absolute_path))
            f.write("enabled=0\n")
            f.write("gpgcheck=0\n")

        return util.translate_path(compose, repo_file)
