# -*- coding: utf-8 -*-

import difflib
import errno
import os
import shutil
import tempfile
from collections import defaultdict

import mock
import six
from kobo.rpmlib import parse_nvr

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from pungi.util import get_arch_variant_data
from pungi import paths, checks
from pungi.module_util import Modulemd


class BaseTestCase(unittest.TestCase):
    def assertFilesEqual(self, fn1, fn2):
        with open(fn1, "rb") as f1:
            lines1 = f1.read().decode("utf-8").splitlines()
        with open(fn2, "rb") as f2:
            lines2 = f2.read().decode("utf-8").splitlines()
        diff = "\n".join(
            difflib.unified_diff(lines1, lines2, fromfile="EXPECTED", tofile="ACTUAL")
        )
        self.assertEqual(diff, "", "Files differ:\n" + diff)

    def assertFileContent(self, fn, expected):
        with open(fn, "rb") as f:
            lines = f.read().decode("utf-8").splitlines()
        diff = "\n".join(
            difflib.unified_diff(
                lines, expected.splitlines(), fromfile="EXPECTED", tofile="ACTUAL"
            )
        )
        self.assertEqual(diff, "", "Files differ:\n" + diff)


class PungiTestCase(BaseTestCase):
    def setUp(self):
        self.topdir = tempfile.mkdtemp()

    def tearDown(self):
        try:
            shutil.rmtree(self.topdir)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise

    def assertValidConfig(self, conf):
        self.assertEqual(checks.validate(conf, offline=True), ([], []))

    def _make_pkgset_phase(self, names):
        pkgsets = []
        for name in names:
            pkgset = mock.Mock(paths={})
            pkgset.name = name
            for arch in ("x86_64", "amd64"):
                pkgset.paths[arch] = os.path.join(
                    self.topdir, "work", arch, "repo", name
                )
            pkgsets.append(pkgset)
        return mock.Mock(package_sets=pkgsets)


class MockVariant(mock.Mock):
    def __init__(self, is_empty=False, name=None, *args, **kwargs):
        super(MockVariant, self).__init__(*args, is_empty=is_empty, **kwargs)
        self.parent = kwargs.get("parent", None)
        self.arch_mmds = {}
        self.module_uid_to_koji_tag = {}
        self.variants = {}
        self.pkgsets = set()
        self.modules = None
        self.modular_koji_tags = None
        self.name = name
        self.nsvc_to_pkgset = defaultdict(lambda: mock.Mock(rpms_by_arch={}))

    def __str__(self):
        return self.uid

    def get_variants(self, arch=None, types=None):
        return [
            v
            for v in list(self.variants.values())
            if (not arch or arch in v.arches) and (not types or v.type in types)
        ]

    def get_modules(self, arch=None, types=None):
        return []

    def get_modular_koji_tags(self, arch=None, types=None):
        return []

    def add_fake_module(self, nsvc, rpm_nvrs=None, with_artifacts=False, mmd_arch=None):
        if not Modulemd:
            # No support for modules
            return
        name, stream, version, context = nsvc.split(":")
        module_stream = Modulemd.ModuleStreamV2.new(name, stream)
        module_stream.set_version(int(version))
        module_stream.set_context(context)
        module_stream.set_summary("foo")
        module_stream.set_description("foo")
        module_stream.add_module_license("GPL")

        if rpm_nvrs:
            for rpm_nvr in rpm_nvrs:
                rpm_name = parse_nvr(rpm_nvr)["name"]
                component = Modulemd.ComponentRpm.new(rpm_nvr)
                component.set_name(rpm_name)
                component.set_rationale("Needed for test")
                module_stream.add_component(component)
                if with_artifacts:
                    module_stream.add_rpm_artifact(rpm_nvr)

        if self.modules is None:
            self.modules = []
        self.modules.append(":".join([name, stream, version]))
        if mmd_arch:
            nsvc = module_stream.get_nsvc()
            self.arch_mmds.setdefault(mmd_arch, {})[nsvc] = module_stream
        return module_stream


class MockPackageSet(dict):
    def __init__(self, *args):
        for pkg in args:
            self[pkg.path] = pkg


class MockPkg(object):
    def __init__(self, path, is_system_release=False, **kwargs):
        self.path = path
        self.is_system_release = is_system_release
        filename = os.path.basename(path)
        self.nvr, self.arch, _ = filename.rsplit(".", 2)
        self.name, self.version, self.release = self.nvr.rsplit("-", 2)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return self.nvr

    def __lt__(self, another):
        return self.nvr < another.nvr


class IterableMock(mock.Mock):
    def __iter__(self):
        return iter([])


class DummyCompose(object):
    def __init__(self, topdir, config):
        self.supported = True
        self.compose_date = "20151203"
        self.compose_type_suffix = ".t"
        self.compose_type = "test"
        self.compose_respin = 0
        self.compose_id = "Test-20151203.0.t"
        self.compose_label = None
        self.compose_label_major_version = None
        self.image_release = "20151203.t.0"
        self.image_version = "25"
        self.ci_base = mock.Mock(
            release_id="Test-1.0",
            release=mock.Mock(
                short="test", version="1.0", is_layered=False, type_suffix=""
            ),
        )
        self.topdir = topdir
        self.conf = load_config(PKGSET_REPOS, **config)
        checks.validate(self.conf, offline=True)
        self.paths = paths.Paths(self)
        self.has_comps = True
        self.variants = {
            "Server": MockVariant(
                uid="Server",
                arches=["x86_64", "amd64"],
                type="variant",
                id="Server",
                name="Server",
            ),
            "Client": MockVariant(
                uid="Client",
                arches=["amd64"],
                type="variant",
                id="Client",
                name="Client",
            ),
            "Everything": MockVariant(
                uid="Everything",
                arches=["x86_64", "amd64"],
                type="variant",
                id="Everything",
                name="Everything",
            ),
        }
        self.all_variants = self.variants.copy()

        # for PhaseLoggerMixin
        self._logger = mock.Mock(name="compose._logger")
        self._logger.handlers = [mock.Mock()]

        self.log_info = mock.Mock()
        self.log_error = mock.Mock()
        self.log_debug = mock.Mock()
        self.log_warning = mock.Mock()
        self.get_image_name = mock.Mock(return_value="image-name")
        self.image = mock.Mock(
            path="Client/i386/iso/image.iso",
            can_fail=False,
            size=123,
            _max_size=None,
        )
        self.im = mock.Mock(images={"Client": {"amd64": [self.image]}})
        self.old_composes = []
        self.config_dir = "/home/releng/config"
        self.notifier = None
        self.attempt_deliverable = mock.Mock()
        self.fail_deliverable = mock.Mock()
        self.require_deliverable = mock.Mock()
        self.should_create_yum_database = True
        self.cache_region = None
        self.containers_metadata = {}
        self.load_old_compose_config = mock.Mock(return_value=None)

    def setup_optional(self):
        self.all_variants["Server-optional"] = MockVariant(
            uid="Server-optional", arches=["x86_64"], type="optional"
        )
        self.all_variants["Server-optional"].parent = self.variants["Server"]
        self.variants["Server"].variants["optional"] = self.all_variants[
            "Server-optional"
        ]

    def setup_addon(self):
        self.all_variants["Server-HA"] = MockVariant(
            uid="Server-HA", arches=["x86_64"], type="addon", is_empty=False
        )
        self.all_variants["Server-HA"].parent = self.variants["Server"]
        self.variants["Server"].variants["HA"] = self.all_variants["Server-HA"]

    def get_variants(self, arch=None, types=None):
        return [
            v
            for v in list(self.all_variants.values())
            if (not arch or arch in v.arches) and (not types or v.type in types)
        ]

    def can_fail(self, variant, arch, deliverable):
        failable = get_arch_variant_data(
            self.conf, "failable_deliverables", arch, variant
        )
        return deliverable in failable

    def get_arches(self):
        result = set()
        for variant in list(self.variants.values()):
            result |= set(variant.arches)
        return sorted(result)

    def mkdtemp(self, suffix="", prefix="tmp"):
        return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=self.topdir)


def touch(path, content=None):
    """Helper utility that creates an dummy file in given location. Directories
    will be created."""
    content = content or (path + "\n")
    try:
        os.makedirs(os.path.dirname(path))
    except OSError:
        pass
    if not isinstance(content, six.binary_type):
        content = content.encode()
    with open(path, "wb") as f:
        f.write(content)
    return path


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def copy_fixture(fixture_name, dest):
    src = os.path.join(FIXTURE_DIR, fixture_name)
    touch(dest)
    shutil.copy2(src, dest)


def boom(*args, **kwargs):
    raise Exception("BOOM")


def mk_boom(cls=Exception, msg="BOOM"):
    def b(*args, **kwargs):
        raise cls(msg)

    return b


PKGSET_REPOS = dict(
    pkgset_source="repos",
    pkgset_repos={},
)

BASE_CONFIG = dict(
    release_short="test",
    release_name="Test",
    release_version="1.0",
    variants_file="variants.xml",
    createrepo_checksum="sha256",
    gather_method="deps",
)


def load_config(data={}, **kwargs):
    conf = dict()
    conf.update(BASE_CONFIG)
    conf.update(data)
    conf.update(kwargs)
    return conf


def fake_run_in_threads(func, params, threads=None):
    """Like run_in_threads from Kobo, but actually runs tasks serially."""
    for num, param in enumerate(params):
        func(None, param, num)
