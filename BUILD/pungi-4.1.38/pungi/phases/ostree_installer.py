# -*- coding: utf-8 -*-

import os
from kobo.threads import ThreadPool, WorkerThread
import shutil
from productmd import images
from six.moves import shlex_quote
from kobo import shortcuts

from .base import ConfigGuardedPhase, PhaseLoggerMixin
from .. import util
from ..arch import get_valid_arches
from ..util import get_volid, get_repo_urls, version_generator, translate_path
from ..wrappers import iso, lorax, scm
from ..runroot import Runroot


class OstreeInstallerPhase(PhaseLoggerMixin, ConfigGuardedPhase):
    name = 'ostree_installer'

    def __init__(self, compose, buildinstall_phase):
        super(OstreeInstallerPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)
        self.bi = buildinstall_phase

    def validate(self):
        errors = []

        if not self.compose.conf['ostree_installer_overwrite'] and not self.bi.skip():
            for variant in self.compose.get_variants():
                for arch in variant.arches:
                    conf = util.get_arch_variant_data(self.compose.conf, self.name,
                                                      arch, variant)
                    if conf and not variant.is_empty:
                        errors.append('Can not generate ostree installer for %s.%s: '
                                      'it has buildinstall running already and the '
                                      'files would clash.' % (variant.uid, arch))

        if errors:
            raise ValueError('\n'.join(errors))

    def run(self):
        for variant in self.compose.get_variants():
            for arch in variant.arches:
                for conf in self.get_config_block(variant, arch):
                    self.pool.add(OstreeInstallerThread(self.pool))
                    self.pool.queue_put((self.compose, variant, arch, conf))

        self.pool.start()


class OstreeInstallerThread(WorkerThread):
    def process(self, item, num):
        compose, variant, arch, config = item
        self.num = num
        failable_arches = config.get('failable', [])
        self.can_fail = util.can_arch_fail(failable_arches, arch)
        with util.failable(compose, self.can_fail, variant, arch, 'ostree-installer',
                           logger=self.pool._logger):
            self.worker(compose, variant, arch, config)

    def worker(self, compose, variant, arch, config):
        msg = 'Ostree phase for variant %s, arch %s' % (variant.uid, arch)
        self.pool.log_info('[BEGIN] %s' % msg)
        self.logdir = compose.paths.log.topdir('%s/%s/ostree_installer-%s' % (arch, variant, self.num))

        repo_baseurl = compose.paths.work.arch_repo('$basearch', create_dir=False)
        repos = get_repo_urls(None,  # compose==None. Special value says that method should ignore deprecated variant-type repo
                              shortcuts.force_list(config['repo'])
                              + shortcuts.force_list(translate_path(compose, repo_baseurl)),
                              arch=arch,
                              logger=self.pool)
        if compose.has_comps:
            repos.append(
                translate_path(
                    compose,
                    compose.paths.work.comps_repo(
                        '$basearch', variant=variant, create_dir=False
                    ),
                )
            )
        repos = [url.replace('$arch', arch) for url in repos]
        output_dir = os.path.join(compose.paths.work.topdir(arch), variant.uid, 'ostree_installer')
        util.makedirs(os.path.dirname(output_dir))

        self.template_dir = os.path.join(compose.paths.work.topdir(arch), variant.uid, 'lorax_templates')
        self._clone_templates(config.get('template_repo'), config.get('template_branch'))
        disc_type = compose.conf['disc_types'].get('ostree', 'ostree')

        volid = get_volid(compose, arch, variant, disc_type=disc_type)
        self._run_ostree_cmd(compose, variant, arch, config, repos, output_dir, volid)

        filename = compose.get_image_name(arch, variant, disc_type=disc_type)
        self._copy_image(compose, variant, arch, filename, output_dir)
        self._add_to_manifest(compose, variant, arch, filename)
        self.pool.log_info('[DONE ] %s' % (msg))

    def _clone_templates(self, url, branch='master'):
        if not url:
            self.template_dir = None
            return
        scm.get_dir_from_scm({'scm': 'git', 'repo': url, 'branch': branch, 'dir': '.'},
                             self.template_dir, logger=self.pool._logger)

    def _get_release(self, compose, config):
        if 'release' in config:
            return version_generator(compose, config['release']) or compose.image_release
        return config.get('release', None)

    def _copy_image(self, compose, variant, arch, filename, output_dir):
        iso_path = compose.paths.compose.iso_path(arch, variant, filename)
        os_path = compose.paths.compose.os_tree(arch, variant)
        boot_iso = os.path.join(output_dir, 'images', 'boot.iso')

        util.copy_all(output_dir, os_path)
        try:
            os.link(boot_iso, iso_path)
        except OSError:
            shutil.copy2(boot_iso, iso_path)

    def _add_to_manifest(self, compose, variant, arch, filename):
        full_iso_path = compose.paths.compose.iso_path(arch, variant, filename)
        iso_path = compose.paths.compose.iso_path(arch, variant, filename, relative=True)
        implant_md5 = iso.get_implanted_md5(full_iso_path)

        img = images.Image(compose.im)
        img.path = iso_path
        img.mtime = util.get_mtime(full_iso_path)
        img.size = util.get_file_size(full_iso_path)
        img.arch = arch
        img.type = "dvd-ostree"
        img.format = "iso"
        img.disc_number = 1
        img.disc_count = 1
        img.bootable = True
        img.subvariant = variant.uid
        img.implant_md5 = implant_md5
        setattr(img, 'can_fail', self.can_fail)
        setattr(img, 'deliverable', 'ostree-installer')
        try:
            img.volume_id = iso.get_volume_id(full_iso_path)
        except RuntimeError:
            pass
        compose.im.add(variant.uid, arch, img)

    def _get_templates(self, config, key):
        """Retrieve all templates from configuration and make sure the paths
        are absolute. Raises RuntimeError if template repo is needed but not
        configured.
        """
        templates = []
        for template in config.get(key, []):
            if template[0] != '/':
                if not self.template_dir:
                    raise RuntimeError('Relative path to template without setting template_repo.')
                template = os.path.join(self.template_dir, template)
            templates.append(template)
        return templates

    def _run_ostree_cmd(self, compose, variant, arch, config, source_repo, output_dir, volid):
        lorax_wrapper = lorax.LoraxWrapper()
        lorax_cmd = lorax_wrapper.get_lorax_cmd(
            compose.conf['release_name'],
            compose.conf["release_version"],
            self._get_release(compose, config),
            repo_baseurl=source_repo,
            output_dir=output_dir,
            variant=variant.uid,
            nomacboot=True,
            volid=volid,
            buildarch=get_valid_arches(arch)[0],
            buildinstallpackages=config.get('installpkgs'),
            add_template=self._get_templates(config, 'add_template'),
            add_arch_template=self._get_templates(config, 'add_arch_template'),
            add_template_var=config.get('add_template_var'),
            add_arch_template_var=config.get('add_arch_template_var'),
            rootfs_size=config.get('rootfs_size'),
            is_final=compose.supported,
            log_dir=self.logdir,
        )
        cmd = 'rm -rf %s && %s' % (shlex_quote(output_dir),
                                   ' '.join([shlex_quote(x) for x in lorax_cmd]))

        packages = ['pungi', 'lorax', 'ostree']
        log_file = os.path.join(self.logdir, 'runroot.log')

        runroot = Runroot(compose)
        runroot.run(
            cmd, log_file=log_file, arch=arch, packages=packages,
            mounts=[compose.topdir], chown_paths=[output_dir],
            weight=compose.conf['runroot_weights'].get('ostree_installer'))
