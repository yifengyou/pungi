# -*- coding: utf-8 -*-

import mock
import os
import six

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import json
import tempfile
import re
from dogpile.cache import make_region

from pungi.phases.pkgset import pkgsets
from tests import helpers


class MockPathInfo(object):
    def __init__(self, topdir):
        self.topdir = topdir

    def build(self, build_info):
        return self.topdir

    def get_filename(self, rpm_info):
        return "{name}@{version}@{release}@{arch}".format(**rpm_info)

    def signed(self, rpm_info, sigkey):
        return os.path.join("signed", sigkey, self.get_filename(rpm_info))

    def rpm(self, rpm_info):
        return os.path.join("rpms", self.get_filename(rpm_info))

    def work(self):
        return "work"


class MockFile(object):
    def __init__(self, path):
        if path.startswith("/tmp"):
            # Drop /tmp/something/ from path
            path = path.split("/", 3)[-1]
        self.file_path = path
        self.file_name = os.path.basename(path)
        self.name, self.version, self.release, self.arch = self.file_name.split("@")
        self.sourcerpm = "{0.name}-{0.version}-{0.release}.{0.arch}".format(self)
        self.exclusivearch = []
        self.excludearch = []

    def __hash__(self):
        return hash(self.file_path)

    def __repr__(self):
        return self.file_path

    def __eq__(self, other):
        try:
            return self.file_path == other.file_path
        except AttributeError:
            return self.file_path == other

    def __le__(self, other):
        try:
            return self.file_path < other.file_path
        except AttributeError:
            return self.file_path < other

    def __lt__(self, other):
        return self <= other and self != other

    def __ge__(self, other):
        return not (self <= other) or self == other

    def __gt__(self, other):
        return not (self <= other)


class MockFileCache(dict):
    """Mock for kobo.pkgset.FileCache.
    It gets data from filename and does not touch filesystem.
    """

    def __init__(self, _wrapper):
        super(MockFileCache, self).__init__()
        self.file_cache = self

    def add(self, file_path):
        obj = MockFile(file_path)
        self[file_path] = obj
        return obj


class FakePool(object):
    """This class will be substituted for ReaderPool.
    It implements the same interface, but uses only the last added worker to
    process all tasks sequentially.
    """

    def __init__(self, package_set, logger=None):
        self.queue = []
        self.worker = None
        self.package_set = package_set

    def log_warning(self, *args, **kwargs):
        pass

    @property
    def queue_total(self):
        return len(self.queue)

    def queue_put(self, item):
        self.queue.append(item)

    def add(self, worker):
        self.worker = worker

    def start(self):
        for i, item in enumerate(self.queue):
            self.worker.process(item, i)

    def stop(self):
        pass


class PkgsetCompareMixin(object):
    def assertPkgsetEqual(self, actual, expected):
        for k, v1 in expected.items():
            self.assertIn(k, actual)
            v2 = actual.pop(k)
            six.assertCountEqual(self, v1, v2)
        self.assertEqual({}, actual)


@mock.patch("pungi.phases.pkgset.pkgsets.ReaderPool", new=FakePool)
@mock.patch("kobo.pkgset.FileCache", new=MockFileCache)
class TestKojiPkgset(PkgsetCompareMixin, helpers.PungiTestCase):
    def setUp(self):
        super(TestKojiPkgset, self).setUp()
        with open(os.path.join(helpers.FIXTURE_DIR, "tagged-rpms.json")) as f:
            self.tagged_rpms = json.load(f)

        self.path_info = MockPathInfo(self.topdir)

        self.koji_wrapper = mock.Mock()
        self.koji_wrapper.koji_proxy.listTaggedRPMS.return_value = self.tagged_rpms
        self.koji_wrapper.koji_module.pathinfo = self.path_info

    def _touch_files(self, filenames):
        for filename in filenames:
            helpers.touch(os.path.join(self.topdir, filename))

    def assertPkgsetEqual(self, actual, expected):
        for k, v1 in expected.items():
            self.assertIn(k, actual)
            v2 = actual.pop(k)
            six.assertCountEqual(self, v1, v2)
        self.assertEqual({}, actual, msg="Some architectures were missing")

    def test_all_arches(self):
        self._touch_files(
            [
                "rpms/pungi@4.1.3@3.fc25@noarch",
                "rpms/pungi@4.1.3@3.fc25@src",
                "rpms/bash@4.3.42@4.fc24@i686",
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash@4.3.42@4.fc24@src",
                "rpms/bash-debuginfo@4.3.42@4.fc24@i686",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        pkgset = pkgsets.KojiPackageSet("pkgset", self.koji_wrapper, [None])

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "src": ["rpms/pungi@4.1.3@3.fc25@src", "rpms/bash@4.3.42@4.fc24@src"],
                "noarch": ["rpms/pungi@4.1.3@3.fc25@noarch"],
                "i686": [
                    "rpms/bash@4.3.42@4.fc24@i686",
                    "rpms/bash-debuginfo@4.3.42@4.fc24@i686",
                ],
                "x86_64": [
                    "rpms/bash@4.3.42@4.fc24@x86_64",
                    "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                ],
            },
        )

    def test_only_one_arch(self):
        self._touch_files(
            [
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, [None], arches=["x86_64"]
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "x86_64": [
                    "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                    "rpms/bash@4.3.42@4.fc24@x86_64",
                ]
            },
        )

    def test_find_signed_with_preference(self):
        self._touch_files(
            [
                "signed/cafebabe/bash@4.3.42@4.fc24@x86_64",
                "signed/deadbeef/bash@4.3.42@4.fc24@x86_64",
                "signed/deadbeef/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, ["cafebabe", "deadbeef"], arches=["x86_64"]
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "x86_64": [
                    "signed/cafebabe/bash@4.3.42@4.fc24@x86_64",
                    "signed/deadbeef/bash-debuginfo@4.3.42@4.fc24@x86_64",
                ]
            },
        )

    def test_find_signed_fallback_unsigned(self):
        self._touch_files(
            [
                "signed/cafebabe/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, ["cafebabe", None], arches=["x86_64"]
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "x86_64": [
                    "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                    "signed/cafebabe/bash@4.3.42@4.fc24@x86_64",
                ]
            },
        )

    def test_can_not_find_signed_package(self):
        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, ["cafebabe"], arches=["x86_64"]
        )

        with self.assertRaises(RuntimeError) as ctx:
            pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        figure = re.compile(
            r"^RPM\(s\) not found for sigs: .+Check log for details.+bash-4\.3\.42-4\.fc24.+bash-debuginfo-4\.3\.42-4\.fc24$",  # noqa: E501
            re.DOTALL,
        )
        self.assertRegex(str(ctx.exception), figure)

    @mock.patch("os.path.isfile")
    @mock.patch("time.sleep")
    def test_find_signed_after_wait(self, sleep, isfile):
        checked_files = set()

        def check_file(path):
            """First check for any path will fail, second and further will succeed."""
            if path in checked_files:
                return True
            checked_files.add(path)
            return False

        isfile.side_effect = check_file

        fst_key, snd_key = ["cafebabe", "deadbeef"]
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            [fst_key, snd_key],
            arches=["x86_64"],
            signed_packages_retries=2,
            signed_packages_wait=5,
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        fst_pkg = "signed/%s/bash-debuginfo@4.3.42@4.fc24@x86_64"
        snd_pkg = "signed/%s/bash@4.3.42@4.fc24@x86_64"

        self.assertPkgsetEqual(
            result, {"x86_64": [fst_pkg % "cafebabe", snd_pkg % "cafebabe"]}
        )
        # Wait once for each of the two packages
        self.assertEqual(sleep.call_args_list, [mock.call(5)] * 2)
        # Each file will be checked three times
        self.assertEqual(
            isfile.call_args_list,
            [
                mock.call(os.path.join(self.topdir, fst_pkg % fst_key)),
                mock.call(os.path.join(self.topdir, fst_pkg % snd_key)),
                mock.call(os.path.join(self.topdir, fst_pkg % fst_key)),
                mock.call(os.path.join(self.topdir, snd_pkg % fst_key)),
                mock.call(os.path.join(self.topdir, snd_pkg % snd_key)),
                mock.call(os.path.join(self.topdir, snd_pkg % fst_key)),
            ],
        )

    def test_can_not_find_signed_package_allow_invalid_sigkeys(self):
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            ["cafebabe"],
            arches=["x86_64"],
            allow_invalid_sigkeys=True,
        )

        pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        with self.assertRaises(RuntimeError) as ctx:
            pkgset.raise_invalid_sigkeys_exception(pkgset.invalid_sigkey_rpms)

        figure = re.compile(
            r"^RPM\(s\) not found for sigs: .+Check log for details.+bash-4\.3\.42-4\.fc24.+bash-debuginfo-4\.3\.42-4\.fc24$",  # noqa: E501
            re.DOTALL,
        )
        self.assertRegex(str(ctx.exception), figure)

    def test_can_not_find_any_package(self):
        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, ["cafebabe", None], arches=["x86_64"]
        )

        with self.assertRaises(RuntimeError) as ctx:
            pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertRegex(
            str(ctx.exception),
            r"^RPM\(s\) not found for sigs: .+Check log for details.+",
        )

    @mock.patch("time.sleep")
    def test_can_not_find_signed_package_with_retries(self, time):
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            ["cafebabe"],
            arches=["x86_64"],
            signed_packages_retries=2,
            signed_packages_wait=5,
        )

        with self.assertRaises(RuntimeError) as ctx:
            pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertRegex(
            str(ctx.exception),
            r"^RPM\(s\) not found for sigs: .+Check log for details.+",
        )
        # Two packages making three attempts each, so two waits per package.
        self.assertEqual(time.call_args_list, [mock.call(5)] * 4)

    def test_packages_attribute(self):
        self._touch_files(
            [
                "rpms/pungi@4.1.3@3.fc25@noarch",
                "rpms/pungi@4.1.3@3.fc25@src",
                "rpms/bash@4.3.42@4.fc24@i686",
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash@4.3.42@4.fc24@src",
                "rpms/bash-debuginfo@4.3.42@4.fc24@i686",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            [None],
            packages=["bash"],
            populate_only_packages=True,
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "src": ["rpms/bash@4.3.42@4.fc24@src"],
                "i686": ["rpms/bash@4.3.42@4.fc24@i686"],
                "x86_64": ["rpms/bash@4.3.42@4.fc24@x86_64"],
            },
        )

    def test_get_extra_rpms_from_tasks(self):
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            [None],
            arches=["x86_64"],
            extra_tasks=["123", "456"],
        )
        children_tasks = [[{"id": 1}, {"id": 2}], [{"id": 3}, {"id": 4}]]
        task_results = [
            {
                "logs": [
                    "tasks/root.log",
                    "tasks/hw_info.log",
                    "tasks/state.log",
                    "tasks/build.log",
                    "tasks/mock_output.log",
                    "tasks/noarch_rpmdiff.json",
                ],
                "rpms": ["tasks/pungi-4.1.39-5.f30.noarch.rpm"],
                "srpms": ["tasks/pungi-4.1.39-5.f30.src.rpm"],
            },
            {
                "logs": [
                    "tasks/5478/29155478/root.log",
                    "tasks/5478/29155478/hw_info.log",
                    "tasks/5478/29155478/state.log",
                    "tasks/5478/29155478/build.log",
                ],
                "source": {
                    "source": "pungi-4.1.39-5.f30.src.rpm",
                    "url": "pungi-4.1.39-5.f30.src.rpm",
                },
                "srpm": "tasks/5478/29155478/pungi-4.1.39-5.f30.src.rpm",
            },
        ]
        self.koji_wrapper.retrying_multicall_map.side_effect = [
            children_tasks,
            task_results,
        ]

        expected_rpms = [
            {
                "arch": "noarch",
                "build_id": None,
                "epoch": "",
                "name": "pungi",
                "path_from_task": "work/tasks/pungi-4.1.39-5.f30.noarch.rpm",
                "release": "5.f30",
                "src": False,
                "version": "4.1.39",
            },
            {
                "arch": "src",
                "build_id": None,
                "epoch": "",
                "name": "pungi",
                "path_from_task": "work/tasks/pungi-4.1.39-5.f30.src.rpm",
                "release": "5.f30",
                "src": True,
                "version": "4.1.39",
            },
        ]

        rpms = pkgset.get_extra_rpms_from_tasks()
        self.assertEqual(rpms, expected_rpms)

    def test_get_latest_rpms_cache(self):
        self._touch_files(
            [
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        cache_region = make_region().configure("dogpile.cache.memory")
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            [None],
            arches=["x86_64"],
            cache_region=cache_region,
        )

        # Try calling the populate twice, but expect just single listTaggedRPMs
        # call - that means the caching worked.
        for i in range(2):
            result = pkgset.populate("f25")
            self.assertEqual(
                self.koji_wrapper.koji_proxy.mock_calls,
                [
                    mock.call.listTaggedRPMS(
                        "f25", event=None, inherit=True, latest=True
                    )
                ],
            )
            self.assertPkgsetEqual(
                result,
                {
                    "x86_64": [
                        "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                        "rpms/bash@4.3.42@4.fc24@x86_64",
                    ]
                },
            )

    def test_get_latest_rpms_cache_different_id(self):
        self._touch_files(
            [
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        cache_region = make_region().configure("dogpile.cache.memory")
        pkgset = pkgsets.KojiPackageSet(
            "pkgset",
            self.koji_wrapper,
            [None],
            arches=["x86_64"],
            cache_region=cache_region,
        )

        # Try calling the populate twice with different event id. It must not
        # cache anything.
        expected_calls = []
        for i in range(2):
            expected_calls.append(
                mock.call.listTaggedRPMS("f25", event=i, inherit=True, latest=True)
            )
            result = pkgset.populate("f25", event={"id": i})
            self.assertEqual(self.koji_wrapper.koji_proxy.mock_calls, expected_calls)
            self.assertPkgsetEqual(
                result,
                {
                    "x86_64": [
                        "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                        "rpms/bash@4.3.42@4.fc24@x86_64",
                    ]
                },
            )

    def test_extra_builds_attribute(self):
        self._touch_files(
            [
                "rpms/pungi@4.1.3@3.fc25@noarch",
                "rpms/pungi@4.1.3@3.fc25@src",
                "rpms/bash@4.3.42@4.fc24@i686",
                "rpms/bash@4.3.42@4.fc24@x86_64",
                "rpms/bash@4.3.42@4.fc24@src",
                "rpms/bash-debuginfo@4.3.42@4.fc24@i686",
                "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
            ]
        )

        # Return "pungi" RPMs and builds using "get_latest_rpms" which gets
        # them from Koji multiCall.
        extra_rpms = [rpm for rpm in self.tagged_rpms[0] if rpm["name"] == "pungi"]
        extra_builds = [
            build for build in self.tagged_rpms[1] if build["package_name"] == "pungi"
        ]
        self.koji_wrapper.retrying_multicall_map.side_effect = [
            extra_builds,
            [extra_rpms],
        ]

        # Do not return "pungi" RPMs and builds using the listTaggedRPMs, so
        # we can be sure "pungi" gets into compose using the `extra_builds`.
        self.koji_wrapper.koji_proxy.listTaggedRPMS.return_value = [
            [rpm for rpm in self.tagged_rpms[0] if rpm["name"] != "pungi"],
            [b for b in self.tagged_rpms[1] if b["package_name"] != "pungi"],
        ]

        pkgset = pkgsets.KojiPackageSet(
            "pkgset", self.koji_wrapper, [None], extra_builds=["pungi-4.1.3-3.fc25"]
        )

        result = pkgset.populate("f25")

        self.assertEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.listTaggedRPMS("f25", event=None, inherit=True, latest=True)],
        )

        self.assertPkgsetEqual(
            result,
            {
                "src": ["rpms/pungi@4.1.3@3.fc25@src", "rpms/bash@4.3.42@4.fc24@src"],
                "noarch": ["rpms/pungi@4.1.3@3.fc25@noarch"],
                "i686": [
                    "rpms/bash@4.3.42@4.fc24@i686",
                    "rpms/bash-debuginfo@4.3.42@4.fc24@i686",
                ],
                "x86_64": [
                    "rpms/bash@4.3.42@4.fc24@x86_64",
                    "rpms/bash-debuginfo@4.3.42@4.fc24@x86_64",
                ],
            },
        )


class TestReuseKojiPkgset(helpers.PungiTestCase):
    def setUp(self):
        super(TestReuseKojiPkgset, self).setUp()
        self.old_compose_dir = tempfile.mkdtemp()
        self.old_compose = helpers.DummyCompose(self.old_compose_dir, {})
        self.compose = helpers.DummyCompose(
            self.topdir, {"old_composes": os.path.dirname(self.old_compose_dir)}
        )

        self.koji_wrapper = mock.Mock()

        self.tag = "test-tag"
        self.inherited_tag = "inherited-test-tag"
        self.pkgset = pkgsets.KojiPackageSet(
            self.tag, self.koji_wrapper, [None], arches=["x86_64"]
        )
        self.pkgset.log_debug = mock.Mock()
        self.pkgset.log_info = mock.Mock()

    def assert_not_reuse(self):
        self.assertIsNone(getattr(self.pkgset, "reuse", None))

    def test_resue_no_old_compose_found(self):
        self.pkgset.try_to_reuse(self.compose, self.tag)
        self.pkgset.log_info.assert_called_once_with(
            "Trying to reuse pkgset data of old compose"
        )
        self.pkgset.log_debug.assert_called_once_with(
            "No old compose found. Nothing to reuse."
        )
        self.assert_not_reuse()

    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_read_koji_event_file_failed(self, mock_old_topdir):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(
            side_effect=Exception("unknown error")
        )
        self.pkgset.try_to_reuse(self.compose, self.tag)
        self.pkgset.log_debug.assert_called_once_with(
            "Can't read koji event from file: unknown error"
        )
        self.assert_not_reuse()

    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_build_under_tag_changed(self, mock_old_topdir):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(side_effect=[3, 1])
        self.koji_wrapper.koji_proxy.queryHistory.return_value = {
            "tag_listing": [{}],
            "tag_inheritance": [],
        }

        self.pkgset.try_to_reuse(self.compose, self.tag)

        self.assertEqual(
            self.pkgset.log_debug.mock_calls,
            [
                mock.call(
                    "Koji event doesn't match, querying changes between event 1 and 3"
                ),
                mock.call("Builds under tag %s changed. Can't reuse." % self.tag),
            ],
        )
        self.assert_not_reuse()

    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_build_under_inherited_tag_changed(self, mock_old_topdir):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(side_effect=[3, 1])
        self.koji_wrapper.koji_proxy.queryHistory.side_effect = [
            {"tag_listing": [], "tag_inheritance": []},
            {"tag_listing": [{}], "tag_inheritance": []},
        ]
        self.koji_wrapper.koji_proxy.getFullInheritance.return_value = [
            {"name": self.inherited_tag}
        ]

        self.pkgset.try_to_reuse(self.compose, self.tag)

        self.assertEqual(
            self.pkgset.log_debug.mock_calls,
            [
                mock.call(
                    "Koji event doesn't match, querying changes between event 1 and 3"
                ),
                mock.call(
                    "Builds under inherited tag %s changed. Can't reuse."
                    % self.inherited_tag
                ),
            ],
        )
        self.assert_not_reuse()

    @mock.patch("pungi.paths.os.path.exists", return_value=True)
    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_failed_load_reuse_file(self, mock_old_topdir, mock_exists):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(side_effect=[3, 1])
        self.koji_wrapper.koji_proxy.queryHistory.return_value = {
            "tag_listing": [],
            "tag_inheritance": [],
        }
        self.koji_wrapper.koji_proxy.getFullInheritance.return_value = []
        self.pkgset.load_old_file_cache = mock.Mock(
            side_effect=Exception("unknown error")
        )

        self.pkgset.try_to_reuse(self.compose, self.tag)

        self.assertEqual(
            self.pkgset.log_debug.mock_calls,
            [
                mock.call(
                    "Koji event doesn't match, querying changes between event 1 and 3"
                ),
                mock.call(
                    "Loading reuse file: %s"
                    % os.path.join(
                        self.old_compose_dir,
                        "work/global",
                        "pkgset_%s_reuse.pickle" % self.tag,
                    )
                ),
                mock.call("Failed to load reuse file: unknown error"),
            ],
        )
        self.assert_not_reuse()

    @mock.patch("pungi.paths.os.path.exists", return_value=True)
    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_criteria_not_match(self, mock_old_topdir, mock_exists):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(side_effect=[3, 1])
        self.koji_wrapper.koji_proxy.queryHistory.return_value = {
            "tag_listing": [],
            "tag_inheritance": [],
        }
        self.koji_wrapper.koji_proxy.getFullInheritance.return_value = []
        self.pkgset.load_old_file_cache = mock.Mock(
            return_value={"allow_invalid_sigkeys": True}
        )

        self.pkgset.try_to_reuse(self.compose, self.tag)

        self.assertEqual(
            self.pkgset.log_debug.mock_calls,
            [
                mock.call(
                    "Koji event doesn't match, querying changes between event 1 and 3"
                ),
                mock.call(
                    "Loading reuse file: %s"
                    % os.path.join(
                        self.old_compose_dir,
                        "work/global",
                        "pkgset_%s_reuse.pickle" % self.tag,
                    )
                ),
            ],
        )
        self.assertEqual(
            self.pkgset.log_info.mock_calls,
            [
                mock.call("Trying to reuse pkgset data of old compose"),
                mock.call("Criteria does not match. Nothing to reuse."),
            ],
        )
        self.assert_not_reuse()

    @mock.patch("pungi.phases.pkgset.pkgsets.copy_all")
    @mock.patch("pungi.paths.os.path.exists", return_value=True)
    @mock.patch.object(helpers.paths.Paths, "get_old_compose_topdir")
    def test_reuse_pkgset(self, mock_old_topdir, mock_exists, mock_copy_all):
        mock_old_topdir.return_value = self.old_compose_dir
        self.pkgset._get_koji_event_from_file = mock.Mock(side_effect=[3, 1])
        self.koji_wrapper.koji_proxy.queryHistory.return_value = {
            "tag_listing": [],
            "tag_inheritance": [],
        }
        self.koji_wrapper.koji_proxy.getFullInheritance.return_value = []
        self.pkgset.load_old_file_cache = mock.Mock(
            return_value={
                "allow_invalid_sigkeys": self.pkgset._allow_invalid_sigkeys,
                "packages": self.pkgset.packages,
                "populate_only_packages": self.pkgset.populate_only_packages,
                "extra_builds": self.pkgset.extra_builds,
                "sigkeys": self.pkgset.sigkey_ordering,
                "include_packages": None,
                "rpms_by_arch": mock.Mock(),
                "srpms_by_name": mock.Mock(),
            }
        )
        self.pkgset.old_file_cache = mock.Mock()

        self.pkgset.try_to_reuse(self.compose, self.tag)

        old_repo_dir = os.path.join(self.old_compose_dir, "work/global/repo", self.tag)
        self.assertEqual(
            self.pkgset.log_info.mock_calls,
            [
                mock.call("Trying to reuse pkgset data of old compose"),
                mock.call("Copying repo data for reuse: %s" % old_repo_dir),
            ],
        )
        self.assertEqual(old_repo_dir, self.pkgset.reuse)
        self.assertEqual(self.pkgset.file_cache, self.pkgset.old_file_cache)


@mock.patch("kobo.pkgset.FileCache", new=MockFileCache)
class TestMergePackageSets(PkgsetCompareMixin, unittest.TestCase):
    def test_merge_in_another_arch(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        for name in ["rpms/pungi@4.1.3@3.fc25@noarch", "rpms/pungi@4.1.3@3.fc25@src"]:
            pkg = first.file_cache.add(name)
            first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        for name in ["rpms/bash@4.3.42@4.fc24@i686"]:
            pkg = second.file_cache.add(name)
            second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686"])

        self.assertPkgsetEqual(
            first.rpms_by_arch,
            {
                "src": ["rpms/pungi@4.1.3@3.fc25@src"],
                "noarch": ["rpms/pungi@4.1.3@3.fc25@noarch"],
                "i686": ["rpms/bash@4.3.42@4.fc24@i686"],
            },
        )

    def test_merge_includes_noarch_with_different_exclude_arch(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/pungi@4.1.3@3.fc25@noarch")
        pkg.excludearch = ["x86_64"]
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686", "noarch"])

        self.assertPkgsetEqual(
            first.rpms_by_arch,
            {
                "i686": ["rpms/bash@4.3.42@4.fc24@i686"],
                "noarch": ["rpms/pungi@4.1.3@3.fc25@noarch"],
            },
        )

    def test_merge_excludes_noarch_exclude_arch(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/pungi@4.1.3@3.fc25@noarch")
        pkg.excludearch = ["i686"]
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686", "noarch"])

        self.assertPkgsetEqual(
            first.rpms_by_arch, {"i686": ["rpms/bash@4.3.42@4.fc24@i686"], "noarch": []}
        )

    def test_merge_excludes_noarch_exclusive_arch(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/pungi@4.1.3@3.fc25@noarch")
        pkg.exclusivearch = ["x86_64"]
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686", "noarch"])

        self.assertPkgsetEqual(
            first.rpms_by_arch, {"i686": ["rpms/bash@4.3.42@4.fc24@i686"], "noarch": []}
        )

    def test_merge_includes_noarch_with_same_exclusive_arch(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/pungi@4.1.3@3.fc25@noarch")
        pkg.exclusivearch = ["i686"]
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686", "noarch"])

        self.assertPkgsetEqual(
            first.rpms_by_arch,
            {
                "i686": ["rpms/bash@4.3.42@4.fc24@i686"],
                "noarch": ["rpms/pungi@4.1.3@3.fc25@noarch"],
            },
        )

    def test_merge_skips_package_in_cache(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686"])

        self.assertPkgsetEqual(
            first.rpms_by_arch, {"i686": ["rpms/bash@4.3.42@4.fc24@i686"]}
        )

    def test_merge_skips_src_without_binary(self):
        first = pkgsets.PackageSetBase("first", [None])
        second = pkgsets.PackageSetBase("second", [None])

        pkg = first.file_cache.add("rpms/bash@4.3.42@4.fc24@i686")
        first.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkg = second.file_cache.add("rpms/pungi@4.1.3@3.fc25@src")
        second.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        first.merge(second, "i386", ["i686", "src"])

        self.assertPkgsetEqual(
            first.rpms_by_arch,
            {"i686": ["rpms/bash@4.3.42@4.fc24@i686"], "src": [], "nosrc": []},
        )


@mock.patch("kobo.pkgset.FileCache", new=MockFileCache)
class TestSaveFileList(unittest.TestCase):
    def setUp(self):
        fd, self.tmpfile = tempfile.mkstemp()
        os.close(fd)

    def tearDown(self):
        os.unlink(self.tmpfile)

    def test_save_arches_alphabetically(self):
        pkgset = pkgsets.PackageSetBase("pkgset", [None])
        for name in [
            "rpms/pungi@4.1.3@3.fc25@x86_64",
            "rpms/pungi@4.1.3@3.fc25@src",
            "rpms/pungi@4.1.3@3.fc25@ppc64",
        ]:
            pkg = pkgset.file_cache.add(name)
            pkgset.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkgset.save_file_list(self.tmpfile)

        with open(self.tmpfile) as f:
            rpms = f.read().strip().split("\n")
            self.assertEqual(
                rpms,
                [
                    "rpms/pungi@4.1.3@3.fc25@ppc64",
                    "rpms/pungi@4.1.3@3.fc25@src",
                    "rpms/pungi@4.1.3@3.fc25@x86_64",
                ],
            )

    def test_save_strip_prefix(self):
        pkgset = pkgsets.PackageSetBase("pkgset", [None])
        for name in ["rpms/pungi@4.1.3@3.fc25@noarch", "rpms/pungi@4.1.3@3.fc25@src"]:
            pkg = pkgset.file_cache.add(name)
            pkgset.rpms_by_arch.setdefault(pkg.arch, []).append(pkg)

        pkgset.save_file_list(self.tmpfile, remove_path_prefix="rpms/")

        with open(self.tmpfile) as f:
            rpms = f.read().strip().split("\n")
            six.assertCountEqual(
                self, rpms, ["pungi@4.1.3@3.fc25@noarch", "pungi@4.1.3@3.fc25@src"]
            )
