import os

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from parameterized import parameterized
from pungi import module_util
from pungi.module_util import Modulemd

from tests import helpers


@unittest.skipUnless(Modulemd, "Skipped test, no module support.")
class TestModuleUtil(helpers.PungiTestCase):
    def _get_stream(self, mod_name, stream_name):
        stream = Modulemd.ModuleStream.new(
            Modulemd.ModuleStreamVersionEnum.TWO, mod_name, stream_name
        )
        stream.props.version = 42
        stream.props.context = "deadbeef"
        stream.props.arch = "x86_64"

        return stream

    def _write_obsoletes(self, defs):
        for mod_name, stream, obsoleted_by in defs:
            mod_index = Modulemd.ModuleIndex.new()
            mmdobs = Modulemd.Obsoletes.new(1, 10993435, mod_name, stream, "testmsg")
            mmdobs.set_obsoleted_by(obsoleted_by[0], obsoleted_by[1])
            mod_index.add_obsoletes(mmdobs)
            filename = "%s:%s.yaml" % (mod_name, stream)
            with open(os.path.join(self.topdir, filename), "w") as f:
                f.write(mod_index.dump_to_string())

    def _write_defaults(self, defs):
        for mod_name, streams in defs.items():
            for stream in streams:
                mod_index = Modulemd.ModuleIndex.new()
                mmddef = Modulemd.DefaultsV1.new(mod_name)
                mmddef.set_default_stream(stream)
                mod_index.add_defaults(mmddef)
                filename = "%s-%s.yaml" % (mod_name, stream)
                with open(os.path.join(self.topdir, filename), "w") as f:
                    f.write(mod_index.dump_to_string())

    @parameterized.expand(
        [
            (
                "MULTIPLE",
                [
                    ("httpd", "1.22.1", ("httpd-new", "3.0")),
                    ("httpd", "10.4", ("httpd", "11.1.22")),
                ],
            ),
            (
                "NORMAL",
                [
                    ("gdb", "2.8", ("gdb", "3.0")),
                    ("nginx", "12.7", ("nginx-nightly", "13.3")),
                ],
            ),
        ]
    )
    def test_merged_module_obsoletes_idx(self, test_name, data):
        self._write_obsoletes(data)

        mod_index = module_util.get_module_obsoletes_idx(self.topdir, [])

        if test_name == "MULTIPLE":
            # Multiple obsoletes are allowed
            mod = mod_index.get_module("httpd")
            self.assertEqual(len(mod.get_obsoletes()), 2)
        else:
            mod = mod_index.get_module("gdb")
            self.assertEqual(len(mod.get_obsoletes()), 1)
            mod_obsolete = mod.get_obsoletes()
            self.assertIsNotNone(mod_obsolete)
            self.assertEqual(mod_obsolete[0].get_obsoleted_by_module_stream(), "3.0")

    def test_collect_module_defaults_with_index(self):
        stream = self._get_stream("httpd", "1")
        mod_index = Modulemd.ModuleIndex()
        mod_index.add_module_stream(stream)

        defaults_data = {"httpd": ["1.44.2"], "python": ["3.6", "3.5"]}
        self._write_defaults(defaults_data)

        mod_index = module_util.collect_module_defaults(
            self.topdir, defaults_data.keys(), mod_index
        )

        for module_name in defaults_data.keys():
            mod = mod_index.get_module(module_name)
            self.assertIsNotNone(mod)

            mod_defaults = mod.get_defaults()
            self.assertIsNotNone(mod_defaults)

            if module_name == "httpd":
                self.assertEqual(mod_defaults.get_default_stream(), "1.44.2")
            else:
                # Can't have multiple defaults for one stream
                self.assertEqual(mod_defaults.get_default_stream(), None)

    def test_handles_non_defaults_file_without_validation(self):
        self._write_defaults({"httpd": ["1"], "python": ["3.6"]})
        helpers.touch(
            os.path.join(self.topdir, "boom.yaml"),
            "\n".join(
                [
                    "document: modulemd",
                    "version: 2",
                    "data:",
                    "  summary: dummy module",
                    "  description: dummy module",
                    "  license:",
                    "    module: [GPL]",
                    "    content: [GPL]",
                ]
            ),
        )

        idx = module_util.collect_module_defaults(self.topdir)

        self.assertEqual(len(idx.get_module_names()), 0)

    @parameterized.expand([(False, ["httpd"]), (False, ["python"])])
    def test_collect_module_obsoletes(self, no_index, mod_list):
        if not no_index:
            stream = self._get_stream(mod_list[0], "1.22.1")
            mod_index = Modulemd.ModuleIndex()
            mod_index.add_module_stream(stream)
        else:
            mod_index = None

        data = [
            ("httpd", "1.22.1", ("httpd-new", "3.0")),
            ("httpd", "10.4", ("httpd", "11.1.22")),
        ]
        self._write_obsoletes(data)

        mod_index = module_util.collect_module_obsoletes(
            self.topdir, mod_list, mod_index
        )

        # Obsoletes should not me merged without corresponding module
        # if module list is present
        if "python" in mod_list:
            mod = mod_index.get_module("httpd")
            self.assertIsNone(mod)
        else:
            mod = mod_index.get_module("httpd")

            # No modules
            if "httpd" not in mod_list:
                self.assertIsNone(mod.get_obsoletes())
            else:
                self.assertIsNotNone(mod)
                obsoletes_from_orig = mod.get_newest_active_obsoletes("1.22.1", None)

                self.assertEqual(
                    obsoletes_from_orig.get_obsoleted_by_module_name(), "httpd-new"
                )

    def test_collect_module_obsoletes_without_modlist(self):
        stream = self._get_stream("nginx", "1.22.1")
        mod_index = Modulemd.ModuleIndex()
        mod_index.add_module_stream(stream)

        data = [
            ("httpd", "1.22.1", ("httpd-new", "3.0")),
            ("nginx", "10.4", ("nginx", "11.1.22")),
            ("nginx", "11.1.22", ("nginx", "66")),
        ]
        self._write_obsoletes(data)

        mod_index = module_util.collect_module_obsoletes(self.topdir, [], mod_index)

        # All obsoletes are merged into main Index when filter is empty
        self.assertEqual(len(mod_index.get_module_names()), 2)

        mod = mod_index.get_module("httpd")
        self.assertIsNotNone(mod)

        self.assertEqual(len(mod.get_obsoletes()), 1)

        mod = mod_index.get_module("nginx")
        self.assertIsNotNone(mod)

        self.assertEqual(len(mod.get_obsoletes()), 2)
