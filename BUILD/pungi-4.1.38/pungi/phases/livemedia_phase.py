# -*- coding: utf-8 -*-

import os
import time
from kobo import shortcuts

from pungi.util import makedirs, get_mtime, get_file_size, failable, log_failed_task
from pungi.util import translate_path, get_repo_urls
from pungi.phases.base import ConfigGuardedPhase, ImageConfigMixin, PhaseLoggerMixin
from pungi.linker import Linker
from pungi.wrappers.kojiwrapper import KojiWrapper
from kobo.threads import ThreadPool, WorkerThread
from productmd.images import Image


class LiveMediaPhase(PhaseLoggerMixin, ImageConfigMixin, ConfigGuardedPhase):
    """class for wrapping up koji spin-livemedia"""
    name = 'live_media'

    def __init__(self, compose):
        super(LiveMediaPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def _get_repos(self, image_conf, variant):
        """
        Get a list of repo urls. First included are those explicitly listed in config,
        followed by repo for current variant if it's not present in the list.
        """
        repos = shortcuts.force_list(image_conf.get('repo', []))

        if not variant.is_empty:
            if variant.uid not in repos:
                repos.append(variant.uid)

        return get_repo_urls(self.compose, repos)

    def _get_arches(self, image_conf, arches):
        if 'arches' in image_conf:
            arches = set(image_conf.get('arches', [])) & arches
        return sorted(arches)

    def _get_install_tree(self, image_conf, variant):
        if 'install_tree_from' in image_conf:
            variant_uid = image_conf['install_tree_from']
            try:
                variant = self.compose.all_variants[variant_uid]
            except KeyError:
                raise RuntimeError(
                    'There is no variant %s to get repo from when building live media for %s.'
                    % (variant_uid, variant.uid))
        return translate_path(
            self.compose,
            self.compose.paths.compose.os_tree('$basearch', variant, create_dir=False)
        )

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != 'src'])
            for image_conf in self.get_config_block(variant):
                subvariant = image_conf.get('subvariant', variant.uid)
                name = image_conf.get(
                    'name', "%s-%s-Live" % (self.compose.ci_base.release.short, subvariant))
                config = {
                    'target': self.get_config(image_conf, 'target'),
                    'arches': self._get_arches(image_conf, arches),
                    'ksfile': image_conf['kickstart'],
                    'ksurl': self.get_ksurl(image_conf),
                    'ksversion': image_conf.get('ksversion'),
                    'scratch': image_conf.get('scratch', False),
                    'release': self.get_release(image_conf),
                    'skip_tag': image_conf.get('skip_tag'),
                    'name': name,
                    'subvariant': subvariant,
                    'title': image_conf.get('title'),
                    'repo': self._get_repos(image_conf, variant),
                    'install_tree': self._get_install_tree(image_conf, variant),
                    'version': self.get_version(image_conf),
                    'failable_arches': image_conf.get('failable', []),
                }
                if config['failable_arches'] == ['*']:
                    config['failable_arches'] = config['arches']
                self.pool.add(LiveMediaThread(self.pool))
                self.pool.queue_put((self.compose, variant, config))

        self.pool.start()


class LiveMediaThread(WorkerThread):
    def process(self, item, num):
        compose, variant, config = item
        subvariant = config.pop('subvariant')
        self.failable_arches = config.pop('failable_arches')
        self.num = num
        can_fail = set(self.failable_arches) == set(config['arches'])
        with failable(compose, can_fail, variant, '*', 'live-media', subvariant,
                      logger=self.pool._logger):
            self.worker(compose, variant, subvariant, config)

    def _get_log_file(self, compose, variant, subvariant, config):
        arches = '-'.join(config['arches'])
        return compose.paths.log.log_file(arches, 'livemedia-%s-%s'
                                          % (variant.uid, subvariant))

    def _run_command(self, koji_wrapper, cmd, compose, log_file):
        time.sleep(self.num * 3)
        output = koji_wrapper.run_blocking_cmd(cmd, log_file=log_file)
        self.pool.log_debug('live media outputs: %s' % (output))
        if output['retcode'] != 0:
            self.pool.log_error('Live media task failed.')
            raise RuntimeError('Live media task failed: %s. See %s for more details.'
                               % (output['task_id'], log_file))
        return output

    def _get_cmd(self, koji_wrapper, config):
        """Replace `arches` (as list) with `arch` as a comma-separated string."""
        copy = dict(config)
        copy['arch'] = ','.join(copy.pop('arches', []))
        copy['can_fail'] = self.failable_arches
        return koji_wrapper.get_live_media_cmd(copy)

    def worker(self, compose, variant, subvariant, config):
        msg = ('Live media: %s (arches: %s, variant: %s, subvariant: %s)'
               % (config['name'], ' '.join(config['arches']), variant.uid, subvariant))
        self.pool.log_info('[BEGIN] %s' % msg)

        koji_wrapper = KojiWrapper(compose.conf['koji_profile'])
        cmd = self._get_cmd(koji_wrapper, config)

        log_file = self._get_log_file(compose, variant, subvariant, config)
        output = self._run_command(koji_wrapper, cmd, compose, log_file)

        # collect results and update manifest
        image_infos = []

        paths = koji_wrapper.get_image_paths(
            output['task_id'],
            callback=lambda arch: log_failed_task(compose, variant, arch, 'live-media', subvariant)
        )

        for arch, paths in paths.items():
            for path in paths:
                if path.endswith('.iso'):
                    image_infos.append({'path': path, 'arch': arch})

        if len(image_infos) < len(config['arches']) - len(self.failable_arches):
            self.pool.log_error(
                'Error in koji task %s. Expected to find at least one image '
                'for each required arch (%s). Got %s.'
                % (output['task_id'], len(config['arches']), len(image_infos)))
            raise RuntimeError('Image count mismatch in task %s.' % output['task_id'])

        linker = Linker(logger=self.pool._logger)
        link_type = compose.conf["link_type"]
        for image_info in image_infos:
            image_dir = compose.paths.compose.iso_dir(image_info['arch'], variant)
            makedirs(image_dir)
            relative_image_dir = (
                compose.paths.compose.iso_dir(image_info['arch'], variant, relative=True)
            )

            # let's not change filename of koji outputs
            image_dest = os.path.join(image_dir, os.path.basename(image_info['path']))
            linker.link(image_info['path'], image_dest, link_type=link_type)

            # Update image manifest
            img = Image(compose.im)
            img.type = 'live'
            img.format = 'iso'
            img.path = os.path.join(relative_image_dir, os.path.basename(image_dest))
            img.mtime = get_mtime(image_dest)
            img.size = get_file_size(image_dest)
            img.arch = image_info['arch']
            img.disc_number = 1     # We don't expect multiple disks
            img.disc_count = 1
            img.bootable = True
            img.subvariant = subvariant
            setattr(img, 'can_fail', bool(self.failable_arches))
            setattr(img, 'deliverable', 'live-media')
            compose.im.add(variant=variant.uid, arch=image_info['arch'], image=img)

        self.pool.log_info('[DONE ] %s (task id: %s)' % (msg, output['task_id']))
