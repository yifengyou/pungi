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


import copy
import os
import time
import json

import productmd.composeinfo
import productmd.treeinfo
from productmd.common import get_major_version
from kobo.shortcuts import relative_path, compute_file_checksums

from pungi.compose_metadata.discinfo import write_discinfo as create_discinfo
from pungi.compose_metadata.discinfo import write_media_repo as create_media_repo


def get_description(compose, variant, arch):
    if "release_discinfo_description" in compose.conf:
        result = compose.conf["release_discinfo_description"]
    elif variant.type == "layered-product":
        # we need to make sure the layered product behaves as it was composed separately
        result = "%s %s for %s %s" % (variant.release_name, variant.release_version, compose.conf["release_name"], get_major_version(compose.conf["release_version"]))
    else:
        result = "%s %s" % (compose.conf["release_name"], compose.conf["release_version"])
        if compose.conf.get("base_product_name", ""):
            result += " for %s %s" % (compose.conf["base_product_name"], compose.conf["base_product_version"])

    result = result % {"variant_name": variant.name, "arch": arch}
    return result


def write_discinfo(compose, arch, variant):
    if variant.type == "addon":
        return
    os_tree = compose.paths.compose.os_tree(arch, variant)
    path = os.path.join(os_tree, ".discinfo")
    # description = get_volid(compose, arch, variant)
    description = get_description(compose, variant, arch)
    return create_discinfo(path, description, arch)


def write_media_repo(compose, arch, variant, timestamp=None):
    if variant.type == "addon":
        return
    os_tree = compose.paths.compose.os_tree(arch, variant)
    path = os.path.join(os_tree, "media.repo")
    # description = get_volid(compose, arch, variant)
    description = get_description(compose, variant, arch)
    return create_media_repo(path, description, timestamp)


def compose_to_composeinfo(compose):
    ci = productmd.composeinfo.ComposeInfo()

    # compose
    ci.compose.id = compose.compose_id
    ci.compose.type = compose.compose_type
    ci.compose.date = compose.compose_date
    ci.compose.respin = compose.compose_respin
    ci.compose.label = compose.compose_label
    ci.compose.final = compose.supported

    # product
    ci.release.name = compose.conf["release_name"]
    ci.release.version = compose.conf["release_version"]
    ci.release.short = compose.conf["release_short"]
    ci.release.is_layered = True if compose.conf.get("base_product_name", "") else False
    ci.release.type = compose.conf["release_type"].lower()
    ci.release.internal = bool(compose.conf["release_internal"])

    # base product
    if ci.release.is_layered:
        ci.base_product.name = compose.conf["base_product_name"]
        ci.base_product.version = compose.conf["base_product_version"]
        ci.base_product.short = compose.conf["base_product_short"]
        ci.base_product.type = compose.conf["base_product_type"].lower()

    def dump_variant(variant, parent=None):
        var = productmd.composeinfo.Variant(ci)

        tree_arches = compose.conf.get("tree_arches")
        if tree_arches and not (set(variant.arches) & set(tree_arches)):
            return None

        # variant details
        # remove dashes from variant ID, rely on productmd verification
        var.id = variant.id.replace("-", "")
        var.uid = variant.uid
        var.name = variant.name
        var.type = variant.type
        var.arches = set(variant.arches)

        if var.type == "layered-product":
            var.release.name = variant.release_name
            var.release.short = variant.release_short
            var.release.version = variant.release_version
            var.release.is_layered = True
            var.release.type = ci.release.type

        for arch in variant.arches:
            # paths: binaries
            var.paths.os_tree[arch] = relative_path(compose.paths.compose.os_tree(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.repository[arch] = relative_path(compose.paths.compose.repository(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.packages[arch] = relative_path(compose.paths.compose.packages(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            iso_dir = compose.paths.compose.iso_dir(arch=arch, variant=variant, create_dir=False) or ""
            if iso_dir and os.path.isdir(os.path.join(compose.paths.compose.topdir(), iso_dir)):
                var.paths.isos[arch] = relative_path(iso_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            jigdo_dir = compose.paths.compose.jigdo_dir(arch=arch, variant=variant, create_dir=False) or ""
            if jigdo_dir and os.path.isdir(os.path.join(compose.paths.compose.topdir(), jigdo_dir)):
                var.paths.jigdos[arch] = relative_path(jigdo_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")

            # paths: sources
            var.paths.source_tree[arch] = relative_path(compose.paths.compose.os_tree(arch="source", variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.source_repository[arch] = relative_path(compose.paths.compose.repository(arch="source", variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.source_packages[arch] = relative_path(compose.paths.compose.packages(arch="source", variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            source_iso_dir = compose.paths.compose.iso_dir(arch="source", variant=variant, create_dir=False) or ""
            if source_iso_dir and os.path.isdir(os.path.join(compose.paths.compose.topdir(), source_iso_dir)):
                var.paths.source_isos[arch] = relative_path(source_iso_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            source_jigdo_dir = compose.paths.compose.jigdo_dir(arch="source", variant=variant, create_dir=False) or ""
            if source_jigdo_dir and os.path.isdir(os.path.join(compose.paths.compose.topdir(), source_jigdo_dir)):
                var.paths.source_jigdos[arch] = relative_path(source_jigdo_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")

            # paths: debug
            var.paths.debug_tree[arch] = relative_path(compose.paths.compose.debug_tree(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.debug_repository[arch] = relative_path(compose.paths.compose.debug_repository(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            var.paths.debug_packages[arch] = relative_path(compose.paths.compose.debug_packages(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            '''
            # XXX: not suported (yet?)
            debug_iso_dir = compose.paths.compose.debug_iso_dir(arch=arch, variant=variant) or ""
            if debug_iso_dir:
                var.debug_iso_dir[arch] = relative_path(debug_iso_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            debug_jigdo_dir = compose.paths.compose.debug_jigdo_dir(arch=arch, variant=variant) or ""
            if debug_jigdo_dir:
                var.debug_jigdo_dir[arch] = relative_path(debug_jigdo_dir, compose.paths.compose.topdir().rstrip("/") + "/").rstrip("/")
            '''

        for v in variant.get_variants(recursive=False):
            x = dump_variant(v, parent=variant)
            if x is not None:
                var.add(x)
        return var

    for variant_id in sorted(compose.variants):
        variant = compose.variants[variant_id]
        v = dump_variant(variant)
        if v is not None:
            ci.variants.add(v)
    return ci


def write_compose_info(compose):
    ci = compose_to_composeinfo(compose)

    msg = "Writing composeinfo"
    compose.log_info("[BEGIN] %s" % msg)

    path = compose.paths.compose.metadata("composeinfo.json")
    # make a copy of composeinfo and modify the copy
    # if any path in variant paths doesn't exist or just an empty
    # dir, set it to None, then it won't be dumped.
    ci_copy = copy.deepcopy(ci)
    for variant in ci_copy.variants.variants.values():
        for field in variant.paths._fields:
            field_paths = getattr(variant.paths, field)
            for arch, dirpath in field_paths.items():
                dirpath = os.path.join(compose.paths.compose.topdir(), dirpath)
                if not os.path.isdir(dirpath):
                    # If the directory does not exist, do not include the path
                    # in metadata.
                    field_paths[arch] = None
    ci_copy.dump(path)

    compose.log_info("[DONE ] %s" % msg)


def write_tree_info(compose, arch, variant, timestamp=None, bi=None):
    if variant.type in ("addon", ) or variant.is_empty:
        return

    if not timestamp:
        timestamp = int(time.time())
    else:
        timestamp = int(timestamp)

    os_tree = compose.paths.compose.os_tree(arch=arch, variant=variant).rstrip("/") + "/"

    ti = productmd.treeinfo.TreeInfo()
    # load from buildinstall .treeinfo

    if variant.type == "layered-product":
        # we need to make sure the layered product behaves as it was composed separately

        # release
        # TODO: read from variants.xml
        ti.release.name = variant.release_name
        ti.release.version = variant.release_version
        ti.release.short = variant.release_short
        ti.release.is_layered = True
        ti.release.type = compose.conf["release_type"].lower()

        # base product
        ti.base_product.name = compose.conf["release_name"]
        if "." in compose.conf["release_version"]:
            # remove minor version if present
            ti.base_product.version = get_major_version(compose.conf["release_version"])
        else:
            ti.base_product.version = compose.conf["release_version"]
        ti.base_product.short = compose.conf["release_short"]
    else:
        # release
        ti.release.name = compose.conf["release_name"]
        ti.release.version = compose.conf["release_version"]
        ti.release.short = compose.conf["release_short"]
        ti.release.is_layered = True if compose.conf.get("base_product_name", "") else False
        ti.release.type = compose.conf["release_type"].lower()

        # base product
        if ti.release.is_layered:
            ti.base_product.name = compose.conf["base_product_name"]
            ti.base_product.version = compose.conf["base_product_version"]
            ti.base_product.short = compose.conf["base_product_short"]

    # tree
    ti.tree.arch = arch
    ti.tree.build_timestamp = timestamp
    # ti.platforms

    # main variant
    var = productmd.treeinfo.Variant(ti)
    if variant.type == "layered-product":
        var.id = variant.parent.id
        var.uid = variant.parent.uid
        var.name = variant.parent.name
        var.type = "variant"
    else:
        # remove dashes from variant ID, rely on productmd verification
        var.id = variant.id.replace("-", "")
        var.uid = variant.uid
        var.name = variant.name
        var.type = variant.type

    var.paths.packages = relative_path(compose.paths.compose.packages(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", os_tree).rstrip("/") or "."
    var.paths.repository = relative_path(compose.paths.compose.repository(arch=arch, variant=variant, create_dir=False).rstrip("/") + "/", os_tree).rstrip("/") or "."

    ti.variants.add(var)

    repomd_path = os.path.join(var.paths.repository, "repodata", "repomd.xml")
    if os.path.isfile(repomd_path):
        ti.checksums.add(repomd_path, "sha256", root_dir=os_tree)

    for i in variant.get_variants(types=["addon"], arch=arch):
        addon = productmd.treeinfo.Variant(ti)
        addon.id = i.id
        addon.uid = i.uid
        addon.name = i.name
        addon.type = i.type

        os_tree = compose.paths.compose.os_tree(arch=arch, variant=i).rstrip("/") + "/"
        addon.paths.packages = relative_path(compose.paths.compose.packages(arch=arch, variant=i, create_dir=False).rstrip("/") + "/", os_tree).rstrip("/") or "."
        addon.paths.repository = relative_path(compose.paths.compose.repository(arch=arch, variant=i, create_dir=False).rstrip("/") + "/", os_tree).rstrip("/") or "."
        var.add(addon)

        repomd_path = os.path.join(addon.paths.repository, "repodata", "repomd.xml")
        if os.path.isfile(repomd_path):
            ti.checksums.add(repomd_path, "sha256", root_dir=os_tree)

    class LoraxProduct(productmd.treeinfo.Release):
        def _validate_short(self):
            # HACK: set self.short so .treeinfo produced by lorax can be read
            if not self.short:
                self.short = compose.conf["release_short"]

    class LoraxTreeInfo(productmd.treeinfo.TreeInfo):
        def __init__(self, *args, **kwargs):
            super(LoraxTreeInfo, self).__init__(*args, **kwargs)
            self.release = LoraxProduct(self)

    # images
    if variant.type == "variant" and bi.succeeded(variant, arch):
        os_tree = compose.paths.compose.os_tree(arch, variant)

        # clone all but 'general' sections from buildinstall .treeinfo

        bi_dir = compose.paths.work.buildinstall_dir(arch)
        if compose.conf.get('buildinstall_method') == 'lorax':
            # The .treeinfo file produced by lorax is nested in variant
            # subdirectory. Legacy buildinstall runs once per arch, so there is
            # only one file.
            bi_dir = os.path.join(bi_dir, variant.uid)
        bi_treeinfo = os.path.join(bi_dir, ".treeinfo")

        if os.path.exists(bi_treeinfo):
            bi_ti = LoraxTreeInfo()
            bi_ti.load(bi_treeinfo)

            # stage2 - mainimage
            if bi_ti.stage2.mainimage:
                ti.stage2.mainimage = bi_ti.stage2.mainimage
                ti.checksums.add(ti.stage2.mainimage, "sha256", root_dir=os_tree)

            # stage2 - instimage
            if bi_ti.stage2.instimage:
                ti.stage2.instimage = bi_ti.stage2.instimage
                ti.checksums.add(ti.stage2.instimage, "sha256", root_dir=os_tree)

            # images
            for platform in bi_ti.images.images:
                ti.images.images[platform] = {}
                ti.tree.platforms.add(platform)
                for image, path in bi_ti.images.images[platform].items():
                    if not path:
                        # The .treeinfo file contains an image without a path.
                        # We can't add that.
                        continue
                    ti.images.images[platform][image] = path
                    ti.checksums.add(path, "sha256", root_dir=os_tree)

        # add product.img to images-$arch
        product_img = os.path.join(os_tree, "images", "product.img")
        product_img_relpath = relative_path(product_img, os_tree.rstrip("/") + "/")
        if os.path.isfile(product_img):
            for platform in ti.images.images:
                ti.images.images[platform]["product.img"] = product_img_relpath
                ti.checksums.add(product_img_relpath, "sha256", root_dir=os_tree)

    path = os.path.join(compose.paths.compose.os_tree(arch=arch, variant=variant), ".treeinfo")
    compose.log_info("Writing treeinfo: %s" % path)
    ti.dump(path)


def write_extra_files(tree_path, files, checksum_type='sha256', logger=None):
    """
    Write the metadata for all extra files added to the compose.

    :param tree_path:
        Root of the tree to write the ``extra_files.json`` metadata file for.

    :param files:
        A list of files that should be included in the metadata file. These
        should be paths that are relative to ``tree_path``.

    :return:
        Path to the metadata file written.
    """
    metadata_path = os.path.join(tree_path, 'extra_files.json')
    if logger:
        logger.info('Calculating content of {metadata}'.format(metadata=metadata_path))
    metadata = {'header': {'version': '1.0'}, 'data': []}
    for f in files:
        if logger:
            logger.debug('Processing {file}'.format(file=f))
        path = os.path.join(tree_path, f)
        try:
            checksum = compute_file_checksums(path, checksum_type)
        except IOError as exc:
            file = os.path.relpath(exc.filename, '/'.join(tree_path.split('/')[:-3]))
            raise RuntimeError('Failed to calculate checksum for %s: %s' % (file, exc.strerror))
        entry = {
            'file': f,
            'checksums': checksum,
            'size': os.path.getsize(path),
        }
        metadata['data'].append(entry)

    if logger:
        logger.info('Writing {metadata}'.format(metadata=metadata_path))

    with open(metadata_path, 'w') as fd:
        json.dump(metadata, fd, sort_keys=True, indent=4, separators=(',', ': '))
    return metadata_path
