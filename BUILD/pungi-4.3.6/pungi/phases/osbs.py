# -*- coding: utf-8 -*-

import copy
import fnmatch
import json
import os
from kobo.threads import ThreadPool, WorkerThread
from kobo import shortcuts
from productmd.rpms import Rpms
from six.moves import configparser

from .base import ConfigGuardedPhase, PhaseLoggerMixin
from .. import util
from ..wrappers import kojiwrapper
from ..wrappers.scm import get_file_from_scm


class OSBSPhase(PhaseLoggerMixin, ConfigGuardedPhase):
    name = "osbs"

    def __init__(self, compose, pkgset_phase, buildinstall_phase):
        super(OSBSPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.pool.registries = {}
        self.pool.pkgset_phase = pkgset_phase
        self.pool.buildinstall_phase = buildinstall_phase

    def run(self):
        for variant in self.compose.get_variants():
            for conf in self.get_config_block(variant):
                self.pool.add(OSBSThread(self.pool))
                self.pool.queue_put((self.compose, variant, conf))

        self.pool.start()

    def request_push(self):
        """Store configuration data about where to push the created images and
        then send the same data to message bus.
        """
        if not self.pool.registries:
            return

        # Write the data into a file.
        registry_file = os.path.join(
            self.compose.paths.log.topdir(), "osbs-registries.json"
        )
        with open(registry_file, "w") as fh:
            json.dump(self.pool.registries, fh)

        # Send a message with the data
        if self.compose.notifier:
            self.compose.notifier.send(
                "osbs-request-push",
                config_location=util.translate_path(self.compose, registry_file),
                config=self.pool.registries,
            )


def get_registry(compose, nvr, fallback=None):
    """Get a configured registry for the image from config matching given NVR.
    If not present, return fallback value.
    """
    for pattern, registry in compose.conf.get("osbs_registries", {}).items():
        if fnmatch.fnmatch(nvr, pattern):
            return registry
    return fallback


class OSBSThread(WorkerThread):
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
        msg = "OSBS task for variant %s" % variant.uid
        self.pool.log_info("[BEGIN] %s" % msg)

        original_config = copy.deepcopy(config)

        # Start task
        source = config.pop("url")
        target = config.pop("target")
        priority = config.pop("priority", None)
        gpgkey = config.pop("gpgkey", None)
        repos = [
            self._get_repo(compose, v, gpgkey=gpgkey)
            for v in [variant.uid] + shortcuts.force_list(config.pop("repo", []))
        ]
        # Deprecated in 4.1.36
        registry = config.pop("registry", None)

        config["yum_repourls"] = repos

        log_dir = os.path.join(compose.paths.log.topdir(), "osbs")
        util.makedirs(log_dir)
        log_file = os.path.join(
            log_dir, "%s-%s-watch-task.log" % (variant.uid, self.num)
        )
        reuse_file = log_file[:-4] + ".reuse.json"

        try:
            image_conf = self._get_image_conf(compose, original_config)
        except Exception as e:
            image_conf = None
            self.pool.log_info(
                "Can't get image-build.conf for variant: %s source: %s - %s"
                % (variant.uid, source, str(e))
            )

        koji = kojiwrapper.KojiWrapper(compose)
        koji.login()

        task_id = self._try_to_reuse(
            compose, variant, original_config, image_conf, reuse_file
        )

        if not task_id:
            task_id = koji.koji_proxy.buildContainer(
                source, target, config, priority=priority
            )

        koji.save_task_id(task_id)

        # Wait for it to finish and capture the output into log file (even
        # though there is not much there).
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError(
                "OSBS: task %s failed: see %s for details" % (task_id, log_file)
            )

        scratch = config.get("scratch", False)
        nvr, archive_ids = add_metadata(variant, task_id, compose, scratch)
        if nvr:
            registry = get_registry(compose, nvr, registry)
            if registry:
                self.pool.registries[nvr] = registry

        self._write_reuse_metadata(
            compose,
            variant,
            original_config,
            image_conf,
            task_id,
            archive_ids,
            reuse_file,
        )

        self.pool.log_info("[DONE ] %s" % msg)

    def _get_image_conf(self, compose, config):
        """Get image-build.conf from git repo.

        :param Compose compose: Current compose.
        :param dict config: One osbs config item of compose.conf["osbs"][$variant]
        """
        tmp_dir = compose.mkdtemp(prefix="osbs_")

        url = config["url"].split("#")
        if len(url) == 1:
            url.append(config["git_branch"])

        filename = "image-build.conf"
        get_file_from_scm(
            {
                "scm": "git",
                "repo": url[0],
                "branch": url[1],
                "file": [filename],
            },
            tmp_dir,
        )

        c = configparser.ConfigParser()
        c.read(os.path.join(tmp_dir, filename))
        return c

    def _get_ksurl(self, image_conf):
        """Get ksurl from image-build.conf"""
        ksurl = image_conf.get("image-build", "ksurl")

        if ksurl:
            resolver = util.GitUrlResolver(offline=False)
            return resolver(ksurl)
        else:
            return None

    def _get_repo(self, compose, repo, gpgkey=None):
        """
        Return repo file URL of repo, if repo contains "://", it's already a
        URL of repo file. Or it's a variant UID or local path, then write a .repo
        file pointing to that location and return the URL to .repo file.
        """
        if "://" in repo:
            return repo.replace("$COMPOSE_ID", compose.compose_id)

        if repo.startswith("/"):
            # The repo is an absolute path on the filesystem
            repo_path = repo
            variant = "local"
            repo_file = os.path.join(
                compose.paths.work.tmp_dir(None, None),
                "compose-rpms-%s-%s.repo" % (variant, self.num),
            )

        else:
            # We got a variant name and have to find the repository for that variant.
            try:
                variant = compose.all_variants[repo]
            except KeyError:
                raise RuntimeError(
                    "There is no variant %s to get repo from to pass to OSBS." % repo
                )
            cts_url = compose.conf.get("cts_url", None)
            if cts_url:
                return os.path.join(
                    cts_url,
                    "api/1/composes",
                    compose.compose_id,
                    "repo/?variant=%s" % variant,
                )

            repo_path = compose.paths.compose.repository(
                "$basearch", variant, create_dir=False
            )

            repo_file = os.path.join(
                compose.paths.work.tmp_dir(None, variant),
                "compose-rpms-%s-%s.repo" % (variant, self.num),
            )

        gpgcheck = 1 if gpgkey else 0
        with open(repo_file, "w") as f:
            f.write("[%s-%s-%s]\n" % (compose.compose_id, variant, self.num))
            f.write("name=Compose %s (RPMs) - %s\n" % (compose.compose_id, variant))
            f.write("baseurl=%s\n" % util.translate_path(compose, repo_path))
            f.write("enabled=1\n")
            f.write("gpgcheck=%s\n" % gpgcheck)
            if gpgcheck:
                f.write("gpgkey=%s\n" % gpgkey)

        return util.translate_path(compose, repo_file)

    def _try_to_reuse(self, compose, variant, config, image_conf, reuse_file):
        """Try to reuse results of old compose.

        :param Compose compose: Current compose.
        :param Variant variant: Current variant.
        :param dict config: One osbs config item of compose.conf["osbs"][$variant]
        :param ConfigParser image_conf: ConfigParser obj of image-build.conf.
        :param str reuse_file: Path to reuse metadata file
        """
        log_msg = "Cannot reuse old osbs phase results - %s"

        if not compose.conf["osbs_allow_reuse"]:
            self.pool.log_info(log_msg % "reuse of old osbs results is disabled.")
            return False

        old_reuse_file = compose.paths.old_compose_path(reuse_file)
        if not old_reuse_file:
            self.pool.log_info(log_msg % "Can't find old reuse metadata file")
            return False

        try:
            with open(old_reuse_file) as f:
                old_reuse_metadata = json.load(f)
        except Exception as e:
            self.pool.log_info(
                log_msg % "Can't load old reuse metadata file: %s" % str(e)
            )
            return False

        if old_reuse_metadata["config"] != config:
            self.pool.log_info(log_msg % "osbs config changed")
            return False

        if not image_conf:
            self.pool.log_info(log_msg % "Can't get image-build.conf")
            return False

        # Make sure ksurl not change
        try:
            ksurl = self._get_ksurl(image_conf)
        except Exception as e:
            self.pool.log_info(
                log_msg % "Can't get ksurl from image-build.conf - %s" % str(e)
            )
            return False

        if not old_reuse_metadata["ksurl"]:
            self.pool.log_info(
                log_msg % "Can't get ksurl from old compose reuse metadata."
            )
            return False

        if ksurl != old_reuse_metadata["ksurl"]:
            self.pool.log_info(log_msg % "ksurl changed")
            return False

        # Make sure buildinstall phase is reused
        try:
            arches = image_conf.get("image-build", "arches").split(",")
        except Exception as e:
            self.pool.log_info(
                log_msg % "Can't get arches from image-build.conf - %s" % str(e)
            )
        for arch in arches:
            if not self.pool.buildinstall_phase.reused(variant, arch):
                self.pool.log_info(
                    log_msg % "buildinstall phase changed %s.%s" % (variant, arch)
                )
                return False

        # Make sure rpms installed in image exists in current compose
        rpm_manifest_file = compose.paths.compose.metadata("rpms.json")
        rpm_manifest = Rpms()
        rpm_manifest.load(rpm_manifest_file)
        rpms = set()
        for variant in rpm_manifest.rpms:
            for arch in rpm_manifest.rpms[variant]:
                for src in rpm_manifest.rpms[variant][arch]:
                    for nevra in rpm_manifest.rpms[variant][arch][src]:
                        rpms.add(nevra)

        for nevra in old_reuse_metadata["rpmlist"]:
            if nevra not in rpms:
                self.pool.log_info(
                    log_msg % "%s does not exist in current compose" % nevra
                )
                return False

        self.pool.log_info(
            "Reusing old OSBS task %d result" % old_reuse_file["task_id"]
        )
        return old_reuse_file["task_id"]

    def _write_reuse_metadata(
        self, compose, variant, config, image_conf, task_id, archive_ids, reuse_file
    ):
        """Write metadata to file for reusing.

        :param Compose compose: Current compose.
        :param Variant variant: Current variant.
        :param dict config: One osbs config item of compose.conf["osbs"][$variant]
        :param ConfigParser image_conf: ConfigParser obj of image-build.conf.
        :param int task_id: Koji task id of osbs task.
        :param list archive_ids: List of koji archive id
        :param str reuse_file: Path to reuse metadata file.
        """
        msg = "Writing reuse metadata file %s" % reuse_file
        compose.log_info(msg)

        rpmlist = set()
        koji = kojiwrapper.KojiWrapper(compose)
        for archive_id in archive_ids:
            rpms = koji.koji_proxy.listRPMs(imageID=archive_id)
            for item in rpms:
                if item["epoch"]:
                    rpmlist.add(
                        "%s:%s-%s-%s.%s"
                        % (
                            item["name"],
                            item["epoch"],
                            item["version"],
                            item["release"],
                            item["arch"],
                        )
                    )
                else:
                    rpmlist.add("%s.%s" % (item["nvr"], item["arch"]))

        try:
            ksurl = self._get_ksurl(image_conf)
        except Exception:
            ksurl = None

        data = {
            "config": config,
            "ksurl": ksurl,
            "rpmlist": sorted(rpmlist),
            "task_id": task_id,
        }
        try:
            with open(reuse_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            compose.log_info(msg + " failed - %s" % str(e))


def add_metadata(variant, task_id, compose, is_scratch):
    """Given a task ID, find details about the container and add it to global
    metadata."""
    # Create new Koji session. The task could take so long to finish that
    # our session will expire. This second session does not need to be
    # authenticated since it will only do reading operations.
    koji = kojiwrapper.KojiWrapper(compose)

    # Create metadata
    metadata = {
        "compose_id": compose.compose_id,
        "koji_task": task_id,
    }

    result = koji.koji_proxy.getTaskResult(task_id)
    if is_scratch:
        metadata.update({"repositories": result["repositories"]})
        # add a fake arch of 'scratch', so we can construct the metadata
        # in same data structure as real builds.
        compose.containers_metadata.setdefault(variant.uid, {}).setdefault(
            "scratch", []
        ).append(metadata)
        return None, []

    else:
        build_id = int(result["koji_builds"][0])
        buildinfo = koji.koji_proxy.getBuild(build_id)
        archives = koji.koji_proxy.listArchives(build_id, type="image")

        nvr = "%(name)s-%(version)s-%(release)s" % buildinfo

        metadata.update(
            {
                "name": buildinfo["name"],
                "version": buildinfo["version"],
                "release": buildinfo["release"],
                "nvr": nvr,
                "creation_time": buildinfo["creation_time"],
            }
        )
        archive_ids = []
        for archive in archives:
            data = {
                "filename": archive["filename"],
                "size": archive["size"],
                "checksum": archive["checksum"],
            }
            data.update(archive["extra"])
            data.update(metadata)
            arch = archive["extra"]["image"]["arch"]
            compose.log_debug(
                "Created Docker base image %s-%s-%s.%s"
                % (metadata["name"], metadata["version"], metadata["release"], arch)
            )
            compose.containers_metadata.setdefault(variant.uid, {}).setdefault(
                arch, []
            ).append(data)
            archive_ids.append(archive["id"])
        return nvr, archive_ids
