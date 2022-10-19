# -*- coding: utf-8 -*-

import fnmatch
import json
import os
from kobo.threads import ThreadPool, WorkerThread
from kobo import shortcuts

from .base import ConfigGuardedPhase, PhaseLoggerMixin
from .. import util
from ..wrappers import kojiwrapper


class OSBSPhase(PhaseLoggerMixin, ConfigGuardedPhase):
    name = 'osbs'

    def __init__(self, compose):
        super(OSBSPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.pool.metadata = {}
        self.pool.registries = {}

    def run(self):
        for variant in self.compose.get_variants():
            for conf in self.get_config_block(variant):
                self.pool.add(OSBSThread(self.pool))
                self.pool.queue_put((self.compose, variant, conf))

        self.pool.start()

    def dump_metadata(self):
        """Create a file with image metadata if the phase actually ran."""
        if self._skipped:
            return
        with open(self.compose.paths.compose.metadata('osbs.json'), 'w') as f:
            json.dump(self.pool.metadata, f, indent=4, sort_keys=True,
                      separators=(',', ': '))

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
        with util.failable(compose, bool(config.pop('failable', None)), variant, '*', 'osbs',
                           logger=self.pool._logger):
            self.worker(compose, variant, config)

    def worker(self, compose, variant, config):
        msg = 'OSBS task for variant %s' % variant.uid
        self.pool.log_info('[BEGIN] %s' % msg)
        koji = kojiwrapper.KojiWrapper(compose.conf['koji_profile'])
        koji.login()

        # Start task
        source = config.pop('url')
        target = config.pop('target')
        priority = config.pop('priority', None)
        gpgkey = config.pop('gpgkey', None)
        repos = [self._get_repo(compose, v, gpgkey=gpgkey)
                 for v in [variant.uid] + shortcuts.force_list(config.pop('repo', []))]
        # Deprecated in 4.1.36
        registry = config.pop("registry", None)

        config['yum_repourls'] = repos

        task_id = koji.koji_proxy.buildContainer(source, target, config,
                                                 priority=priority)

        # Wait for it to finish and capture the output into log file (even
        # though there is not much there).
        log_dir = os.path.join(compose.paths.log.topdir(), 'osbs')
        util.makedirs(log_dir)
        log_file = os.path.join(log_dir, '%s-%s-watch-task.log'
                                % (variant.uid, self.num))
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError('OSBS: task %s failed: see %s for details'
                               % (task_id, log_file))

        scratch = config.get('scratch', False)
        nvr = self._add_metadata(variant, task_id, compose, scratch)
        if nvr:
            registry = get_registry(compose, nvr, registry)
            if registry:
                self.pool.registries[nvr] = registry

        self.pool.log_info('[DONE ] %s' % msg)

    def _add_metadata(self, variant, task_id, compose, is_scratch):
        # Create new Koji session. The task could take so long to finish that
        # our session will expire. This second session does not need to be
        # authenticated since it will only do reading operations.
        koji = kojiwrapper.KojiWrapper(compose.conf['koji_profile'])

        # Create metadata
        metadata = {
            'compose_id': compose.compose_id,
            'koji_task': task_id,
        }

        result = koji.koji_proxy.getTaskResult(task_id)
        if is_scratch:
            metadata.update({
                'repositories': result['repositories'],
            })
            # add a fake arch of 'scratch', so we can construct the metadata
            # in same data structure as real builds.
            self.pool.metadata.setdefault(
                variant.uid, {}).setdefault('scratch', []).append(metadata)
            return None

        else:
            build_id = int(result['koji_builds'][0])
            buildinfo = koji.koji_proxy.getBuild(build_id)
            archives = koji.koji_proxy.listArchives(build_id)

            nvr = "%(name)s-%(version)s-%(release)s" % buildinfo

            metadata.update({
                'name': buildinfo['name'],
                'version': buildinfo['version'],
                'release': buildinfo['release'],
                'nvr': nvr,
                'creation_time': buildinfo['creation_time'],
            })
            for archive in archives:
                data = {
                    'filename': archive['filename'],
                    'size': archive['size'],
                    'checksum': archive['checksum'],
                }
                data.update(archive['extra'])
                data.update(metadata)
                arch = archive['extra']['image']['arch']
                self.pool.log_debug('Created Docker base image %s-%s-%s.%s' % (
                    metadata['name'], metadata['version'], metadata['release'], arch))
                self.pool.metadata.setdefault(
                    variant.uid, {}).setdefault(arch, []).append(data)
            return nvr

    def _get_repo(self, compose, repo, gpgkey=None):
        """
        Return repo file URL of repo, if repo contains "://", it's already a
        URL of repo file. Or it's a variant UID or local path, then write a .repo
        file pointing to that location and return the URL to .repo file.
        """
        if "://" in repo:
            return repo

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
            repo_path = compose.paths.compose.repository(
                "$basearch", variant, create_dir=False
            )

            repo_file = os.path.join(
                compose.paths.work.tmp_dir(None, variant),
                'compose-rpms-%s-%s.repo' % (variant, self.num),
            )

        gpgcheck = 1 if gpgkey else 0
        with open(repo_file, 'w') as f:
            f.write('[%s-%s-%s]\n' % (compose.compose_id, variant, self.num))
            f.write('name=Compose %s (RPMs) - %s\n' % (compose.compose_id, variant))
            f.write('baseurl=%s\n' % util.translate_path(compose, repo_path))
            f.write('enabled=1\n')
            f.write('gpgcheck=%s\n' % gpgcheck)
            if gpgcheck:
                f.write('gpgkey=%s\n' % gpgkey)

        return util.translate_path(compose, repo_file)
