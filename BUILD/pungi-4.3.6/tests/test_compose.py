# -*- coding: utf-8 -*-

import logging
import mock

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import os
import six
import tempfile
import shutil
import json

from pungi.compose import Compose


class ConfigWrapper(dict):
    def __init__(self, *args, **kwargs):
        super(ConfigWrapper, self).__init__(*args, **kwargs)
        self._open_file = "%s/fixtures/config.conf" % os.path.abspath(
            os.path.dirname(__file__)
        )


class ComposeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

        # Basic ComposeInfo metadata used in tests.
        self.ci_json = {
            "header": {"type": "productmd.composeinfo", "version": mock.ANY},
            "payload": {
                "compose": {
                    "date": "20200526",
                    "id": "test-1.0-20200526.0",
                    "respin": 0,
                    "type": "production",
                },
                "release": {
                    "internal": False,
                    "name": "Test",
                    "short": "test",
                    "type": "ga",
                    "version": "1.0",
                },
                "variants": {},
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @mock.patch("pungi.compose.ComposeInfo")
    def test_setup_logger(self, ci):
        conf = {}
        logger = logging.getLogger("test_setup_logger")
        logger.setLevel(logging.DEBUG)
        compose = Compose(conf, self.tmp_dir, logger=logger)
        self.assertEqual(len(logger.handlers), 2)

        pungi_log = logger.handlers[0].stream.name
        exclude_arch_log = logger.handlers[1].stream.name
        self.assertEqual(os.path.basename(pungi_log), "pungi.global.log")
        self.assertEqual(
            os.path.basename(exclude_arch_log), "excluding-arch.global.log"
        )

        msg = "test log"
        compose.log_info(msg)
        with open(pungi_log) as f:
            self.assertTrue(msg in f.read())
        with open(exclude_arch_log) as f:
            self.assertTrue(msg not in f.read())

        msg = "Populating package set for arch: x86_64"
        compose.log_info(msg)
        with open(exclude_arch_log) as f:
            self.assertTrue(msg in f.read())

    @mock.patch("pungi.compose.ComposeInfo")
    def test_can_fail(self, ci):
        conf = {
            "failable_deliverables": [
                (
                    "^.*$",
                    {"*": ["buildinstall"], "i386": ["buildinstall", "live", "iso"]},
                ),
            ]
        }
        compose = Compose(conf, self.tmp_dir)
        variant = mock.Mock(uid="Server")

        self.assertTrue(compose.can_fail(variant, "x86_64", "buildinstall"))
        self.assertFalse(compose.can_fail(variant, "x86_64", "live"))
        self.assertTrue(compose.can_fail(variant, "i386", "live"))

        self.assertFalse(compose.can_fail(None, "x86_64", "live"))
        self.assertTrue(compose.can_fail(None, "i386", "live"))

        self.assertTrue(compose.can_fail(variant, "*", "buildinstall"))
        self.assertFalse(compose.can_fail(variant, "*", "live"))

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_image_name(self, ci):
        conf = {}
        variant = mock.Mock(uid="Server", type="variant")
        ci.return_value.compose.respin = 2
        ci.return_value.compose.id = "compose_id"
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.0"
        ci.return_value.compose.label_major_version = "1"

        ci.return_value.release.version = "3.0"
        ci.return_value.release.short = "rel_short"

        compose = Compose(conf, self.tmp_dir)

        keys = [
            "arch",
            "compose_id",
            "date",
            "disc_num",
            "disc_type",
            "label",
            "label_major_version",
            "release_short",
            "respin",
            "suffix",
            "type",
            "type_suffix",
            "variant",
            "version",
        ]
        format = "-".join(["%(" + k + ")s" for k in keys])
        name = compose.get_image_name(
            "x86_64",
            variant,
            format=format,
            disc_num=7,
            disc_type="live",
            suffix=".iso",
        )

        self.assertEqual(
            name,
            "-".join(
                [
                    "x86_64",
                    "compose_id",
                    "20160107",
                    "7",
                    "live",
                    "RC-1.0",
                    "1",
                    "rel_short",
                    "2",
                    ".iso",
                    "nightly",
                    ".n",
                    "Server",
                    "3.0",
                ]
            ),
        )

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_image_name_variant_mapping(self, ci):
        conf = {"image_name_format": {"^Server$": "whatever"}}
        variant = mock.Mock(uid="Server", type="variant")

        compose = Compose(conf, self.tmp_dir)

        name = compose.get_image_name(
            "x86_64", variant, disc_num=7, disc_type="live", suffix=".iso"
        )

        self.assertEqual(name, "whatever")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_image_name_variant_mapping_no_match(self, ci):
        conf = {"image_name_format": {"^Client$": "whatever"}}
        variant = mock.Mock(uid="Server", type="variant")
        ci.return_value.compose.id = "compose_id"

        compose = Compose(conf, self.tmp_dir)
        name = compose.get_image_name(
            "x86_64", variant, disc_num=7, disc_type="live", suffix=".iso"
        )

        self.assertEqual(name, "compose_id-Server-x86_64-live7.iso")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_image_name_layered_product(self, ci):
        conf = {}
        variant = mock.Mock(uid="Server-LP", type="layered-product")
        variant.parent = mock.Mock(uid="Server")
        ci.return_value.compose.respin = 2
        ci.return_value.compose.id = "compose_id"
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.0"
        ci.return_value.compose.label_major_version = "1"

        ci.return_value.release.version = "3.0"
        ci.return_value.release.short = "rel_short"

        ci.return_value["Server-LP"].compose_id = "Gluster 1.0"

        compose = Compose(conf, self.tmp_dir)

        format = "{compose_id} {variant}"
        name = compose.get_image_name(
            "x86_64",
            variant,
            format=format,
            disc_num=7,
            disc_type="live",
            suffix=".iso",
        )

        self.assertEqual(name, "Gluster 1.0 Server")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_image_name_type_netinst(self, ci):
        conf = {}
        variant = mock.Mock(uid="Server", type="variant")
        ci.return_value.compose.respin = 2
        ci.return_value.compose.id = "compose_id"
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.0"
        ci.return_value.compose.label_major_version = "1"

        ci.return_value.release.version = "3.0"
        ci.return_value.release.short = "rel_short"

        compose = Compose(conf, self.tmp_dir)

        keys = [
            "arch",
            "compose_id",
            "date",
            "disc_num",
            "disc_type",
            "label",
            "label_major_version",
            "release_short",
            "respin",
            "suffix",
            "type",
            "type_suffix",
            "variant",
            "version",
        ]
        format = "-".join(["%(" + k + ")s" for k in keys])
        name = compose.get_image_name(
            "x86_64",
            variant,
            format=format,
            disc_num=7,
            disc_type="netinst",
            suffix=".iso",
        )

        self.assertEqual(
            name,
            "-".join(
                [
                    "x86_64",
                    "compose_id",
                    "20160107",
                    "7",
                    "netinst",
                    "RC-1.0",
                    "1",
                    "rel_short",
                    "2",
                    ".iso",
                    "nightly",
                    ".n",
                    "Server",
                    "3.0",
                ]
            ),
        )

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_release(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = None

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_release, "20160107.n.2")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_release_production(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "production"
        ci.return_value.compose.type_suffix = ""
        ci.return_value.compose.label = None

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_release, "20160107.2")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_release_from_label(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "production"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "Alpha-1.2"

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_release, "1.2")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_version_without_label(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = None
        ci.return_value.release.version = "25"

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_version, "25")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_version_with_label(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "Alpha-1.2"
        ci.return_value.release.version = "25"

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_version, "25_Alpha")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_image_version_with_label_rc(self, ci):
        conf = {}
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.2"
        ci.return_value.release.version = "25"

        compose = Compose(conf, self.tmp_dir)

        self.assertEqual(compose.image_version, "25")

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_variant_arches_without_filter(self, ci):
        ci.return_value.compose.id = "composeid"

        conf = ConfigWrapper(
            variants_file={"scm": "file", "repo": None, "file": "variants.xml"},
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
        )

        compose = Compose(conf, self.tmp_dir)
        compose.read_variants()

        self.assertEqual(
            sorted(v.uid for v in compose.variants.values()),
            ["Client", "Crashy", "Live", "Server"],
        )
        self.assertEqual(
            sorted(v.uid for v in compose.variants["Server"].variants.values()),
            ["Server-Gluster", "Server-ResilientStorage", "Server-optional"],
        )
        six.assertCountEqual(
            self, compose.variants["Client"].arches, ["i386", "x86_64"]
        )
        self.assertEqual(compose.variants["Crashy"].arches, ["ppc64le"])
        self.assertEqual(compose.variants["Live"].arches, ["x86_64"])
        six.assertCountEqual(
            self, compose.variants["Server"].arches, ["s390x", "x86_64"]
        )
        self.assertEqual(
            compose.variants["Server"].variants["Gluster"].arches, ["x86_64"]
        )
        self.assertEqual(
            compose.variants["Server"].variants["ResilientStorage"].arches, ["x86_64"]
        )
        six.assertCountEqual(
            self,
            compose.variants["Server"].variants["optional"].arches,
            ["s390x", "x86_64"],
        )

        self.assertEqual(
            [v.uid for v in compose.get_variants()],
            [
                "Client",
                "Crashy",
                "Live",
                "Server",
                "Server-Gluster",
                "Server-ResilientStorage",
                "Server-optional",
            ],
        )
        self.assertEqual(compose.get_arches(), ["i386", "ppc64le", "s390x", "x86_64"])

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_variant_arches_with_arch_filter(self, ci):
        ci.return_value.compose.id = "composeid"

        conf = ConfigWrapper(
            variants_file={"scm": "file", "repo": None, "file": "variants.xml"},
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
            tree_arches=["x86_64"],
        )

        compose = Compose(conf, self.tmp_dir)
        compose.read_variants()

        self.assertEqual(
            sorted(v.uid for v in compose.variants.values()),
            ["Client", "Live", "Server"],
        )
        self.assertEqual(
            sorted(v.uid for v in compose.variants["Server"].variants.values()),
            ["Server-Gluster", "Server-ResilientStorage", "Server-optional"],
        )
        self.assertEqual(compose.variants["Client"].arches, ["x86_64"])
        self.assertEqual(compose.variants["Live"].arches, ["x86_64"])
        self.assertEqual(compose.variants["Server"].arches, ["x86_64"])
        self.assertEqual(
            compose.variants["Server"].variants["Gluster"].arches, ["x86_64"]
        )
        self.assertEqual(
            compose.variants["Server"].variants["ResilientStorage"].arches, ["x86_64"]
        )
        self.assertEqual(
            compose.variants["Server"].variants["optional"].arches, ["x86_64"]
        )

        self.assertEqual(compose.get_arches(), ["x86_64"])
        self.assertEqual(
            [v.uid for v in compose.get_variants()],
            [
                "Client",
                "Live",
                "Server",
                "Server-Gluster",
                "Server-ResilientStorage",
                "Server-optional",
            ],
        )

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_variant_arches_with_variant_filter(self, ci):
        ci.return_value.compose.id = "composeid"
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "production"
        ci.return_value.compose.type_suffix = ".n"

        conf = ConfigWrapper(
            variants_file={"scm": "file", "repo": None, "file": "variants.xml"},
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
            tree_variants=["Server", "Client", "Server-Gluster"],
        )

        compose = Compose(conf, self.tmp_dir)
        compose.read_variants()

        self.assertEqual(
            sorted(v.uid for v in compose.variants.values()), ["Client", "Server"]
        )
        six.assertCountEqual(
            self, compose.variants["Client"].arches, ["i386", "x86_64"]
        )
        six.assertCountEqual(
            self, compose.variants["Server"].arches, ["s390x", "x86_64"]
        )
        self.assertEqual(
            compose.variants["Server"].variants["Gluster"].arches, ["x86_64"]
        )

        self.assertEqual(compose.get_arches(), ["i386", "s390x", "x86_64"])
        self.assertEqual(
            [v.uid for v in compose.get_variants()],
            ["Client", "Server", "Server-Gluster"],
        )

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_variant_arches_with_both_filters(self, ci):
        ci.return_value.compose.id = "composeid"
        ci.return_value.compose.respin = 2
        ci.return_value.compose.date = "20160107"
        ci.return_value.compose.type = "production"
        ci.return_value.compose.type_suffix = ".n"

        logger = mock.Mock()
        logger.handlers = []

        conf = ConfigWrapper(
            variants_file={"scm": "file", "repo": None, "file": "variants.xml"},
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
            tree_variants=["Server", "Client", "Server-optional"],
            tree_arches=["x86_64"],
        )

        compose = Compose(conf, self.tmp_dir, logger=logger)
        compose.read_variants()

        self.assertEqual(
            sorted(v.uid for v in compose.variants.values()), ["Client", "Server"]
        )
        self.assertEqual(compose.variants["Client"].arches, ["x86_64"])
        self.assertEqual(compose.variants["Server"].arches, ["x86_64"])
        self.assertEqual(
            compose.variants["Server"].variants["optional"].arches, ["x86_64"]
        )

        self.assertEqual(compose.get_arches(), ["x86_64"])
        self.assertEqual(
            [v.uid for v in compose.get_variants()],
            ["Client", "Server", "Server-optional"],
        )

        six.assertCountEqual(
            self,
            logger.info.call_args_list,
            [
                mock.call("Excluding variant Live: filtered by configuration."),
                mock.call("Excluding variant Crashy: all its arches are filtered."),
                mock.call(
                    "Excluding variant Server-ResilientStorage: filtered by configuration."  # noqa: E501
                ),
                mock.call(
                    "Excluding variant Server-Gluster: filtered by configuration."
                ),
            ],
        )

    @mock.patch("pungi.compose.ComposeInfo")
    def test_mkdtemp(self, ci):
        ci.return_value.compose.id = "composeid"
        conf = ConfigWrapper(
            variants_file={"scm": "file", "repo": None, "file": "variants.xml"},
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
            tree_variants=["Server", "Client", "Server-optional"],
            tree_arches=["x86_64"],
        )
        compose = Compose(conf, self.tmp_dir)
        d = compose.mkdtemp()
        self.assertTrue(os.path.isdir(d))
        d = compose.mkdtemp(prefix="tweak_buildinstall")
        self.assertTrue(os.path.isdir(d))

    @mock.patch("time.strftime", new=lambda fmt, time: "20200526")
    def test_get_compose_info(self):
        conf = ConfigWrapper(
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
        )

        ci = Compose.get_compose_info(conf)
        ci_json = json.loads(ci.dumps())
        self.assertEqual(ci_json, self.ci_json)

    @mock.patch("time.strftime", new=lambda fmt, time: "20200526")
    def test_get_compose_info_cts(self):
        conf = ConfigWrapper(
            release_name="Test",
            release_version="1.0",
            release_short="test",
            release_type="ga",
            release_internal=False,
            cts_url="https://cts.localhost.tld/",
            cts_keytab="/tmp/some.keytab",
        )

        # The `mock.ANY` in ["header"]["version"] cannot be serialized,
        # so for this test, we replace it with real version.
        ci_copy = dict(self.ci_json)
        ci_copy["header"]["version"] = "1.2"
        mocked_response = mock.MagicMock()
        mocked_response.text = json.dumps(self.ci_json)
        mocked_requests = mock.MagicMock()
        mocked_requests.post.return_value = mocked_response

        mocked_requests_kerberos = mock.MagicMock()

        # The `requests` and `requests_kerberos` modules are imported directly
        # in the `get_compose_info` function. To patch them, we need to patch
        # the `sys.modules` directly so the patched modules are returned by
        # `import`.
        with mock.patch.dict(
            "sys.modules",
            requests=mocked_requests,
            requests_kerberos=mocked_requests_kerberos,
        ):
            ci = Compose.get_compose_info(conf, respin_of="Fedora-Rawhide-20200517.n.1")
            ci_json = json.loads(ci.dumps())
            self.assertEqual(ci_json, self.ci_json)

            expected_json = {
                "compose_info": self.ci_json,
                "parent_compose_ids": None,
                "respin_of": "Fedora-Rawhide-20200517.n.1",
            }

            mocked_response.raise_for_status.assert_called_once()
            mocked_requests.post.assert_called_once_with(
                "https://cts.localhost.tld/api/1/composes/",
                auth=mock.ANY,
                json=expected_json,
            )


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.logger = mock.Mock()
        self.logger.handlers = []
        with mock.patch("pungi.compose.ComposeInfo"):
            self.compose = Compose({}, self.tmp_dir, logger=self.logger)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_get_status_non_existing(self):
        status = self.compose.get_status()
        self.assertIsNone(status)

    def test_get_status_existing(self):
        with open(os.path.join(self.tmp_dir, "STATUS"), "w") as f:
            f.write("FOOBAR")

        self.assertEqual(self.compose.get_status(), "FOOBAR")

    def test_get_status_is_dir(self):
        os.mkdir(os.path.join(self.tmp_dir, "STATUS"))

        self.assertIsNone(self.compose.get_status())

    def test_write_status(self):
        self.compose.write_status("DOOMED")

        with open(os.path.join(self.tmp_dir, "STATUS"), "r") as f:
            self.assertEqual(f.read(), "DOOMED\n")

    def test_write_non_standard_status(self):
        self.compose.write_status("FOOBAR")

        self.assertEqual(self.logger.log.call_count, 1)
        with open(os.path.join(self.tmp_dir, "STATUS"), "r") as f:
            self.assertEqual(f.read(), "FOOBAR\n")

    def test_write_status_on_finished(self):
        self.compose.write_status("FINISHED")

        with self.assertRaises(RuntimeError):
            self.compose.write_status("NOT REALLY")

    def test_write_status_with_failed_deliverables(self):
        self.compose.conf = {
            "failable_deliverables": [("^.+$", {"*": ["live", "build-image"]})]
        }

        variant = mock.Mock(uid="Server")
        self.compose.fail_deliverable(variant, "x86_64", "live")
        self.compose.fail_deliverable(None, "*", "build-image")

        self.compose.write_status("FINISHED")

        self.logger.log.assert_has_calls(
            [
                mock.call(
                    20, "Failed build-image on variant <>, arch <*>, subvariant <None>."
                ),
                mock.call(
                    20,
                    "Failed live on variant <Server>, arch <x86_64>, subvariant <None>.",  # noqa: E501
                ),
            ],
            any_order=True,
        )

        with open(os.path.join(self.tmp_dir, "STATUS"), "r") as f:
            self.assertEqual(f.read(), "FINISHED_INCOMPLETE\n")

    def test_calls_notifier(self):
        self.compose.notifier = mock.Mock()
        self.compose.write_status("FINISHED")

        self.assertTrue(self.compose.notifier.send.call_count, 1)

    def test_no_database_with_dnf_backend(self):
        self.compose.conf["gather_backend"] = "dnf"
        self.assertFalse(self.compose.should_create_yum_database)

    def test_no_database_with_dnf_backend_config_override(self):
        self.compose.conf["gather_backend"] = "dnf"
        self.compose.conf["createrepo_database"] = True
        self.assertTrue(self.compose.should_create_yum_database)

    def test_no_database_with_yum_backend(self):
        self.compose.conf["gather_backend"] = "yum"
        self.assertTrue(self.compose.should_create_yum_database)

    def test_no_database_with_yum_backend_config_override(self):
        self.compose.conf["gather_backend"] = "yum"
        self.compose.conf["createrepo_database"] = False
        self.assertFalse(self.compose.should_create_yum_database)


class DumpContainerMetadataTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        with mock.patch("pungi.compose.ComposeInfo"):
            self.compose = Compose({}, self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_dump_metadata(self):
        metadata = {"Server": {"x86_64": "Metadata"}}
        self.compose.containers_metadata = metadata
        self.compose.dump_containers_metadata()

        with open(self.tmp_dir + "/compose/metadata/osbs.json") as f:
            data = json.load(f)
            self.assertEqual(data, metadata)

    @mock.patch("pungi.phases.osbs.ThreadPool")
    def test_dump_empty_metadata(self, ThreadPool):
        self.compose.dump_containers_metadata()
        self.assertFalse(os.path.isfile(self.tmp_dir + "/compose/metadata/osbs.json"))


class TracebackTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        with mock.patch("pungi.compose.ComposeInfo"):
            self.compose = Compose({}, self.tmp_dir)
        self.patcher = mock.patch("kobo.tback.Traceback")
        self.Traceback = self.patcher.start()
        self.Traceback.return_value.get_traceback.return_value = b"traceback"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)
        self.patcher.stop()

    def assertTraceback(self, filename):
        self.assertTrue(
            os.path.isfile("%s/logs/global/%s.global.log" % (self.tmp_dir, filename))
        )
        self.assertEqual(
            self.Traceback.mock_calls, [mock.call(), mock.call().get_traceback()]
        )

    def test_traceback_default(self):
        self.compose.traceback()
        self.assertTraceback("traceback")

    def test_with_detail(self):
        self.compose.traceback("extra-info")
        self.assertTraceback("traceback-extra-info")
