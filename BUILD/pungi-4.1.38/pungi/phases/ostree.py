# -*- coding: utf-8 -*-

import copy
import json
import os
from kobo import shortcuts
from kobo.threads import ThreadPool, WorkerThread

from pungi.arch_utils import getBaseArch
from pungi.runroot import Runroot
from .base import ConfigGuardedPhase
from .. import util
from ..ostree.utils import get_ref_from_treefile, get_commitid_from_commitid_file
from ..util import get_repo_dicts, translate_path
from ..wrappers import scm


class OSTreePhase(ConfigGuardedPhase):
    name = 'ostree'

    def __init__(self, compose):
        super(OSTreePhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.compose._logger)

    def _enqueue(self, variant, arch, conf):
        self.pool.add(OSTreeThread(self.pool))
        self.pool.queue_put((self.compose, variant, arch, conf))

    def run(self):
        if isinstance(self.compose.conf.get(self.name), dict):
            for variant in self.compose.get_variants():
                for conf in self.get_config_block(variant):
                    for arch in conf.get('arches', []) or variant.arches:
                        self._enqueue(variant, arch, conf)
        else:
            # Legacy code path to support original configuration.
            for variant in self.compose.get_variants():
                for arch in variant.arches:
                    for conf in self.get_config_block(variant, arch):
                        self._enqueue(variant, arch, conf)

        self.pool.start()


class OSTreeThread(WorkerThread):
    def process(self, item, num):
        compose, variant, arch, config = item
        self.num = num
        failable_arches = config.get('failable', [])
        with util.failable(compose, util.can_arch_fail(failable_arches, arch),
                           variant, arch, 'ostree'):
            self.worker(compose, variant, arch, config)

    def worker(self, compose, variant, arch, config):
        msg = 'OSTree phase for variant %s, arch %s' % (variant.uid, arch)
        self.pool.log_info('[BEGIN] %s' % msg)
        workdir = compose.paths.work.topdir('ostree-%d' % self.num)
        self.logdir = compose.paths.log.topdir('%s/%s/ostree-%d' %
                                               (arch, variant.uid, self.num))
        repodir = os.path.join(workdir, 'config_repo')
        self._clone_repo(repodir, config['config_url'], config.get('config_branch', 'master'))

        repo_baseurl = compose.paths.work.arch_repo('$basearch', create_dir=False)
        comps_repo = compose.paths.work.comps_repo('$basearch', variant=variant, create_dir=False)
        repos = shortcuts.force_list(config['repo']) + [translate_path(compose, repo_baseurl)]
        if compose.has_comps:
            repos.append(translate_path(compose, comps_repo))
        repos = get_repo_dicts(repos, logger=self.pool)

        # copy the original config and update before save to a json file
        new_config = copy.copy(config)

        # repos in configuration can have repo url set to variant UID,
        # update it to have the actual url that we just translated.
        new_config.update({'repo': repos})

        # remove unnecessary (for 'pungi-make-ostree tree' script ) elements
        # from config, it doesn't hurt to have them, however remove them can
        # reduce confusion
        for k in ['ostree_repo', 'treefile', 'config_url', 'config_branch',
                  'failable', 'version', 'update_summary']:
            new_config.pop(k, None)

        # write a json file to save the configuration, so 'pungi-make-ostree tree'
        # can take use of it
        extra_config_file = os.path.join(workdir, 'extra_config.json')
        with open(extra_config_file, 'w') as f:
            json.dump(new_config, f, indent=4)

        # Ensure target directory exists, otherwise Koji task will fail to
        # mount it.
        util.makedirs(config['ostree_repo'])

        self._run_ostree_cmd(compose, variant, arch, config, repodir,
                                       extra_config_file=extra_config_file)

        if compose.notifier:
            original_ref = get_ref_from_treefile(
                os.path.join(repodir, config["treefile"]),
                arch,
                logger=self.pool._logger,
            )
            ref = config.get("ostree_ref") or original_ref
            ref = ref.replace("${basearch}", getBaseArch(arch))
            # 'pungi-make-ostree tree' writes commitid to commitid.log in
            # logdir, except if there was no new commit we will get None
            # instead. If the commit id could not be read, an exception will be
            # raised.
            commitid = get_commitid_from_commitid_file(
                os.path.join(self.logdir, 'commitid.log')
            )
            compose.notifier.send('ostree',
                                  variant=variant.uid,
                                  arch=arch,
                                  ref=ref,
                                  commitid=commitid,
                                  repo_path=translate_path(compose, config['ostree_repo']),
                                  local_repo_path=config['ostree_repo'])

        self.pool.log_info('[DONE ] %s' % (msg))

    def _run_ostree_cmd(self, compose, variant, arch, config, config_repo, extra_config_file=None):
        cmd = [
            'pungi-make-ostree',
            'tree',
            '--repo=%s' % config['ostree_repo'],
            '--log-dir=%s' % self.logdir,
            '--treefile=%s' % os.path.join(config_repo, config['treefile']),
        ]

        version = util.version_generator(compose, config.get('version'))
        if version:
            cmd.append('--version=%s' % version)

        if extra_config_file:
            cmd.append('--extra-config=%s' % extra_config_file)

        if config.get('update_summary', False):
            cmd.append('--update-summary')

        ostree_ref = config.get('ostree_ref')
        if ostree_ref:
            cmd.append('--ostree-ref=%s' % ostree_ref)

        if config.get('force_new_commit', False):
            cmd.append('--force-new-commit')

        packages = ['pungi', 'ostree', 'rpm-ostree']
        log_file = os.path.join(self.logdir, 'runroot.log')
        mounts = [compose.topdir, config['ostree_repo']]

        runroot = Runroot(compose)
        runroot.run(
            cmd, log_file=log_file, arch=arch, packages=packages,
            mounts=mounts, new_chroot=True,
            weight=compose.conf['runroot_weights'].get('ostree'))

    def _clone_repo(self, repodir, url, branch):
        scm.get_dir_from_scm({'scm': 'git', 'repo': url, 'branch': branch, 'dir': '.'},
                             repodir, logger=self.pool._logger)
