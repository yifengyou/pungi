# -*- coding: utf-8 -*-

import copy
import os
import time
from kobo import shortcuts

from pungi.util import makedirs, get_mtime, get_file_size, failable, log_failed_task
from pungi.util import translate_path, get_repo_urls, version_generator
from pungi.phases import base
from pungi.linker import Linker
from pungi.wrappers.kojiwrapper import KojiWrapper
from kobo.threads import ThreadPool, WorkerThread
from kobo.shortcuts import force_list
from productmd.images import Image


# This is a mapping from formats to file extensions. The format is what koji
# image-build command expects as argument, and the extension is what the file
# name will be ending with. The extensions are used to filter out which task
# results will be pulled into the compose.
EXTENSIONS = {
    'docker': ['tar.gz', 'tar.xz'],
    'liveimg-squashfs': ['liveimg.squashfs'],
    'qcow': ['qcow'],
    'qcow2': ['qcow2'],
    'raw': ['raw'],
    'raw-xz': ['raw.xz'],
    'rhevm-ova': ['rhevm.ova'],
    'tar-gz': ['tar.gz'],
    'vagrant-hyperv': ['vagrant-hyperv.box'],
    'vagrant-libvirt': ['vagrant-libvirt.box'],
    'vagrant-virtualbox': ['vagrant-virtualbox.box'],
    'vagrant-vmware-fusion': ['vagrant-vmware-fusion.box'],
    'vdi': ['vdi'],
    'vmdk': ['vmdk'],
    'vpc': ['vhd'],
    'vsphere-ova': ['vsphere.ova'],
}


class ImageBuildPhase(base.PhaseLoggerMixin, base.ImageConfigMixin, base.ConfigGuardedPhase):
    """class for wrapping up koji image-build"""
    name = "image_build"

    def __init__(self, compose):
        super(ImageBuildPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def _get_install_tree(self, image_conf, variant):
        """
        Get a path to os tree for a variant specified in `install_tree_from` or
        current variant. If the config is set, it will be removed from the
        dict.
        """
        if variant.type != 'variant':
            # Buildinstall only runs for top-level variants. Nested variants
            # need to re-use install tree from parent.
            variant = variant.parent

        install_tree_from = image_conf.pop('install_tree_from', variant.uid)
        if '://' in install_tree_from:
            # It's a URL, return it unchanged
            return install_tree_from
        if install_tree_from.startswith("/"):
            # It's a path on local filesystem.
            return translate_path(self.compose, install_tree_from)

        install_tree_source = self.compose.all_variants.get(install_tree_from)
        if not install_tree_source:
            raise RuntimeError(
                'There is no variant %s to get install tree from when building image for %s.'
                % (install_tree_from, variant.uid))
        return translate_path(
            self.compose,
            self.compose.paths.compose.os_tree('$arch', install_tree_source, create_dir=False)
        )

    def _get_repo(self, image_conf, variant):
        """
        Get a comma separated list of repos. First included are those
        explicitly listed in config, followed by by repo for current variant
        if it's not included in the list already.
        """
        repos = shortcuts.force_list(image_conf.get('repo', []))

        if not variant.is_empty and variant.uid not in repos:
            repos.append(variant.uid)

        return ",".join(get_repo_urls(self.compose, repos, arch='$arch'))

    def _get_arches(self, image_conf, arches):
        if 'arches' in image_conf['image-build']:
            arches = set(image_conf['image-build'].get('arches', [])) & arches
        return sorted(arches)

    def _set_release(self, image_conf):
        """If release is set explicitly to None, replace it with date and respin."""
        if 'release' in image_conf:
            image_conf['release'] = (version_generator(self.compose, image_conf['release']) or
                                     self.compose.image_release)

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != 'src'])

            for image_conf in self.get_config_block(variant):
                # We will modify the data, so we need to make a copy to
                # prevent problems in next iteration where the original
                # value is needed.
                image_conf = copy.deepcopy(image_conf)

                # image_conf is passed to get_image_build_cmd as dict

                image_conf["image-build"]['arches'] = self._get_arches(image_conf, arches)
                if not image_conf["image-build"]['arches']:
                    continue

                # Replace possible ambiguous ref name with explicit hash.
                ksurl = self.get_ksurl(image_conf['image-build'])
                if ksurl:
                    image_conf["image-build"]['ksurl'] = ksurl

                image_conf["image-build"]["variant"] = variant

                image_conf["image-build"]["install_tree"] = self._get_install_tree(image_conf['image-build'], variant)

                release = self.get_release(image_conf['image-build'])
                if release:
                    image_conf['image-build']['release'] = release

                image_conf['image-build']['version'] = self.get_version(image_conf['image-build'])
                image_conf['image-build']['target'] = self.get_config(image_conf['image-build'], 'target')

                # Pungi config can either contain old [(format, suffix)], or
                # just list of formats, or a single format.
                formats = []
                for format in force_list(image_conf["image-build"]["format"]):
                    formats.append(format[0] if isinstance(format, (tuple, list)) else format)
                image_conf["image-build"]["format"] = formats
                image_conf["image-build"]['repo'] = self._get_repo(image_conf['image-build'], variant)

                can_fail = image_conf['image-build'].pop('failable', [])
                if can_fail == ['*']:
                    can_fail = image_conf['image-build']['arches']
                if can_fail:
                    image_conf['image-build']['can_fail'] = sorted(can_fail)

                cmd = {
                    "image_conf": image_conf,
                    "conf_file": self.compose.paths.work.image_build_conf(
                        image_conf["image-build"]['variant'],
                        image_name=image_conf["image-build"]['name'],
                        image_type='-'.join(formats),
                        arches=image_conf["image-build"]['arches'],
                    ),
                    "image_dir": self.compose.paths.compose.image_dir(variant),
                    "relative_image_dir": self.compose.paths.compose.image_dir(
                        variant, relative=True
                    ),
                    "link_type": self.compose.conf["link_type"],
                    "scratch": image_conf['image-build'].pop('scratch', False),
                }
                self.pool.add(CreateImageBuildThread(self.pool))
                self.pool.queue_put((self.compose, cmd))

        self.pool.start()


class CreateImageBuildThread(WorkerThread):
    def fail(self, compose, cmd):
        self.pool.log_error("CreateImageBuild failed.")

    def process(self, item, num):
        compose, cmd = item
        variant = cmd["image_conf"]["image-build"]["variant"]
        subvariant = cmd["image_conf"]["image-build"].get("subvariant", variant.uid)
        self.failable_arches = cmd["image_conf"]['image-build'].get('can_fail', '')
        self.can_fail = self.failable_arches == cmd['image_conf']['image-build']['arches']
        with failable(compose, self.can_fail, variant, '*', 'image-build', subvariant,
                      logger=self.pool._logger):
            self.worker(num, compose, variant, subvariant, cmd)

    def worker(self, num, compose, variant, subvariant, cmd):
        arches = cmd["image_conf"]["image-build"]['arches']
        formats = '-'.join(cmd['image_conf']['image-build']['format'])
        dash_arches = '-'.join(arches)
        log_file = compose.paths.log.log_file(
            dash_arches,
            "imagebuild-%s-%s-%s" % (variant.uid, subvariant, formats)
        )
        msg = ("Creating image (formats: %s, arches: %s, variant: %s, subvariant: %s)"
               % (formats, dash_arches, variant, subvariant))
        self.pool.log_info("[BEGIN] %s" % msg)

        koji_wrapper = KojiWrapper(compose.conf["koji_profile"])

        # writes conf file for koji image-build
        self.pool.log_info("Writing image-build config for %s.%s into %s" % (
            variant, dash_arches, cmd["conf_file"]))

        koji_cmd = koji_wrapper.get_image_build_cmd(cmd["image_conf"],
                                                    conf_file_dest=cmd["conf_file"],
                                                    scratch=cmd['scratch'])

        # avoid race conditions?
        # Kerberos authentication failed: Permission denied in replay cache code (-1765328215)
        time.sleep(num * 3)
        output = koji_wrapper.run_blocking_cmd(koji_cmd, log_file=log_file)
        self.pool.log_debug("build-image outputs: %s" % (output))
        if output["retcode"] != 0:
            self.fail(compose, cmd)
            raise RuntimeError("ImageBuild task failed: %s. See %s for more details."
                               % (output["task_id"], log_file))

        # copy image to images/
        image_infos = []

        paths = koji_wrapper.get_image_paths(
            output["task_id"],
            callback=lambda arch: log_failed_task(compose, variant, arch, 'image-build', subvariant)
        )

        for arch, paths in paths.items():
            for path in paths:
                for format in cmd['image_conf']['image-build']['format']:
                    for suffix in EXTENSIONS[format]:
                        if path.endswith(suffix):
                            image_infos.append({'path': path,
                                                'suffix': suffix,
                                                'type': format,
                                                'arch': arch})
                            break

        # The usecase here is that you can run koji image-build with multiple --format
        # It's ok to do it serialized since we're talking about max 2 images per single
        # image_build record
        linker = Linker(logger=self.pool._logger)
        for image_info in image_infos:
            image_dir = cmd["image_dir"] % {"arch": image_info['arch']}
            makedirs(image_dir)
            relative_image_dir = cmd["relative_image_dir"] % {"arch": image_info['arch']}

            # let's not change filename of koji outputs
            image_dest = os.path.join(image_dir, os.path.basename(image_info['path']))
            linker.link(image_info['path'], image_dest, link_type=cmd["link_type"])

            # Update image manifest
            img = Image(compose.im)
            img.type = image_info['type']
            img.format = image_info['suffix']
            img.path = os.path.join(relative_image_dir, os.path.basename(image_dest))
            img.mtime = get_mtime(image_dest)
            img.size = get_file_size(image_dest)
            img.arch = image_info['arch']
            img.disc_number = 1     # We don't expect multiple disks
            img.disc_count = 1
            img.bootable = False
            img.subvariant = subvariant
            setattr(img, 'can_fail', self.can_fail)
            setattr(img, 'deliverable', 'image-build')
            compose.im.add(variant=variant.uid, arch=image_info['arch'], image=img)

        self.pool.log_info("[DONE ] %s (task id: %s)" % (msg, output['task_id']))
