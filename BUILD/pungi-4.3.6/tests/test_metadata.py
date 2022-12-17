import mock
import os

import six

from tests import helpers

from pungi import metadata
from pungi.compose_metadata import discinfo


class DiscInfoTestCase(helpers.PungiTestCase):
    def setUp(self):
        super(DiscInfoTestCase, self).setUp()
        os.environ["SOURCE_DATE_EPOCH"] = "101010101"
        self.path = os.path.join(self.topdir, "compose/Server/x86_64/os/.discinfo")

    def test_write_discinfo_variant(self):
        compose = helpers.DummyCompose(
            self.topdir, {"release_name": "Test", "release_version": "1.0"}
        )

        metadata.write_discinfo(compose, "x86_64", compose.variants["Server"])

        with open(self.path) as f:
            self.assertEqual(
                f.read().strip().split("\n"), ["101010101", "Test 1.0", "x86_64", "ALL"]
            )

        self.assertEqual(
            discinfo.read_discinfo(self.path),
            {
                "timestamp": "101010101",
                "description": "Test 1.0",
                "disc_numbers": ["ALL"],
                "arch": "x86_64",
            },
        )

    def test_write_discinfo_custom_description(self):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_name": "Test",
                "release_version": "1.0",
                "release_discinfo_description": "Fuzzy %(variant_name)s.%(arch)s",
            },
        )
        compose.variants["Server"].name = "Server"

        metadata.write_discinfo(compose, "x86_64", compose.variants["Server"])

        with open(self.path) as f:
            self.assertEqual(
                f.read().strip().split("\n"),
                ["101010101", "Fuzzy Server.x86_64", "x86_64", "ALL"],
            )

    def test_write_discinfo_layered_product(self):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_name": "Test",
                "release_version": "1.0",
                "base_product_name": "Base",
                "base_product_version": 42,
            },
        )

        metadata.write_discinfo(compose, "x86_64", compose.variants["Server"])

        with open(self.path) as f:
            self.assertEqual(
                f.read().strip().split("\n"),
                ["101010101", "Test 1.0 for Base 42", "x86_64", "ALL"],
            )

    def test_write_discinfo_integrated_layered_product(self):
        compose = helpers.DummyCompose(
            self.topdir, {"release_name": "Test", "release_version": "1.0"}
        )
        compose.variants["ILP"] = mock.Mock(
            uid="Server",
            arches=["x86_64"],
            type="layered-product",
            is_empty=False,
            release_name="Integrated",
            release_version="2.1",
            parent=compose.variants["Server"],
        )

        metadata.write_discinfo(compose, "x86_64", compose.variants["ILP"])

        with open(self.path) as f:
            self.assertEqual(
                f.read().strip().split("\n"),
                ["101010101", "Integrated 2.1 for Test 1", "x86_64", "ALL"],
            )

    def test_addons_dont_have_discinfo(self):
        compose = helpers.DummyCompose(
            self.topdir, {"release_name": "Test", "release_version": "1.0"}
        )
        compose.variants["ILP"] = mock.Mock(
            uid="Server",
            arches=["x86_64"],
            type="addon",
            is_empty=False,
            parent=compose.variants["Server"],
        )

        metadata.write_discinfo(compose, "x86_64", compose.variants["ILP"])

        self.assertFalse(os.path.isfile(self.path))


class MediaRepoTestCase(helpers.PungiTestCase):
    def setUp(self):
        super(MediaRepoTestCase, self).setUp()
        self.path = os.path.join(self.topdir, "compose/Server/x86_64/os/media.repo")

    def test_write_media_repo(self):
        compose = helpers.DummyCompose(
            self.topdir, {"release_name": "Test", "release_version": "1.0"}
        )

        metadata.write_media_repo(
            compose, "x86_64", compose.variants["Server"], timestamp=123456
        )

        with open(self.path) as f:
            lines = f.read().strip().split("\n")
            self.assertEqual(lines[0], "[InstallMedia]")
            six.assertCountEqual(
                self,
                lines[1:],
                [
                    "name=Test 1.0",
                    "mediaid=123456",
                    "metadata_expire=-1",
                    "gpgcheck=0",
                    "cost=500",
                ],
            )

    def test_addons_dont_have_media_repo(self):
        compose = helpers.DummyCompose(
            self.topdir, {"release_name": "Test", "release_version": "1.0"}
        )
        compose.variants["ILP"] = mock.Mock(
            uid="Server",
            arches=["x86_64"],
            type="addon",
            is_empty=False,
            parent=compose.variants["Server"],
        )

        metadata.write_discinfo(compose, "x86_64", compose.variants["ILP"])

        self.assertFalse(os.path.isfile(self.path))


FOO_MD5 = {"md5": "acbd18db4cc2f85cedef654fccc4a4d8"}
BAR_MD5 = {"md5": "37b51d194a7513e45b56f6524f2d51f2"}


class TestPopulateExtraFiles(helpers.PungiTestCase):
    def setUp(self):
        super(TestPopulateExtraFiles, self).setUp()
        self.variant = mock.Mock(uid="Server")
        self.metadata = mock.Mock()

    def test_with_relative_root(self):
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/foo"), content="foo"
        )
        helpers.touch(
            os.path.join(self.topdir, "compose/Server/x86_64/os/bar"), content="bar"
        )

        metadata.populate_extra_files_metadata(
            self.metadata,
            self.variant,
            "x86_64",
            os.path.join(self.topdir, "compose/Server/x86_64/os"),
            ["foo", "bar"],
            ["md5"],
            relative_root=os.path.join(self.topdir, "compose"),
        )

        self.maxDiff = None

        six.assertCountEqual(
            self,
            self.metadata.mock_calls,
            [
                mock.call.add("Server", "x86_64", "Server/x86_64/os/foo", 3, FOO_MD5),
                mock.call.add("Server", "x86_64", "Server/x86_64/os/bar", 3, BAR_MD5),
                mock.call.dump_for_tree(
                    mock.ANY, "Server", "x86_64", "Server/x86_64/os/"
                ),
            ],
        )

    def test_without_relative_root(self):
        helpers.touch(os.path.join(self.topdir, "foo"), content="foo")
        helpers.touch(os.path.join(self.topdir, "bar"), content="bar")

        metadata.populate_extra_files_metadata(
            self.metadata, self.variant, "x86_64", self.topdir, ["foo", "bar"], ["md5"]
        )

        six.assertCountEqual(
            self,
            self.metadata.mock_calls,
            [
                mock.call.add("Server", "x86_64", "foo", 3, FOO_MD5),
                mock.call.add("Server", "x86_64", "bar", 3, BAR_MD5),
                mock.call.dump_for_tree(mock.ANY, "Server", "x86_64", ""),
            ],
        )
