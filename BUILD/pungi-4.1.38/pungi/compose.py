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


__all__ = (
    "Compose",
)


import errno
import os
import time
import tempfile
import shutil
import json

import kobo.log
from productmd.composeinfo import ComposeInfo
from productmd.images import Images
from dogpile.cache import make_region


from pungi.graph import SimpleAcyclicOrientedGraph
from pungi.wrappers.variants import VariantsXmlParser
from pungi.paths import Paths
from pungi.wrappers.scm import get_file_from_scm
from pungi.util import (
    makedirs, get_arch_variant_data, get_format_substs, get_variant_data
)
from pungi.metadata import compose_to_composeinfo

try:
    # This is available since productmd >= 1.18
    # TODO: remove this once the version is distributed widely enough
    from productmd.composeinfo import SUPPORTED_MILESTONES
except ImportError:
    SUPPORTED_MILESTONES = ["RC", "Update", "SecurityFix"]


def get_compose_dir(topdir, conf, compose_type="production", compose_date=None, compose_respin=None, compose_label=None, already_exists_callbacks=None):
    already_exists_callbacks = already_exists_callbacks or []

    # create an incomplete composeinfo to generate compose ID
    ci = ComposeInfo()
    ci.release.name = conf["release_name"]
    ci.release.short = conf["release_short"]
    ci.release.version = conf["release_version"]
    ci.release.is_layered = True if conf.get("base_product_name", "") else False
    ci.release.type = conf.get("release_type", "ga").lower()
    ci.release.internal = bool(conf.get("release_internal", False))
    if ci.release.is_layered:
        ci.base_product.name = conf["base_product_name"]
        ci.base_product.short = conf["base_product_short"]
        ci.base_product.version = conf["base_product_version"]
        ci.base_product.type = conf.get("base_product_type", "ga").lower()

    ci.compose.label = compose_label
    ci.compose.type = compose_type
    ci.compose.date = compose_date or time.strftime("%Y%m%d", time.localtime())
    ci.compose.respin = compose_respin or 0

    while 1:
        ci.compose.id = ci.create_compose_id()

        compose_dir = os.path.join(topdir, ci.compose.id)

        exists = False
        # TODO: callbacks to determine if a composeid was already used
        # for callback in already_exists_callbacks:
        #     if callback(data):
        #         exists = True
        #         break

        # already_exists_callbacks fallback: does target compose_dir exist?
        try:
            os.makedirs(compose_dir)
        except OSError as ex:
            if ex.errno == errno.EEXIST:
                exists = True
            else:
                raise

        if exists:
            ci.compose.respin += 1
            continue
        break

    with open(os.path.join(compose_dir, "COMPOSE_ID"), "w") as f:
        f.write(ci.compose.id)
    work_dir = os.path.join(compose_dir, "work", "global")
    makedirs(work_dir)
    ci.dump(os.path.join(work_dir, "composeinfo-base.json"))
    return compose_dir


class Compose(kobo.log.LoggingBase):
    def __init__(self, conf, topdir, debug=False, skip_phases=None, just_phases=None, old_composes=None, koji_event=None, supported=False, logger=None, notifier=None):
        kobo.log.LoggingBase.__init__(self, logger)
        # TODO: check if minimal conf values are set
        self.conf = conf
        # This is a dict mapping UID to Variant objects. It only contains top
        # level variants.
        self.variants = {}
        # This is a similar mapping, but contains even nested variants.
        self.all_variants = {}
        self.topdir = os.path.abspath(topdir)
        self.skip_phases = skip_phases or []
        self.just_phases = just_phases or []
        self.old_composes = old_composes or []
        self.koji_event = koji_event or conf.get("koji_event")
        self.notifier = notifier

        # intentionally upper-case (visible in the code)
        self.DEBUG = debug

        # path definitions
        self.paths = Paths(self)

        # Set up logging to file
        if logger:
            kobo.log.add_file_logger(logger, self.paths.log.log_file("global", "pungi.log"))

        # to provide compose_id, compose_date and compose_respin
        self.ci_base = ComposeInfo()
        self.ci_base.load(os.path.join(self.paths.work.topdir(arch="global"), "composeinfo-base.json"))

        self.supported = supported
        if self.compose_label and self.compose_label.split("-")[0] in SUPPORTED_MILESTONES:
            self.log_info("Automatically setting 'supported' flag due to label: %s." % self.compose_label)
            self.supported = True

        self.im = Images()
        if self.DEBUG:
            try:
                self.im.load(self.paths.compose.metadata("images.json"))
            except RuntimeError:
                pass
            # images.json doesn't exists
            except IOError:
                pass
            # images.json is not a valid json file, for example, it's an empty file
            except ValueError:
                pass
        self.im.compose.id = self.compose_id
        self.im.compose.type = self.compose_type
        self.im.compose.date = self.compose_date
        self.im.compose.respin = self.compose_respin
        self.im.metadata_path = self.paths.compose.metadata()

        # Stores list of deliverables that failed, but did not abort the
        # compose.
        # {deliverable: [(Variant.uid, arch, subvariant)]}
        self.failed_deliverables = {}
        self.attempted_deliverables = {}
        self.required_deliverables = {}

        if self.conf.get("dogpile_cache_backend", None):
            self.cache_region = make_region().configure(
                self.conf.get("dogpile_cache_backend"),
                expiration_time=self.conf.get("dogpile_cache_expiration_time", 3600),
                arguments=self.conf.get("dogpile_cache_arguments", {})
            )
        else:
            self.cache_region = make_region().configure('dogpile.cache.null')

    get_compose_dir = staticmethod(get_compose_dir)

    def __getitem__(self, name):
        return self.variants[name]

    @property
    def compose_id(self):
        return self.ci_base.compose.id

    @property
    def compose_date(self):
        return self.ci_base.compose.date

    @property
    def compose_respin(self):
        return self.ci_base.compose.respin

    @property
    def compose_type(self):
        return self.ci_base.compose.type

    @property
    def compose_type_suffix(self):
        return self.ci_base.compose.type_suffix

    @property
    def compose_label(self):
        return self.ci_base.compose.label

    @property
    def compose_label_major_version(self):
        return self.ci_base.compose.label_major_version

    @property
    def has_comps(self):
        return bool(self.conf.get("comps_file", False))

    @property
    def has_module_defaults(self):
        return bool(self.conf.get("module_defaults_dir", False))

    @property
    def config_dir(self):
        return os.path.dirname(self.conf._open_file or "")

    @property
    def should_create_yum_database(self):
        """Explicit configuration trumps all. Otherwise check gather backend
        and only create it for Yum.
        """
        config = self.conf.get('createrepo_database')
        if config is not None:
            return config
        return self.conf['gather_backend'] == 'yum'

    def read_variants(self):
        # TODO: move to phases/init ?
        variants_file = self.paths.work.variants_file(arch="global")
        msg = "Writing variants file: %s" % variants_file

        if self.DEBUG and os.path.isfile(variants_file):
            self.log_warning("[SKIP ] %s" % msg)
        else:
            scm_dict = self.conf["variants_file"]
            if isinstance(scm_dict, dict):
                file_name = os.path.basename(scm_dict["file"])
                if scm_dict["scm"] == "file":
                    scm_dict["file"] = os.path.join(self.config_dir, os.path.basename(scm_dict["file"]))
            else:
                file_name = os.path.basename(scm_dict)
                scm_dict = os.path.join(self.config_dir, os.path.basename(scm_dict))

            self.log_debug(msg)
            tmp_dir = self.mkdtemp(prefix="variants_file_")
            get_file_from_scm(scm_dict, tmp_dir, logger=self._logger)
            shutil.copy2(os.path.join(tmp_dir, file_name), variants_file)
            shutil.rmtree(tmp_dir)

        tree_arches = self.conf.get("tree_arches", None)
        tree_variants = self.conf.get("tree_variants", None)
        with open(variants_file, "r") as file_obj:
            parser = VariantsXmlParser(file_obj, tree_arches, tree_variants, logger=self._logger)
            self.variants = parser.parse()

        self.all_variants = {}
        for variant in self.get_variants():
            self.all_variants[variant.uid] = variant

        # populate ci_base with variants - needed for layered-products (compose_id)
        ####FIXME - compose_to_composeinfo is no longer needed and has been
        ####        removed, but I'm not entirely sure what this is needed for
        ####        or if it is at all
        self.ci_base = compose_to_composeinfo(self)

    def get_variants(self, types=None, arch=None):
        result = []
        for i in self.variants.values():
            if (not types or i.type in types) and (not arch or arch in i.arches):
                result.append(i)
            result.extend(i.get_variants(types=types, arch=arch))
        return sorted(set(result))

    def get_arches(self):
        result = set()
        for variant in self.get_variants():
            for arch in variant.arches:
                result.add(arch)
        return sorted(result)

    @property
    def status_file(self):
        """Path to file where the compose status will be stored."""
        if not hasattr(self, '_status_file'):
            self._status_file = os.path.join(self.topdir, 'STATUS')
        return self._status_file

    def _log_failed_deliverables(self):
        for kind, data in self.failed_deliverables.items():
            for variant, arch, subvariant in data:
                self.log_info('Failed %s on variant <%s>, arch <%s>, subvariant <%s>.'
                              % (kind, variant, arch, subvariant))
        log = os.path.join(self.paths.log.topdir('global'), 'deliverables.json')
        with open(log, 'w') as f:
            json.dump({'required': self.required_deliverables,
                       'failed': self.failed_deliverables,
                       'attempted': self.attempted_deliverables},
                      f, indent=4)

    def write_status(self, stat_msg):
        if stat_msg not in ("STARTED", "FINISHED", "DOOMED", "TERMINATED"):
            self.log_warning("Writing nonstandard compose status: %s" % stat_msg)
        old_status = self.get_status()
        if stat_msg == old_status:
            return
        if old_status == "FINISHED":
            msg = "Could not modify a FINISHED compose: %s" % self.topdir
            self.log_error(msg)
            raise RuntimeError(msg)

        if stat_msg == 'FINISHED' and self.failed_deliverables:
            stat_msg = 'FINISHED_INCOMPLETE'

        self._log_failed_deliverables()

        with open(self.status_file, "w") as f:
            f.write(stat_msg + "\n")

        if self.notifier:
            self.notifier.send('status-change', status=stat_msg)

    def get_status(self):
        if not os.path.isfile(self.status_file):
            return
        return open(self.status_file, "r").read().strip()

    def get_image_name(self, arch, variant, disc_type='dvd',
                       disc_num=1, suffix='.iso', format=None):
        """Create a filename for image with given parameters.

        :raises RuntimeError: when unknown ``disc_type`` is given
        """
        default_format = "{compose_id}-{variant}-{arch}-{disc_type}{disc_num}{suffix}"
        format = format or self.conf.get('image_name_format', default_format)

        if isinstance(format, dict):
            conf = get_variant_data(self.conf, "image_name_format", variant)
            format = conf[0] if conf else default_format

        if arch == "src":
            arch = "source"

        if disc_num:
            disc_num = int(disc_num)
        else:
            disc_num = ""

        kwargs = {
            'arch': arch,
            'disc_type': disc_type,
            'disc_num': disc_num,
            'suffix': suffix
        }
        if variant.type == "layered-product":
            variant_uid = variant.parent.uid
            kwargs['compose_id'] = self.ci_base[variant.uid].compose_id
        else:
            variant_uid = variant.uid
        args = get_format_substs(self, variant=variant_uid, **kwargs)
        try:
            return (format % args).format(**args)
        except KeyError as err:
            raise RuntimeError('Failed to create image name: unknown format element: %s' % err)

    def can_fail(self, variant, arch, deliverable):
        """Figure out if deliverable can fail on variant.arch.

        Variant can be None.
        """
        failable = get_arch_variant_data(self.conf, 'failable_deliverables', arch, variant)
        return deliverable in failable

    def attempt_deliverable(self, variant, arch, kind, subvariant=None):
        """Log information about attempted deliverable."""
        variant_uid = variant.uid if variant else ''
        self.attempted_deliverables.setdefault(kind, []).append(
            (variant_uid, arch, subvariant))

    def require_deliverable(self, variant, arch, kind, subvariant=None):
        """Log information about attempted deliverable."""
        variant_uid = variant.uid if variant else ''
        self.required_deliverables.setdefault(kind, []).append(
            (variant_uid, arch, subvariant))

    def fail_deliverable(self, variant, arch, kind, subvariant=None):
        """Log information about failed deliverable."""
        variant_uid = variant.uid if variant else ''
        self.failed_deliverables.setdefault(kind, []).append(
            (variant_uid, arch, subvariant))

    @property
    def image_release(self):
        """Generate a value to pass to Koji as image release.

        If this compose has a label, the version from it will be used,
        otherwise we will create a string with date, compose type and respin.
        """
        if self.compose_label:
            milestone, release = self.compose_label.split('-')
            return release

        return '%s%s.%s' % (self.compose_date, self.ci_base.compose.type_suffix,
                            self.compose_respin)

    @property
    def image_version(self):
        """Generate a value to pass to Koji as image version.

        The value is based on release version. If compose has a label, the
        milestone from it is appended to the version (unless it is RC).
        """
        version = self.ci_base.release.version
        if self.compose_label and not self.compose_label.startswith('RC-'):
            milestone, release = self.compose_label.split('-')
            return '%s_%s' % (version, milestone)

        return version

    def mkdtemp(self, arch=None, variant=None, suffix="", prefix="tmp"):
        """
        Create and return a unique temporary directory under dir of
        <compose_topdir>/work/{global,<arch>}/tmp[-<variant>]/
        """
        path = os.path.join(self.paths.work.tmp_dir(arch=arch, variant=variant))
        return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=path)


def get_ordered_variant_uids(compose):
    if not hasattr(compose, "_ordered_variant_uids"):
        ordered_variant_uids = _prepare_variant_as_lookaside(compose)
        # Some variants were not mentioned in configuration value
        # 'variant_as_lookaside' and its run order is not crucial (that
        # means there are no dependencies inside this group). They will be
        # processed first. A-Z sorting is for reproducibility.
        unordered_variant_uids = sorted(
            set(compose.all_variants.keys()) - set(ordered_variant_uids)
        )
        setattr(
            compose,
            "_ordered_variant_uids",
            unordered_variant_uids + ordered_variant_uids
        )
    return getattr(compose, "_ordered_variant_uids")


def _prepare_variant_as_lookaside(compose):
    """
    Configuration value 'variant_as_lookaside' contains variant pairs <variant,
    its lookaside>. In that pair lookaside variant have to be processed first.
    Structure can be represented as a oriented graph. Its spanning line shows
    order how to process this set of variants.
    """
    variant_as_lookaside = compose.conf.get("variant_as_lookaside", [])
    graph = SimpleAcyclicOrientedGraph()
    for variant, lookaside_variant in variant_as_lookaside:
        try:
            graph.add_edge(variant, lookaside_variant)
        except ValueError as e:
            raise ValueError("There is a bad configuration in 'variant_as_lookaside': %s" % e)

    variant_processing_order = reversed(graph.prune_graph())
    return list(variant_processing_order)
