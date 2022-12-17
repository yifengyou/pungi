# -*- coding: utf-8 -*-

import mock
import os
import shutil
import six
from six.moves.configparser import ConfigParser

from tests.helpers import PungiTestCase, FIXTURE_DIR, touch, mk_boom
from pungi_utils import unified_isos


COMPOSE_ID = "DP-1.0-20161013.t.4"


class TestUnifiedIsos(PungiTestCase):
    def setUp(self):
        super(TestUnifiedIsos, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )

    def test_can_init(self):
        compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        isos = unified_isos.UnifiedISO(compose_path)
        self.assertEqual(isos.compose_path, compose_path)
        self.assertRegex(
            isos.temp_dir, "^%s/" % os.path.join(self.topdir, COMPOSE_ID, "work")
        )

    def test_can_find_compose_subdir(self):
        isos = unified_isos.UnifiedISO(os.path.join(self.topdir, COMPOSE_ID))
        self.assertEqual(
            isos.compose_path, os.path.join(self.topdir, COMPOSE_ID, "compose")
        )
        self.assertRegex(
            isos.temp_dir, "^%s/" % os.path.join(self.topdir, COMPOSE_ID, "work")
        )

    @mock.patch("os.rename")
    def test_dump_manifest(self, rename):
        compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        isos = unified_isos.UnifiedISO(compose_path)
        isos.compose._images = mock.Mock()
        isos.dump_manifest()
        self.assertEqual(
            isos.compose._images.mock_calls,
            [mock.call.dump(compose_path + "/metadata/images.json.tmp")],
        )
        self.assertEqual(
            rename.call_args_list,
            [
                mock.call(
                    compose_path + "/metadata/images.json.tmp",
                    compose_path + "/metadata/images.json",
                )
            ],
        )

    @mock.patch("os.rename")
    def test_dump_manifest_fails(self, rename):
        compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        isos = unified_isos.UnifiedISO(compose_path)
        isos.compose._images = mock.Mock()
        isos.compose._images.dump.side_effect = mk_boom()
        with self.assertRaises(Exception):
            isos.dump_manifest()
        self.assertEqual(
            isos.compose._images.mock_calls,
            [mock.call.dump(compose_path + "/metadata/images.json.tmp")],
        )
        self.assertEqual(rename.call_args_list, [])


class TestCreate(PungiTestCase):
    def setUp(self):
        super(TestCreate, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(compose_path)

    def test_create_method(self):
        methods = (
            "link_to_temp",
            "createrepo",
            "discinfo",
            "createiso",
            "update_checksums",
            "dump_manifest",
        )
        for attr in methods:
            setattr(self.isos, attr, mock.Mock())

        with mock.patch("shutil.rmtree") as rmtree:
            self.isos.create()

        for attr in methods:
            self.assertEqual(len(getattr(self.isos, attr).call_args_list), 1)
        self.assertEqual(rmtree.call_args_list, [mock.call(self.isos.temp_dir)])


def get_comps_mapping(path):
    def _comps(variant, arch):
        return os.path.join(
            path, variant, arch, "os", "repodata", "comps-%s.%s.xml" % (variant, arch)
        )

    return {
        "i386": {"Client": _comps("Client", "i386")},
        "s390x": {"Server": _comps("Server", "s390x")},
        "x86_64": {
            "Client": _comps("Client", "x86_64"),
            "Server": _comps("Server", "x86_64"),
        },
    }


def get_productid_mapping(path):
    def _productid(variant, arch):
        return os.path.join(path, variant, arch, "os", "repodata", "productid")

    return {
        "i386": {"Client": _productid("Client", "i386")},
        "s390x": {"Server": _productid("Server", "s390x")},
        "x86_64": {
            "Client": _productid("Client", "x86_64"),
            "Server": _productid("Server", "x86_64"),
        },
    }


def get_repos_mapping(path):
    def _repo(variant, arch):
        return os.path.join(path, "trees", arch, variant)

    def _debug(variant, arch):
        return os.path.join(path, "trees", "debug-" + arch, variant)

    return {
        "i386": {"Client": _repo("Client", "i386")},
        "debug-i386": {"Client": _debug("Client", "i386")},
        "s390x": {"Server": _repo("Server", "s390x")},
        "debug-s390x": {"Server": _debug("Server", "s390x")},
        "src": {"Client": _repo("Client", "src"), "Server": _repo("Server", "src")},
        "x86_64": {
            "Client": _repo("Client", "x86_64"),
            "Server": _repo("Server", "x86_64"),
        },
        "debug-x86_64": {
            "Client": _debug("Client", "x86_64"),
            "Server": _debug("Server", "x86_64"),
        },
    }


class TestLinkToTemp(PungiTestCase):
    def setUp(self):
        super(TestLinkToTemp, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        self.compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(self.compose_path)
        self.isos.linker = mock.Mock()

    def _linkCall(self, variant, arch, file):
        debuginfo = "debuginfo" in file
        srcdir = "tree" if arch == "src" else "debug/tree" if debuginfo else "os"
        destdir = "debug-" + arch if debuginfo else arch
        return mock.call(
            os.path.join(
                self.compose_path,
                variant,
                arch if arch != "src" else "source",
                srcdir,
                "Packages",
                file[0].lower(),
                file,
            ),
            os.path.join(self.isos.temp_dir, "trees", destdir, variant, file),
        )

    def test_link_to_temp(self):
        self.isos.link_to_temp()

        six.assertCountEqual(
            self,
            self.isos.treeinfo.keys(),
            [
                "i386",
                "s390x",
                "src",
                "x86_64",
                "debug-i386",
                "debug-s390x",
                "debug-x86_64",
            ],
        )
        self.assertEqual(self.isos.comps, get_comps_mapping(self.compose_path))
        self.assertEqual(self.isos.productid, get_productid_mapping(self.compose_path))
        self.assertEqual(self.isos.repos, get_repos_mapping(self.isos.temp_dir))

        six.assertCountEqual(
            self,
            self.isos.linker.link.call_args_list,
            [
                self._linkCall(
                    "Server", "s390x", "dummy-filesystem-4.2.37-6.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "s390x", "dummy-elinks-debuginfo-2.6-2.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-filesystem-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-elinks-debuginfo-2.6-2.x86_64.rpm"
                ),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Client", "i386", "dummy-bash-4.2.37-6.i686.rpm"),
                self._linkCall(
                    "Client", "i386", "dummy-bash-debuginfo-4.2.37-6.i686.rpm"
                ),
                self._linkCall("Client", "x86_64", "dummy-bash-4.2.37-6.x86_64.rpm"),
                self._linkCall(
                    "Client", "x86_64", "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall("Client", "src", "dummy-bash-4.2.37-6.src.rpm"),
                self._linkCall("Client", "src", "dummy-bash-4.2.37-6.src.rpm"),
            ],
        )

    def test_link_to_temp_without_treefile(self):
        os.remove(os.path.join(self.compose_path, "Client", "i386", "os", ".treeinfo"))

        with mock.patch("sys.stderr"):
            self.isos.link_to_temp()

        six.assertCountEqual(
            self,
            self.isos.treeinfo.keys(),
            ["s390x", "src", "x86_64", "debug-s390x", "debug-x86_64"],
        )
        comps = get_comps_mapping(self.compose_path)
        comps.pop("i386")
        self.assertEqual(self.isos.comps, comps)
        productid = get_productid_mapping(self.compose_path)
        productid.pop("i386")
        self.assertEqual(self.isos.productid, productid)
        repos = get_repos_mapping(self.isos.temp_dir)
        repos.pop("i386")
        repos.pop("debug-i386")
        self.assertEqual(self.isos.repos, repos)

        self.maxDiff = None

        six.assertCountEqual(
            self,
            self.isos.linker.link.call_args_list,
            [
                self._linkCall(
                    "Server", "s390x", "dummy-filesystem-4.2.37-6.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "s390x", "dummy-elinks-debuginfo-2.6-2.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-filesystem-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-elinks-debuginfo-2.6-2.x86_64.rpm"
                ),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Client", "x86_64", "dummy-bash-4.2.37-6.x86_64.rpm"),
                self._linkCall(
                    "Client", "x86_64", "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall("Client", "src", "dummy-bash-4.2.37-6.src.rpm"),
            ],
        )

    def test_link_to_temp_extra_file(self):
        gpl_file = touch(
            os.path.join(self.compose_path, "Server", "x86_64", "os", "GPL")
        )

        self.isos.link_to_temp()

        six.assertCountEqual(
            self,
            self.isos.treeinfo.keys(),
            [
                "i386",
                "s390x",
                "src",
                "x86_64",
                "debug-i386",
                "debug-s390x",
                "debug-x86_64",
            ],
        )
        self.assertEqual(self.isos.comps, get_comps_mapping(self.compose_path))
        self.assertEqual(self.isos.productid, get_productid_mapping(self.compose_path))
        self.assertEqual(self.isos.repos, get_repos_mapping(self.isos.temp_dir))

        six.assertCountEqual(
            self,
            self.isos.linker.link.call_args_list,
            [
                self._linkCall(
                    "Server", "s390x", "dummy-filesystem-4.2.37-6.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "s390x", "dummy-elinks-debuginfo-2.6-2.s390x.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-filesystem-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall(
                    "Server", "x86_64", "dummy-elinks-debuginfo-2.6-2.x86_64.rpm"
                ),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Server", "src", "dummy-filesystem-4.2.37-6.src.rpm"),
                self._linkCall("Client", "i386", "dummy-bash-4.2.37-6.i686.rpm"),
                self._linkCall(
                    "Client", "i386", "dummy-bash-debuginfo-4.2.37-6.i686.rpm"
                ),
                self._linkCall("Client", "x86_64", "dummy-bash-4.2.37-6.x86_64.rpm"),
                self._linkCall(
                    "Client", "x86_64", "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm"
                ),
                self._linkCall("Client", "src", "dummy-bash-4.2.37-6.src.rpm"),
                self._linkCall("Client", "src", "dummy-bash-4.2.37-6.src.rpm"),
                mock.call(
                    os.path.join(gpl_file),
                    os.path.join(self.isos.temp_dir, "trees", "x86_64", "GPL"),
                ),
            ],
        )


class TestCreaterepo(PungiTestCase):
    def setUp(self):
        super(TestCreaterepo, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        self.compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(self.compose_path)
        self.isos.linker = mock.Mock()
        # TODO mock treeinfo and use mappings for other data
        self.isos.link_to_temp()
        self.maxDiff = None
        self.comps = get_comps_mapping(self.compose_path)

    def mock_cr(self, path, groupfile, update):
        self.assertTrue(update)
        touch(os.path.join(path, "repodata", "repomd.xml"))
        return ("/".join(path.split("/")[-2:]), groupfile)

    def mock_mr(self, path, pid, compress_type):
        self.assertEqual(compress_type, "gz")
        return ("/".join(path.split("/")[-3:-1]), pid)

    @mock.patch("pungi.wrappers.createrepo.CreaterepoWrapper")
    @mock.patch("pungi_utils.unified_isos.run")
    def test_createrepo(self, run, cr):
        cr.return_value.get_createrepo_cmd.side_effect = self.mock_cr
        self.isos.createrepo()

        six.assertCountEqual(
            self,
            run.call_args_list,
            [
                mock.call(("src/Client", None), show_cmd=True),
                mock.call(("src/Server", None), show_cmd=True),
                mock.call(("i386/Client", self.comps["i386"]["Client"]), show_cmd=True),
                mock.call(
                    ("s390x/Server", self.comps["s390x"]["Server"]), show_cmd=True
                ),
                mock.call(
                    ("x86_64/Client", self.comps["x86_64"]["Client"]), show_cmd=True
                ),
                mock.call(
                    ("x86_64/Server", self.comps["x86_64"]["Server"]), show_cmd=True
                ),
                mock.call(("debug-i386/Client", None), show_cmd=True),
                mock.call(("debug-s390x/Server", None), show_cmd=True),
                mock.call(("debug-x86_64/Client", None), show_cmd=True),
                mock.call(("debug-x86_64/Server", None), show_cmd=True),
            ],
        )

        checksums = {}

        # treeinfo checksums
        for arch in self.isos.treeinfo.keys():
            parser = ConfigParser()
            parser.optionxform = str
            parser.read(os.path.join(self.isos.temp_dir, "trees", arch, ".treeinfo"))
            checksums[arch] = [k for k, v in parser.items("checksums")]

        self.assertEqual(
            checksums,
            {
                "i386": ["Client/repodata/repomd.xml"],
                "debug-i386": ["Client/repodata/repomd.xml"],
                "s390x": ["Server/repodata/repomd.xml"],
                "debug-s390x": ["Server/repodata/repomd.xml"],
                "src": ["Client/repodata/repomd.xml", "Server/repodata/repomd.xml"],
                "x86_64": ["Client/repodata/repomd.xml", "Server/repodata/repomd.xml"],
                "debug-x86_64": [
                    "Client/repodata/repomd.xml",
                    "Server/repodata/repomd.xml",
                ],
            },
        )

    @mock.patch("pungi.wrappers.createrepo.CreaterepoWrapper")
    @mock.patch("pungi_utils.unified_isos.run")
    def test_createrepo_with_productid(self, run, cr):
        for x in self.isos.productid.values():
            for f in x.values():
                touch(f)
        cr.return_value.get_createrepo_cmd.side_effect = self.mock_cr
        cr.return_value.get_modifyrepo_cmd.side_effect = self.mock_mr
        self.isos.createrepo()

        six.assertCountEqual(
            self,
            run.call_args_list,
            [
                mock.call(("src/Client", None), show_cmd=True),
                mock.call(("src/Server", None), show_cmd=True),
                mock.call(("i386/Client", self.comps["i386"]["Client"]), show_cmd=True),
                mock.call(("debug-i386/Client", None), show_cmd=True),
                mock.call(
                    ("s390x/Server", self.comps["s390x"]["Server"]), show_cmd=True
                ),
                mock.call(("debug-s390x/Server", None), show_cmd=True),
                mock.call(
                    ("x86_64/Client", self.comps["x86_64"]["Client"]), show_cmd=True
                ),
                mock.call(("debug-x86_64/Client", None), show_cmd=True),
                mock.call(
                    ("x86_64/Server", self.comps["x86_64"]["Server"]), show_cmd=True
                ),
                mock.call(("debug-x86_64/Server", None), show_cmd=True),
                mock.call(
                    (
                        "x86_64/Server",
                        os.path.join(
                            self.isos.temp_dir, "trees/x86_64/Server/repodata/productid"
                        ),
                    )
                ),
                mock.call(
                    (
                        "x86_64/Client",
                        os.path.join(
                            self.isos.temp_dir, "trees/x86_64/Client/repodata/productid"
                        ),
                    )
                ),
                mock.call(
                    (
                        "s390x/Server",
                        os.path.join(
                            self.isos.temp_dir, "trees/s390x/Server/repodata/productid"
                        ),
                    )
                ),
                mock.call(
                    (
                        "i386/Client",
                        os.path.join(
                            self.isos.temp_dir, "trees/i386/Client/repodata/productid"
                        ),
                    )
                ),
            ],
        )

        checksums = {}

        # treeinfo checksums
        for arch in self.isos.treeinfo.keys():
            parser = ConfigParser()
            parser.optionxform = str
            parser.read(os.path.join(self.isos.temp_dir, "trees", arch, ".treeinfo"))
            checksums[arch] = [k for k, v in parser.items("checksums")]

        self.assertEqual(
            checksums,
            {
                "i386": ["Client/repodata/repomd.xml"],
                "debug-i386": ["Client/repodata/repomd.xml"],
                "s390x": ["Server/repodata/repomd.xml"],
                "debug-s390x": ["Server/repodata/repomd.xml"],
                "src": ["Client/repodata/repomd.xml", "Server/repodata/repomd.xml"],
                "x86_64": ["Client/repodata/repomd.xml", "Server/repodata/repomd.xml"],
                "debug-x86_64": [
                    "Client/repodata/repomd.xml",
                    "Server/repodata/repomd.xml",
                ],
            },
        )


class TestDiscinfo(PungiTestCase):
    def setUp(self):
        super(TestDiscinfo, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        self.compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(self.compose_path)
        self.isos.linker = mock.Mock()
        # TODO mock treeinfo and use mappings for other data
        self.isos.link_to_temp()
        self.maxDiff = None

    @mock.patch("pungi_utils.unified_isos.create_discinfo")
    def test_discinfo(self, create_discinfo):
        self.isos.discinfo()
        six.assertCountEqual(
            self,
            create_discinfo.call_args_list,
            [
                mock.call(
                    os.path.join(self.isos.temp_dir, "trees", "i386", ".discinfo"),
                    "Dummy Product 1.0",
                    "i386",
                ),
                mock.call(
                    os.path.join(
                        self.isos.temp_dir, "trees", "debug-i386", ".discinfo"
                    ),
                    "Dummy Product 1.0",
                    "i386",
                ),
                mock.call(
                    os.path.join(self.isos.temp_dir, "trees", "s390x", ".discinfo"),
                    "Dummy Product 1.0",
                    "s390x",
                ),
                mock.call(
                    os.path.join(
                        self.isos.temp_dir, "trees", "debug-s390x", ".discinfo"
                    ),
                    "Dummy Product 1.0",
                    "s390x",
                ),
                mock.call(
                    os.path.join(self.isos.temp_dir, "trees", "src", ".discinfo"),
                    "Dummy Product 1.0",
                    "src",
                ),
                mock.call(
                    os.path.join(self.isos.temp_dir, "trees", "x86_64", ".discinfo"),
                    "Dummy Product 1.0",
                    "x86_64",
                ),
                mock.call(
                    os.path.join(
                        self.isos.temp_dir, "trees", "debug-x86_64", ".discinfo"
                    ),
                    "Dummy Product 1.0",
                    "x86_64",
                ),
            ],
        )


CHECKSUMS = {
    "MD5": "cbc3a5767b22babfe3578a2b82d83fcb",
    "SHA1": "afaf8621bfbc22781edfc81b774a2b2f66fdc8b0",
    "SHA256": "84c1c8611b287209e1e76d657e7e69e6192ad72dd2531e0fb7a43b95070fabb1",
}


class TestCreateiso(PungiTestCase):
    def setUp(self):
        super(TestCreateiso, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        self.compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(self.compose_path)
        self.isos.linker = mock.Mock()
        # TODO mock treeinfo and use mappings for other data
        self.isos.link_to_temp()
        # Reset linker to only mock calls from createiso method.
        self.isos.linker = mock.Mock()
        self.maxDiff = None
        self.mkisofs_cmd = None

        self.binary_fn = "DP-1.0-20161013.t.4-x86_64-dvd.iso"
        self.binary = os.path.join(self.isos.temp_dir, "iso", "x86_64", self.binary_fn)
        self.source_fn = "DP-1.0-20161013.t.4-source-dvd.iso"
        self.source = os.path.join(self.isos.temp_dir, "iso", "source", self.source_fn)
        self.debug_fn = "DP-1.0-20161013.t.4-x86_64-debuginfo-dvd.iso"
        self.debug = os.path.join(
            self.isos.temp_dir, "iso", "x86_64-debuginfo", self.debug_fn
        )

    def mock_gmc(self, path, *args, **kwargs):
        touch(path, "ISO FILE\n")
        self.mkisofs_cmd = self.mkisofs_cmd or mock.Mock(name="mkisofs cmd")
        return self.mkisofs_cmd

    def _iso(self, variant, arch, name):
        return os.path.join(self.compose_path, variant, arch, "iso", name)

    def assertResults(self, iso, run, arches):
        self.assertEqual(
            run.mock_calls,
            [
                mock.call(self.mkisofs_cmd, universal_newlines=True),
                mock.call(iso.get_implantisomd5_cmd.return_value),
                mock.call(iso.get_manifest_cmd.return_value),
            ]
            * len(arches),
        )

        images = self.isos.compose.images

        for v in ("Client", "Server"):
            for a in arches:
                for image in images[v]["x86_64"]:
                    arch = iso_arch = "source" if image.arch == "src" else image.arch
                    if a.startswith("debug-"):
                        iso_arch += "-debuginfo"
                        a = a.split("-", 1)[1]
                    path = "{0}/{1}/iso/DP-1.0-20161013.t.4-{1}-dvd.iso".format(v, arch)
                    if image.unified and image.arch == a and image.path == path:
                        break
                else:
                    self.fail("Image for %s.%s missing" % (v, a))

        expected = [
            mock.call(self.binary, self._iso("Client", "x86_64", self.binary_fn)),
            mock.call(
                self.binary + ".manifest",
                self._iso("Client", "x86_64", self.binary_fn + ".manifest"),
            ),
            mock.call(self.binary, self._iso("Server", "x86_64", self.binary_fn)),
            mock.call(
                self.binary + ".manifest",
                self._iso("Server", "x86_64", self.binary_fn + ".manifest"),
            ),
            mock.call(self.source, self._iso("Client", "source", self.source_fn)),
            mock.call(
                self.source + ".manifest",
                self._iso("Client", "source", self.source_fn + ".manifest"),
            ),
            mock.call(self.source, self._iso("Server", "source", self.source_fn)),
            mock.call(
                self.source + ".manifest",
                self._iso("Server", "source", self.source_fn + ".manifest"),
            ),
        ]
        if "debug-x86_64" in arches:
            expected.extend(
                [
                    mock.call(
                        self.debug, self._iso("Client", "x86_64/debug", self.debug_fn)
                    ),
                    mock.call(
                        self.debug + ".manifest",
                        self._iso(
                            "Client", "x86_64/debug", self.debug_fn + ".manifest"
                        ),
                    ),
                    mock.call(
                        self.debug, self._iso("Server", "x86_64/debug", self.debug_fn)
                    ),
                    mock.call(
                        self.debug + ".manifest",
                        self._iso(
                            "Server", "x86_64/debug", self.debug_fn + ".manifest"
                        ),
                    ),
                ]
            )
        six.assertCountEqual(self, self.isos.linker.link.call_args_list, expected)

    @mock.patch("pungi_utils.unified_isos.iso")
    @mock.patch("pungi_utils.unified_isos.run")
    def test_createiso(self, run, iso):
        iso.get_mkisofs_cmd.side_effect = self.mock_gmc
        iso.get_implanted_md5.return_value = "beefcafebabedeadbeefcafebabedead"
        iso.get_volume_id.return_value = "VOLID"

        self.isos.treeinfo = {
            "x86_64": self.isos.treeinfo["x86_64"],
            "src": self.isos.treeinfo["src"],
        }

        self.isos.createiso()

        self.assertResults(iso, run, ["src", "x86_64"])

    @mock.patch("pungi_utils.unified_isos.iso")
    @mock.patch("pungi_utils.unified_isos.run")
    def test_createiso_debuginfo(self, run, iso):
        iso.get_mkisofs_cmd.side_effect = self.mock_gmc
        iso.get_implanted_md5.return_value = "beefcafebabedeadbeefcafebabedead"
        iso.get_volume_id.return_value = "VOLID"

        self.isos.treeinfo = {
            "x86_64": self.isos.treeinfo["x86_64"],
            "debug-x86_64": self.isos.treeinfo["x86_64"],
            "src": self.isos.treeinfo["src"],
        }

        self.isos.createiso()

        self.assertResults(iso, run, ["src", "x86_64", "debug-x86_64"])


class MockImage(mock.Mock):
    def __eq__(self, another):
        return self.path == another.path


class TestUpdateChecksums(PungiTestCase):
    def setUp(self):
        super(TestUpdateChecksums, self).setUp()
        shutil.copytree(
            os.path.join(FIXTURE_DIR, COMPOSE_ID), os.path.join(self.topdir, COMPOSE_ID)
        )
        self.compose_path = os.path.join(self.topdir, COMPOSE_ID, "compose")
        self.isos = unified_isos.UnifiedISO(self.compose_path)
        self.maxDiff = None

    def _isodir(self, variant, arch):
        return os.path.join(self.compose_path, variant, arch, "iso")

    def _call(self, variant, arch, source=False, basename="", one_file=False):
        archdir = arch if not source else "source"
        isodir = self._isodir(variant, archdir)
        filename = "DP-1.0-20161013.t.4-%s-%s-dvd1.iso" % (variant, archdir)
        return mock.call(
            variant,
            arch,
            isodir,
            [MockImage(path=os.path.join(variant, archdir, "iso", filename))],
            ["md5", "sha1", "sha256"],
            basename,
            one_file,
        )

    @mock.patch("pungi_utils.unified_isos.make_checksums")
    def test_update_checksums(self, mmc):
        self.isos.update_checksums()
        six.assertCountEqual(
            self,
            mmc.call_args_list,
            [
                mock.call(
                    self.compose_path,
                    self.isos.compose.images,
                    unified_isos.DEFAULT_CHECKSUMS,
                    False,
                    self.isos._get_base_filename,
                )
            ],
        )

    @mock.patch("pungi_utils.unified_isos.make_checksums")
    def test_update_checksums_one_file(self, mmc):
        self.isos.conf["media_checksum_one_file"] = True
        self.isos.update_checksums()
        six.assertCountEqual(
            self,
            mmc.call_args_list,
            [
                mock.call(
                    self.compose_path,
                    self.isos.compose.images,
                    unified_isos.DEFAULT_CHECKSUMS,
                    True,
                    self.isos._get_base_filename,
                )
            ],
        )

    def test_get_base_filename(self):
        self.isos.conf["media_checksum_base_filename"] = "{variant}-{arch}"
        self.assertEqual(
            self.isos._get_base_filename("Client", "x86_64"), "Client-x86_64-"
        )
