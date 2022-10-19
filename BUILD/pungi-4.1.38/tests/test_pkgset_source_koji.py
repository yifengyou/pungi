# -*- coding: utf-8 -*-

import json
import mock
import os
import re
import sys
try:
    import unittest2 as unittest
except ImportError:
    import unittest

from six.moves import cPickle as pickle

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.pkgset.sources import source_koji
from tests import helpers
from pungi import Modulemd

EVENT_INFO = {'id': 15681980, 'ts': 1460956382.81936}
TAG_INFO = {
    "maven_support": False,
    "locked": False,
    "name": "f25",
    "extra": {
        "mock.package_manager": "dnf"
    },
    "perm": None,
    "id": 335,
    "arches": None,
    "maven_include_all": None,
    "perm_id": None
}


class TestGetKojiEvent(helpers.PungiTestCase):

    def setUp(self):
        super(TestGetKojiEvent, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

        self.event_file = self.topdir + '/work/global/koji-event'

    def test_use_preconfigured_event(self):
        koji_wrapper = mock.Mock()
        self.compose.koji_event = 123456

        koji_wrapper.koji_proxy.getEvent.return_value = EVENT_INFO

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(
            koji_wrapper.mock_calls,
            [mock.call.koji_proxy.getEvent(123456)])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)

    def test_gets_last_event(self):
        self.compose.koji_event = None
        koji_wrapper = mock.Mock()

        koji_wrapper.koji_proxy.getLastEvent.return_value = EVENT_INFO

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(
            koji_wrapper.mock_calls,
            [mock.call.koji_proxy.getLastEvent()])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)

    def test_gets_last_event_in_debug_mode(self):
        self.compose.DEBUG = True
        self.compose.koji_event = None
        koji_wrapper = mock.Mock()
        helpers.touch(self.event_file, json.dumps(EVENT_INFO))

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(koji_wrapper.mock_calls, [])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)


class TestPopulateGlobalPkgset(helpers.PungiTestCase):
    def setUp(self):
        super(TestPopulateGlobalPkgset, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': 'f25',
            'sigkeys': mock.Mock(),
        })
        self.koji_wrapper = mock.Mock()
        self.pkgset_path = os.path.join(self.topdir, 'work', 'global', 'pkgset_global.pickle')
        self.koji_module_path = os.path.join(self.topdir, 'work', 'global', 'koji-module-Server.yaml')

    @mock.patch('six.moves.cPickle.dumps')
    @mock.patch('pungi.phases.pkgset.pkgsets.KojiPackageSet')
    def test_populate(self, KojiPackageSet, pickle_dumps):

        pickle_dumps.return_value = b'DATA'

        orig_pkgset = KojiPackageSet.return_value

        pkgset = source_koji.populate_global_pkgset(
            self.compose, self.koji_wrapper, '/prefix', 123456)

        self.assertIs(pkgset, orig_pkgset)
        self.assertEqual(
            pkgset.mock_calls,
            [
                mock.call.populate(
                    'f25',
                    123456,
                    inherit=True,
                    logfile=self.topdir + '/logs/global/packages_from_f25.global.log',
                    include_packages=set(),
                ),
                mock.call.save_file_list(
                    self.topdir + '/work/global/package_list/global.conf',
                    remove_path_prefix='/prefix',
                ),
                mock.call.save_file_cache(
                    self.topdir + '/work/global/pkgset_file_cache.pickle'
                ),
            ]
        )
        self.assertItemsEqual(pickle_dumps.call_args_list,
                              [mock.call(orig_pkgset, protocol=pickle.HIGHEST_PROTOCOL)])
        with open(self.pkgset_path) as f:
            self.assertEqual(f.read(), 'DATA')

    @mock.patch('six.moves.cPickle.dumps')
    @mock.patch('pungi.phases.pkgset.pkgsets.KojiPackageSet')
    def test_populate_with_multiple_koji_tags(self, KojiPackageSet, pickle_dumps):
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': ['f25', 'f25-extra'],
            'sigkeys': mock.Mock(),
        })

        pickle_dumps.return_value = b'DATA'

        orig_pkgset = KojiPackageSet.return_value

        pkgset = source_koji.populate_global_pkgset(
            self.compose, self.koji_wrapper, '/prefix', 123456)

        self.assertIs(pkgset, orig_pkgset)
        pkgset.assert_has_calls(
            [
                mock.call.populate(
                    'f25',
                    123456,
                    inherit=True,
                    logfile=self.topdir + '/logs/global/packages_from_f25.global.log',
                    include_packages=set(),
                ),
            ]
        )
        pkgset.assert_has_calls(
            [
                mock.call.populate(
                    'f25-extra',
                    123456,
                    inherit=True,
                    logfile=self.topdir + '/logs/global/packages_from_f25-extra.global.log',
                    include_packages=set(),
                ),
            ]
        )
        pkgset.assert_has_calls([mock.call.save_file_list(self.topdir + '/work/global/package_list/global.conf',
                                                          remove_path_prefix='/prefix')])
        # for each tag, call pkgset.fast_merge once for each variant and once for global pkgset
        self.assertEqual(pkgset.fast_merge.call_count, 2 * (len(self.compose.all_variants.values()) + 1))
        self.assertItemsEqual(pickle_dumps.call_args_list,
                              [mock.call(orig_pkgset, protocol=pickle.HIGHEST_PROTOCOL)])
        with open(self.pkgset_path) as f:
            self.assertEqual(f.read(), 'DATA')

    @mock.patch('six.moves.cPickle.load')
    def test_populate_in_debug_mode(self, pickle_load):
        helpers.touch(self.pkgset_path, 'DATA')
        self.compose.DEBUG = True

        pickle_load.return_value

        with mock.patch('pungi.phases.pkgset.sources.source_koji.open',
                        mock.mock_open(), create=True) as m:
            pkgset = source_koji.populate_global_pkgset(
                self.compose, self.koji_wrapper, '/prefix', 123456)

        self.assertEqual(pickle_load.call_args_list,
                         [mock.call(m.return_value)])
        self.assertIs(pkgset, pickle_load.return_value)
        self.assertEqual(
            pkgset.mock_calls,
            [mock.call.save_file_list(self.topdir + '/work/global/package_list/global.conf',
                                      remove_path_prefix='/prefix'),
             mock.call.save_file_cache(self.topdir + '/work/global/pkgset_file_cache.pickle')])

    @mock.patch('six.moves.cPickle.dumps')
    @mock.patch('pungi.phases.pkgset.pkgsets.KojiPackageSet.populate')
    @mock.patch('pungi.phases.pkgset.pkgsets.KojiPackageSet.save_file_list')
    def test_populate_packages_to_gather(self, save_file_list, popuplate,
                                         pickle_dumps):
        self.compose = helpers.DummyCompose(self.topdir, {
            'gather_method': 'nodeps',
            'pkgset_koji_tag': 'f25',
            'sigkeys': mock.Mock(),
            'additional_packages': [
                ('.*', {'*': ['pkg', 'foo.x86_64']}),
            ]
        })
        pickle_dumps.return_value = b'DATA'

        pkgset = source_koji.populate_global_pkgset(
            self.compose, self.koji_wrapper, '/prefix', 123456)
        self.assertItemsEqual(pkgset.packages, ["pkg", "foo"])


class TestGetPackageSetFromKoji(helpers.PungiTestCase):
    def setUp(self):
        super(TestGetPackageSetFromKoji, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': 'f25',
        })
        self.compose.koji_event = None
        self.koji_wrapper = mock.Mock()
        self.koji_wrapper.koji_proxy.getLastEvent.return_value = EVENT_INFO
        self.koji_wrapper.koji_proxy.getTag.return_value = TAG_INFO

    @mock.patch('pungi.phases.pkgset.sources.source_koji.create_arch_repos')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.run_create_global_repo')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.get_create_global_repo_cmd')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.populate_arch_pkgsets')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.populate_global_pkgset')
    def test_get_package_sets(self, pgp, pap, gcgrc, rcgr, car):
        expected = {'x86_64': mock.Mock()}
        pap.return_value = expected
        expected['global'] = pgp.return_value

        pkgsets = source_koji.get_pkgset_from_koji(self.compose, self.koji_wrapper, '/prefix')

        self.assertItemsEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.getLastEvent()]
        )

        self.assertEqual(pgp.call_args_list,
                         [mock.call(self.compose, self.koji_wrapper, '/prefix',
                                    EVENT_INFO)])
        self.assertEqual(pap.call_args_list,
                         [mock.call(self.compose, '/prefix', pgp.return_value)])
        self.assertEqual(gcgrc.call_args_list,
                         [mock.call(self.compose, '/prefix')])
        self.assertEqual(rcgr.call_args_list,
                         [mock.call(self.compose, gcgrc.return_value)])
        self.assertItemsEqual(car.call_args_list, [mock.call(self.compose, '/prefix')])

        self.assertEqual(pkgsets, expected)

    def test_get_koji_modules(self):
        mock_build_ids = [{'id': 1065873, 'name': 'testmodule2-master_dash-20180406051653.96c371af'}]
        mock_extra = {
            'typeinfo': {
                'module': {
                    'content_koji_tag': 'module-b62270b82443edde',
                    'modulemd_str': mock.Mock(),
                    'name': 'testmodule2',
                    'stream': 'master',
                    'version': '20180406051653',
                    'context': '96c371af',
                }
            }
        }
        mock_build_md = [
            {
                'id': 1065873,
                'epoch': None,
                'extra': mock_extra,
                'name': 'testmodule2',
                'nvr': 'testmodule2-master_dash-20180406051653.2e6f5e0a',
                'release': '20180406051653.2e6f5e0a',
                'state': 1,
                'version': 'master_dash',
                'completion_ts': 1433473124.0,
            }
        ]

        self.koji_wrapper.koji_proxy.search.return_value = mock_build_ids
        self.koji_wrapper.koji_proxy.getBuild.return_value = mock_build_md[0]
        event = {"id": 12345, "ts": 1533473124.0}

        module_info_str = "testmodule2:master-dash:20180406051653:96c371af"
        result = source_koji.get_koji_modules(
            self.compose, self.koji_wrapper, event, module_info_str
        )

        assert type(result) is list
        assert len(result) == 1
        module = result[0]
        assert type(module) is dict
        self.assertIn("module_stream", module)
        self.assertIn("module_version", module)
        self.assertIn("module_context", module)
        self.assertIn("tag", module)

        expected_query = "testmodule2-master_dash-20180406051653.96c371af"
        self.koji_wrapper.koji_proxy.search.assert_called_once_with(expected_query, "build",
                                                                    "glob")
        self.koji_wrapper.koji_proxy.getBuild.assert_called_once_with(mock_build_ids[0]["id"])

    def test_get_koji_modules_filter_by_event(self):
        mock_build_ids = [
            {"id": 1065873, "name": "testmodule2-master_dash-20180406051653.96c371af"}
        ]
        mock_extra = {
            "typeinfo": {
                "module": {
                    "content_koji_tag": "module-b62270b82443edde",
                    "modulemd_str": mock.Mock()}
            }
        }
        mock_build_md = [
            {
                "id": 1065873,
                "epoch": None,
                "extra": mock_extra,
                "name": "testmodule2",
                "nvr": "testmodule2-master_dash-20180406051653.2e6f5e0a",
                "release": "20180406051653.2e6f5e0a",
                "state": 1,
                "version": "master_dash",
                "completion_ts": 1633473124.0,
            }
        ]

        self.koji_wrapper.koji_proxy.search.return_value = mock_build_ids
        self.koji_wrapper.koji_proxy.getBuild.return_value = mock_build_md[0]
        event = {"id": 12345, "ts": 1533473124.0}

        with self.assertRaises(ValueError) as ctx:
            source_koji.get_koji_modules(
                self.compose, self.koji_wrapper, event, "testmodule2:master-dash"
            )

        self.assertIn("No module build found", str(ctx.exception))

        self.koji_wrapper.koji_proxy.search.assert_called_once_with(
            "testmodule2-master_dash-*", "build", "glob"
        )
        self.koji_wrapper.koji_proxy.getBuild.assert_called_once_with(mock_build_ids[0]["id"])
        self.koji_wrapper.koji_proxy.listArchives.assert_not_called()
        self.koji_wrapper.koji_proxy.listRPMs.assert_not_called()

    def test_get_koji_modules_no_version(self):
        mock_build_ids = [
            {'id': 1065873, 'name': 'testmodule2-master-20180406051653.2e6f5e0a'},
            {'id': 1065874, 'name': 'testmodule2-master-20180406051653.96c371af'}
        ]
        mock_extra = [
            {
                'typeinfo': {
                    'module': {
                        'content_koji_tag': 'module-b62270b82443edde',
                        'modulemd_str': mock.Mock(),
                        'name': 'testmodule2',
                        'stream': 'master',
                        'version': '20180406051653',
                        'context': '2e6f5e0a',
                    }
                }
            },
            {
                'typeinfo': {
                    'module': {
                        'content_koji_tag': 'module-52e40b9cdd3c0f7d',
                        'modulemd_str': mock.Mock(),
                        'name': 'testmodule2',
                        'stream': 'master',
                        'version': '20180406051653',
                        'context': '96c371af',
                    }
                }
            }
        ]
        mock_build_md = [
            {
                'id': 1065873,
                'epoch': None,
                'extra': mock_extra[0],
                'name': 'testmodule2',
                'nvr': 'testmodule2-master-20180406051653.2e6f5e0a',
                'release': '20180406051653.2e6f5e0a',
                'state': 1,
                'version': 'master',
                'completion_ts': 1433473124.0,
            },
            {
                'id': 1065874,
                'epoch': None,
                'extra': mock_extra[1],
                'name': 'testmodule2',
                'nvr': 'testmodule2-master-20180406051653.96c371af',
                'release': '20180406051653.96c371af',
                'state': 1,
                'version': 'master',
                'completion_ts': 1433473124.0,
            }
        ]

        self.koji_wrapper.koji_proxy.search.return_value = mock_build_ids
        self.koji_wrapper.koji_proxy.getBuild.side_effect = mock_build_md

        event = {"id": 12345, "ts": 1533473124.0}

        module_info_str = "testmodule2:master"
        result = source_koji.get_koji_modules(
            self.compose, self.koji_wrapper, event, module_info_str
        )

        assert type(result) is list
        assert len(result) == 2
        module = result[0]
        for module in result:
            assert type(module) is dict
            self.assertIn("module_stream", module)
            self.assertIn("module_version", module)
            self.assertIn("module_context", module)

        expected_query = "testmodule2-master-*"
        self.koji_wrapper.koji_proxy.search.assert_called_once_with(expected_query, "build",
                                                                    "glob")

        expected_calls = [mock.call(mock_build_ids[0]["id"]), mock.call(mock_build_ids[1]["id"])]
        self.koji_wrapper.koji_proxy.getBuild.mock_calls == expected_calls


class TestSourceKoji(helpers.PungiTestCase):

    @mock.patch('pungi.phases.pkgset.sources.source_koji.get_pkgset_from_koji')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run(self, KojiWrapper, gpfk):
        compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji'
        })
        KojiWrapper.return_value.koji_module.config.topdir = '/prefix'

        phase = source_koji.PkgsetSourceKoji(compose)
        pkgsets, path_prefix = phase()

        self.assertEqual(pkgsets, gpfk.return_value)
        self.assertEqual(path_prefix, '/prefix/')
        self.assertItemsEqual(KojiWrapper.mock_calls,
                              [mock.call('koji')])


class TestCorrectNVR(helpers.PungiTestCase):

    def setUp(self):
        super(TestCorrectNVR, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.nv = "base-runtime-f26"
        self.nvr = "base-runtime-f26-20170502134116"
        self.release_regex = re.compile(r"^(\d){14}$")
        self.new_nv = "base-runtime:f26"
        self.new_nvr = "base-runtime:f26:20170502134116"
        self.new_nvrc = "base-runtime:f26:20170502134116:0123abcd"

    def test_nv(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.nv)
        expectedKeys = ["stream", "name"]
        self.assertItemsEqual(module_info.keys(), expectedKeys)

    def test_nvr(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.nvr)
        expectedKeys = ["stream", "name", "version"]
        self.assertItemsEqual(module_info.keys(), expectedKeys)

    def test_correct_release(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.nvr)
        self.assertIsNotNone(self.release_regex.match(module_info["version"]))

    def test_new_nv(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.new_nv)
        expected = {
            'name': 'base-runtime',
            'stream': 'f26'}

        self.assertEqual(module_info, expected)

    def test_new_nvr(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.new_nvr)
        expected = {
            'name': 'base-runtime',
            'stream': 'f26',
            'version': '20170502134116'}
        self.assertEqual(module_info, expected)

    def test_new_nvrc(self):
        module_info = source_koji.variant_dict_from_str(self.compose, self.new_nvrc)
        expected = {
            'name': 'base-runtime',
            'stream': 'f26',
            'version': '20170502134116',
            'context': '0123abcd'}
        self.assertEqual(module_info, expected)

    def test_new_garbage_value(self):
        self.assertRaises(ValueError, source_koji.variant_dict_from_str,
                          self.compose, 'foo:bar:baz:quux:qaar')


class TestFilterInherited(unittest.TestCase):

    def test_empty_module_list(self):
        event = {"id": 123456}
        koji_proxy = mock.Mock()
        module_builds = []
        top_tag = "top-tag"

        koji_proxy.getFullInheritance.return_value = [
            {"name": "middle-tag"}, {"name": "bottom-tag"}
        ]

        result = source_koji.filter_inherited(koji_proxy, event, module_builds, top_tag)

        self.assertItemsEqual(result, [])
        self.assertEqual(
            koji_proxy.mock_calls,
            [mock.call.getFullInheritance("top-tag", event=123456)],
        )

    def test_exclude_middle_and_bottom_tag(self):
        event = {"id": 123456}
        koji_proxy = mock.Mock()
        top_tag = "top-tag"

        koji_proxy.getFullInheritance.return_value = [
            {"name": "middle-tag"}, {"name": "bottom-tag"}
        ]
        module_builds = [
            {"name": "foo", "version": "1", "release": "1", "tag_name": "top-tag"},
            {"name": "foo", "version": "1", "release": "2", "tag_name": "bottom-tag"},
            {"name": "foo", "version": "1", "release": "3", "tag_name": "middle-tag"},
        ]

        result = source_koji.filter_inherited(koji_proxy, event, module_builds, top_tag)

        self.assertItemsEqual(
            result,
            [{"name": "foo", "version": "1", "release": "1", "tag_name": "top-tag"}],
        )
        self.assertEqual(
            koji_proxy.mock_calls,
            [mock.call.getFullInheritance("top-tag", event=123456)],
        )

    def test_missing_from_top_tag(self):
        event = {"id": 123456}
        koji_proxy = mock.Mock()
        top_tag = "top-tag"

        koji_proxy.getFullInheritance.return_value = [
            {"name": "middle-tag"}, {"name": "bottom-tag"}
        ]
        module_builds = [
            {"name": "foo", "version": "1", "release": "2", "tag_name": "bottom-tag"},
            {"name": "foo", "version": "1", "release": "3", "tag_name": "middle-tag"},
        ]

        result = source_koji.filter_inherited(koji_proxy, event, module_builds, top_tag)

        self.assertItemsEqual(
            result,
            [{"name": "foo", "version": "1", "release": "3", "tag_name": "middle-tag"}],
        )
        self.assertEqual(
            koji_proxy.mock_calls,
            [mock.call.getFullInheritance("top-tag", event=123456)],
        )


class TestFilterByWhitelist(unittest.TestCase):
    def _build(self, n, s, v, c):
        s = s.replace("-", "_")
        return {
            "nvr": "%s-%s-%s.%s" % (n, s, v, c),
            "name": n,
            "version": s,
            "release": "%s.%s" % (v, c),
        }

    def test_no_modules(self):
        compose = mock.Mock()
        module_builds = []
        input_modules = [{"name": "foo:1"}]
        expected = set(["foo:1"])

        source_koji.filter_by_whitelist(compose, module_builds, input_modules, expected)

        self.assertEqual(expected, set(["foo:1"]))

    def test_filter_by_NS(self):
        compose = mock.Mock()
        module_builds = [
            self._build("foo", "1", "201809031048", "cafebabe"),
            self._build("foo", "1", "201809031047", "deadbeef"),
            self._build("foo", "2", "201809031047", "deadbeef"),
        ]
        input_modules = [{"name": "foo:1"}]
        expected = set(["foo:1"])

        result = source_koji.filter_by_whitelist(
            compose, module_builds, input_modules, expected
        )

        self.assertItemsEqual(result, [module_builds[0], module_builds[1]])
        self.assertEqual(expected, set())

    def test_filter_by_NSV(self):
        compose = mock.Mock()
        module_builds = [
            self._build("foo", "1", "201809031048", "cafebabe"),
            self._build("foo", "1", "201809031047", "deadbeef"),
            self._build("foo", "2", "201809031047", "deadbeef"),
        ]
        input_modules = [{"name": "foo:1:201809031047"}]
        expected = set(["foo:1:201809031047"])

        result = source_koji.filter_by_whitelist(
            compose, module_builds, input_modules, expected
        )

        self.assertItemsEqual(result, [module_builds[1]])
        self.assertEqual(expected, set())

    def test_filter_by_NSVC(self):
        compose = mock.Mock()
        module_builds = [
            self._build("foo", "1", "201809031048", "cafebabe"),
            self._build("foo", "1", "201809031047", "deadbeef"),
            self._build("foo", "1", "201809031047", "cafebabe"),
            self._build("foo", "2", "201809031047", "deadbeef"),
        ]
        input_modules = [{"name": "foo:1:201809031047:deadbeef"}]
        expected = set()

        result = source_koji.filter_by_whitelist(
            compose, module_builds, input_modules, expected
        )

        self.assertItemsEqual(result, [module_builds[1]])
        self.assertEqual(expected, set())

    def test_filter_by_wildcard(self):
        compose = mock.Mock()
        module_builds = [
            self._build("foo", "1", "201809031048", "cafebabe"),
            self._build("foo", "1", "201809031047", "deadbeef"),
            self._build("foo", "2", "201809031047", "deadbeef"),
        ]
        input_modules = [{"name": "*"}]
        expected = set(["*"])

        result = source_koji.filter_by_whitelist(
            compose, module_builds, input_modules, expected
        )

        self.assertItemsEqual(result, module_builds)
        self.assertEqual(expected, set())


class MockModule(object):
    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return "MockModule(%r)" % self.path

    def __eq__(self, other):
        return self.path == other.path

    def dup_nsvc(self):
        return "module:master:20190318.abcdef"

    def set_name(self, name):
        pass


@mock.patch("pungi.Modulemd.Module.new_from_file", new=MockModule)
@unittest.skipIf(Modulemd is None, "Skipping tests, no module support")
class TestAddModuleToVariant(unittest.TestCase):

    def setUp(self):
        self.koji = mock.Mock()
        self.koji.koji_module.pathinfo.typedir.return_value = "/koji"
        files = ["modulemd.x86_64.txt", "modulemd.armv7hl.txt", "modulemd.txt"]
        self.koji.koji_proxy.listArchives.return_value = [
            {"btype": "module", "filename": fname} for fname in files
        ] + [{"btype": "foo"}]

    def test_adding_module(self):
        build = {"id": 1234, "extra": {"typeinfo": {"module": {"name": "module"}}}}
        variant = mock.Mock(
            arches=["armhfp", "x86_64"], mmds=[], arch_mmds={}, modules=[]
        )

        source_koji._add_module_to_variant(self.koji, variant, build)

        self.assertEqual(variant.mmds, [MockModule("/koji/modulemd.txt")])
        self.assertEqual(
            variant.arch_mmds,
            {
                "armhfp": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.armv7hl.txt"),
                },
                "x86_64": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.x86_64.txt"),
                },
            },
        )
        self.assertEqual(variant.modules, [])

    def test_adding_module_to_existing(self):
        build = {"id": 1234, "extra": {"typeinfo": {"module": {"name": "module"}}}}
        variant = mock.Mock(
            arches=["armhfp", "x86_64"],
            mmds=[MockModule("/koji/m1.txt")],
            arch_mmds={
                "x86_64": {"m1:latest:20190101.cafe": MockModule("/koji/m1.x86_64.txt")}
            },
            modules=["m1:latest-20190101.cafe"],
        )

        source_koji._add_module_to_variant(self.koji, variant, build)

        self.assertEqual(
            variant.mmds, [MockModule("/koji/m1.txt"), MockModule("/koji/modulemd.txt")]
        )
        self.assertEqual(
            variant.arch_mmds,
            {
                "armhfp": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.armv7hl.txt"),
                },
                "x86_64": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.x86_64.txt"),
                    "m1:latest:20190101.cafe": MockModule("/koji/m1.x86_64.txt"),
                },
            },
        )
        self.assertEqual(variant.modules, ["m1:latest-20190101.cafe"])

    def test_adding_module_with_add_module(self):
        build = {"id": 1234, "extra": {"typeinfo": {"module": {"name": "module"}}}}
        variant = mock.Mock(
            arches=["armhfp", "x86_64"], mmds=[], arch_mmds={}, modules=[]
        )

        source_koji._add_module_to_variant(
            self.koji, variant, build, add_to_variant_modules=True
        )

        self.assertEqual(variant.mmds, [MockModule("/koji/modulemd.txt")])
        self.assertEqual(
            variant.arch_mmds,
            {
                "armhfp": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.armv7hl.txt"),
                },
                "x86_64": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.x86_64.txt"),
                },
            },
        )
        self.assertEqual(variant.modules, ["module:master:20190318.abcdef"])

    def test_adding_module_to_existing_with_add_module(self):
        build = {"id": 1234, "extra": {"typeinfo": {"module": {"name": "module"}}}}
        variant = mock.Mock(
            arches=["armhfp", "x86_64"],
            mmds=[MockModule("/koji/m1.txt")],
            arch_mmds={
                "x86_64": {"m1:latest:20190101.cafe": MockModule("/koji/m1.x86_64.txt")}
            },
            modules=["m1:latest-20190101.cafe"],
        )

        source_koji._add_module_to_variant(
            self.koji, variant, build, add_to_variant_modules=True
        )

        self.assertEqual(
            variant.mmds, [MockModule("/koji/m1.txt"), MockModule("/koji/modulemd.txt")]
        )
        self.assertEqual(
            variant.arch_mmds,
            {
                "armhfp": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.armv7hl.txt"),
                },
                "x86_64": {
                    "module:master:20190318.abcdef": MockModule("/koji/modulemd.x86_64.txt"),
                    "m1:latest:20190101.cafe": MockModule("/koji/m1.x86_64.txt"),
                },
            },
        )
        self.assertEqual(
            variant.modules,
            ["m1:latest-20190101.cafe", "module:master:20190318.abcdef"],
        )
