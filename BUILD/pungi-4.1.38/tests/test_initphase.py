#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    import unittest2 as unittest
except ImportError:
    import unittest
import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi import Modulemd
from pungi.phases import init
from tests.helpers import DummyCompose, PungiTestCase, touch, mk_boom


def fake_run_in_threads(func, params, threads=None):
    for num, param in enumerate(params):
        func(None, param, num)


@mock.patch("pungi.phases.init.run_in_threads", new=fake_run_in_threads)
@mock.patch("pungi.phases.init.validate_comps")
@mock.patch("pungi.phases.init.validate_module_defaults")
@mock.patch("pungi.phases.init.write_module_defaults")
@mock.patch("pungi.phases.init.write_global_comps")
@mock.patch("pungi.phases.init.write_arch_comps")
@mock.patch("pungi.phases.init.create_comps_repo")
@mock.patch("pungi.phases.init.write_variant_comps")
@mock.patch("pungi.phases.init.write_prepopulate_file")
class TestInitPhase(PungiTestCase):

    def test_run(
        self,
        write_prepopulate,
        write_variant,
        create_comps,
        write_arch,
        write_global,
        write_defaults,
        validate_defaults,
        validate_comps,
    ):
        compose = DummyCompose(self.topdir, {})
        compose.has_comps = True
        compose.has_module_defaults = False
        compose.setup_optional()
        phase = init.InitPhase(compose)
        phase.run()

        self.assertEqual(write_global.mock_calls, [mock.call(compose)])
        self.assertEqual(write_prepopulate.mock_calls, [mock.call(compose)])
        self.assertItemsEqual(write_arch.mock_calls,
                              [mock.call(compose, 'x86_64'), mock.call(compose, 'amd64')])
        self.assertItemsEqual(create_comps.mock_calls,
                              [mock.call(compose, 'x86_64', None), mock.call(compose, 'amd64', None),
                               mock.call(compose, 'x86_64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Client']),
                               mock.call(compose, 'x86_64', compose.variants['Everything']),
                               mock.call(compose, 'amd64', compose.variants['Everything']),
                               mock.call(compose, 'x86_64', compose.all_variants['Server-optional'])])
        self.assertItemsEqual(write_variant.mock_calls,
                              [mock.call(compose, 'x86_64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Client']),
                               mock.call(compose, 'x86_64', compose.variants['Everything']),
                               mock.call(compose, 'amd64', compose.variants['Everything']),
                               mock.call(compose, 'x86_64', compose.all_variants['Server-optional'])])
        self.assertItemsEqual(write_defaults, [])
        self.assertItemsEqual(validate_defaults, [])

    def test_run_with_preserve(
        self,
        write_prepopulate,
        write_variant,
        create_comps,
        write_arch,
        write_global,
        write_defaults,
        validate_defaults,
        validate_comps,
    ):
        compose = DummyCompose(self.topdir, {})
        compose.has_comps = True
        compose.has_module_defaults = False
        compose.variants['Everything'].groups = []
        compose.variants['Everything'].modules = []
        phase = init.InitPhase(compose)
        phase.run()

        self.assertEqual(write_global.mock_calls, [mock.call(compose)])
        self.assertEqual(
            validate_comps.call_args_list, [mock.call(write_global.return_value)]
        )
        self.assertEqual(write_prepopulate.mock_calls, [mock.call(compose)])
        self.assertItemsEqual(write_arch.mock_calls,
                              [mock.call(compose, 'x86_64'), mock.call(compose, 'amd64')])
        self.assertItemsEqual(create_comps.mock_calls,
                              [mock.call(compose, 'x86_64', None), mock.call(compose, 'amd64', None),
                               mock.call(compose, 'x86_64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Client']),
                               mock.call(compose, 'x86_64', compose.variants['Everything']),
                               mock.call(compose, 'amd64', compose.variants['Everything'])])
        self.assertItemsEqual(write_variant.mock_calls,
                              [mock.call(compose, 'x86_64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Server']),
                               mock.call(compose, 'amd64', compose.variants['Client']),
                               mock.call(compose, 'x86_64', compose.variants['Everything']),
                               mock.call(compose, 'amd64', compose.variants['Everything'])])
        self.assertItemsEqual(write_defaults, [])
        self.assertItemsEqual(validate_defaults, [])

    def test_run_without_comps(
        self,
        write_prepopulate,
        write_variant,
        create_comps,
        write_arch,
        write_global,
        write_defaults,
        validate_defaults,
        validate_comps,
    ):
        compose = DummyCompose(self.topdir, {})
        compose.has_comps = False
        compose.has_module_defaults = False
        phase = init.InitPhase(compose)
        phase.run()

        self.assertItemsEqual(write_global.mock_calls, [])
        self.assertEqual(validate_comps.call_args_list, [])
        self.assertItemsEqual(write_prepopulate.mock_calls, [mock.call(compose)])
        self.assertItemsEqual(write_arch.mock_calls, [])
        self.assertItemsEqual(create_comps.mock_calls, [])
        self.assertItemsEqual(write_variant.mock_calls, [])
        self.assertItemsEqual(write_defaults, [])
        self.assertItemsEqual(validate_defaults, [])

    def test_with_module_defaults(
        self,
        write_prepopulate,
        write_variant,
        create_comps,
        write_arch,
        write_global,
        write_defaults,
        validate_defaults,
        validate_comps,
    ):
        compose = DummyCompose(self.topdir, {})
        compose.has_comps = False
        compose.has_module_defaults = True
        phase = init.InitPhase(compose)
        phase.run()

        self.assertItemsEqual(write_global.mock_calls, [])
        self.assertEqual(validate_comps.call_args_list, [])
        self.assertItemsEqual(write_prepopulate.mock_calls, [mock.call(compose)])
        self.assertItemsEqual(write_arch.mock_calls, [])
        self.assertItemsEqual(create_comps.mock_calls, [])
        self.assertItemsEqual(write_variant.mock_calls, [])
        self.assertItemsEqual(write_defaults.call_args_list, [mock.call(compose)])
        self.assertItemsEqual(
            validate_defaults.call_args_list,
            [mock.call(compose.paths.work.module_defaults_dir())],
        )


class TestWriteArchComps(PungiTestCase):

    @mock.patch('pungi.phases.init.run')
    def test_run(self, run):
        compose = DummyCompose(self.topdir, {})

        init.write_arch_comps(compose, 'x86_64')

        self.assertEqual(run.mock_calls,
                         [mock.call(['comps_filter', '--arch=x86_64', '--no-cleanup',
                                     '--output=%s/work/x86_64/comps/comps-x86_64.xml' % self.topdir,
                                     self.topdir + '/work/global/comps/comps-global.xml'])])

    @mock.patch('pungi.phases.init.run')
    def test_run_in_debug(self, run):
        compose = DummyCompose(self.topdir, {})
        compose.DEBUG = True
        touch(self.topdir + '/work/x86_64/comps/comps-x86_64.xml')

        init.write_arch_comps(compose, 'x86_64')

        self.assertEqual(run.mock_calls, [])


class TestCreateCompsRepo(PungiTestCase):

    @mock.patch('pungi.phases.init.run')
    def test_run(self, run):
        compose = DummyCompose(self.topdir, {
            'createrepo_checksum': 'sha256',
        })

        init.create_comps_repo(compose, 'x86_64', None)

        self.assertEqual(run.mock_calls,
                         [mock.call(['createrepo_c', self.topdir + '/work/x86_64/comps_repo',
                                     '--outputdir=%s/work/x86_64/comps_repo' % self.topdir,
                                     '--groupfile=%s/work/x86_64/comps/comps-x86_64.xml' % self.topdir,
                                     '--update', '--no-database', '--checksum=sha256',
                                     '--unique-md-filenames'],
                                    logfile=self.topdir + '/logs/x86_64/comps_repo.x86_64.log',
                                    show_cmd=True)])

    @mock.patch('pungi.phases.init.run')
    def test_run_with_variant(self, run):
        compose = DummyCompose(self.topdir, {
            'createrepo_checksum': 'sha256',
        })

        init.create_comps_repo(compose, 'x86_64', compose.variants['Server'])

        self.assertEqual(run.mock_calls,
                         [mock.call(['createrepo_c', self.topdir + '/work/x86_64/comps_repo_Server',
                                     '--outputdir=%s/work/x86_64/comps_repo_Server' % self.topdir,
                                     '--groupfile=%s/work/x86_64/comps/comps-Server.x86_64.xml' % self.topdir,
                                     '--update', '--no-database', '--checksum=sha256',
                                     '--unique-md-filenames'],
                                    logfile=self.topdir + '/logs/x86_64/comps_repo-Server.x86_64.log',
                                    show_cmd=True)])

    @mock.patch('pungi.phases.init.run')
    def test_run_in_debug(self, run):
        compose = DummyCompose(self.topdir, {
            'createrepo_checksum': 'sha256',
        })
        compose.DEBUG = True
        os.makedirs(self.topdir + '/work/x86_64/comps_repo/repodata')

        init.create_comps_repo(compose, 'x86_64', None)

        self.assertEqual(run.mock_calls, [])


class TestWriteGlobalComps(PungiTestCase):

    @mock.patch('shutil.copy2')
    @mock.patch('pungi.phases.init.get_file_from_scm')
    def test_run_in_debug(self, get_file, copy2):
        compose = DummyCompose(self.topdir, {'comps_file': 'some-file.xml'})
        compose.DEBUG = True
        touch(self.topdir + '/work/global/comps/comps-global.xml')

        init.write_global_comps(compose)

        self.assertEqual(get_file.mock_calls, [])
        self.assertEqual(copy2.mock_calls, [])

    @mock.patch('pungi.phases.init.get_file_from_scm')
    def test_run_local_file(self, get_file):
        compose = DummyCompose(self.topdir, {'comps_file': 'some-file.xml'})

        def gen_file(src, dest, logger=None):
            self.assertEqual(src, '/home/releng/config/some-file.xml')
            touch(os.path.join(dest, 'some-file.xml'))

        get_file.side_effect = gen_file

        init.write_global_comps(compose)

        self.assertTrue(os.path.isfile(self.topdir + '/work/global/comps/comps-global.xml'))


class TestWriteVariantComps(PungiTestCase):

    @mock.patch('pungi.phases.init.run')
    @mock.patch('pungi.phases.init.CompsWrapper')
    def test_run(self, CompsWrapper, run):
        compose = DummyCompose(self.topdir, {})
        variant = compose.variants['Server']
        comps = CompsWrapper.return_value
        comps.filter_groups.return_value = []

        init.write_variant_comps(compose, 'x86_64', variant)

        self.assertEqual(run.mock_calls,
                         [mock.call(['comps_filter', '--arch=x86_64', '--keep-empty-group=conflicts',
                                     '--keep-empty-group=conflicts-server',
                                     '--variant=Server',
                                     '--output=%s/work/x86_64/comps/comps-Server.x86_64.xml' % self.topdir,
                                     self.topdir + '/work/global/comps/comps-global.xml'])])
        self.assertEqual(CompsWrapper.call_args_list,
                         [mock.call(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')])
        self.assertEqual(comps.filter_groups.call_args_list, [mock.call(variant.groups)])
        self.assertEqual(comps.filter_environments.mock_calls,
                         [mock.call(variant.environments)])
        self.assertEqual(comps.write_comps.mock_calls, [mock.call()])

    @mock.patch("pungi.phases.init.get_lookaside_groups")
    @mock.patch("pungi.phases.init.run")
    @mock.patch("pungi.phases.init.CompsWrapper")
    def test_run_with_lookaside_groups(self, CompsWrapper, run, glg):
        compose = DummyCompose(self.topdir, {})
        variant = compose.variants["Server"]
        comps = CompsWrapper.return_value
        comps.filter_groups.return_value = []
        glg.return_value = ["foo", "bar"]

        init.write_variant_comps(compose, "x86_64", variant)

        self.assertEqual(
            run.mock_calls,
            [
                mock.call(
                    [
                        "comps_filter",
                        "--arch=x86_64",
                        "--keep-empty-group=conflicts",
                        "--keep-empty-group=conflicts-server",
                        "--variant=Server",
                        "--output=%s/work/x86_64/comps/comps-Server.x86_64.xml" % self.topdir,
                        self.topdir + "/work/global/comps/comps-global.xml",
                        "--lookaside-group=foo",
                        "--lookaside-group=bar",
                    ]
                ),
            ],
        )
        self.assertEqual(
            CompsWrapper.call_args_list,
            [mock.call(self.topdir + "/work/x86_64/comps/comps-Server.x86_64.xml")],
        )
        self.assertEqual(
            comps.filter_groups.call_args_list, [mock.call(variant.groups)]
        )
        self.assertEqual(
            comps.filter_environments.mock_calls, [mock.call(variant.environments)]
        )
        self.assertEqual(comps.write_comps.mock_calls, [mock.call()])

    @mock.patch('pungi.phases.init.run')
    @mock.patch('pungi.phases.init.CompsWrapper')
    def test_run_no_filter_without_groups(self, CompsWrapper, run):
        compose = DummyCompose(self.topdir, {})
        variant = compose.variants['Server']
        variant.groups = []
        comps = CompsWrapper.return_value
        comps.filter_groups.return_value = []

        init.write_variant_comps(compose, 'x86_64', variant)

        self.assertEqual(run.mock_calls,
                         [mock.call(['comps_filter', '--arch=x86_64', '--keep-empty-group=conflicts',
                                     '--keep-empty-group=conflicts-server',
                                     '--variant=Server',
                                     '--output=%s/work/x86_64/comps/comps-Server.x86_64.xml' % self.topdir,
                                     self.topdir + '/work/global/comps/comps-global.xml'])])
        self.assertEqual(CompsWrapper.call_args_list,
                         [mock.call(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')])
        self.assertEqual(comps.filter_groups.call_args_list, [])
        self.assertEqual(comps.filter_environments.mock_calls,
                         [mock.call(variant.environments)])
        self.assertEqual(comps.write_comps.mock_calls, [mock.call()])

    @mock.patch('pungi.phases.init.run')
    @mock.patch('pungi.phases.init.CompsWrapper')
    def test_run_filter_for_modular(self, CompsWrapper, run):
        compose = DummyCompose(self.topdir, {})
        variant = compose.variants['Server']
        variant.groups = []
        variant.modules = ['testmodule:2.0']
        comps = CompsWrapper.return_value
        comps.filter_groups.return_value = []

        init.write_variant_comps(compose, 'x86_64', variant)

        self.assertEqual(run.mock_calls,
                         [mock.call(['comps_filter', '--arch=x86_64', '--keep-empty-group=conflicts',
                                     '--keep-empty-group=conflicts-server',
                                     '--variant=Server',
                                     '--output=%s/work/x86_64/comps/comps-Server.x86_64.xml' % self.topdir,
                                     self.topdir + '/work/global/comps/comps-global.xml'])])
        self.assertEqual(CompsWrapper.call_args_list,
                         [mock.call(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')])
        self.assertEqual(comps.filter_groups.call_args_list, [mock.call([])])
        self.assertEqual(comps.filter_environments.mock_calls,
                         [mock.call(variant.environments)])
        self.assertEqual(comps.write_comps.mock_calls, [mock.call()])

    @mock.patch('pungi.phases.init.run')
    @mock.patch('pungi.phases.init.CompsWrapper')
    def test_run_report_unmatched(self, CompsWrapper, run):
        compose = DummyCompose(self.topdir, {})
        variant = compose.variants['Server']
        comps = CompsWrapper.return_value
        comps.filter_groups.return_value = ['foo', 'bar']

        init.write_variant_comps(compose, 'x86_64', variant)

        self.assertEqual(run.mock_calls,
                         [mock.call(['comps_filter', '--arch=x86_64', '--keep-empty-group=conflicts',
                                     '--keep-empty-group=conflicts-server',
                                     '--variant=Server',
                                     '--output=%s/work/x86_64/comps/comps-Server.x86_64.xml' % self.topdir,
                                     self.topdir + '/work/global/comps/comps-global.xml'])])
        self.assertEqual(CompsWrapper.call_args_list,
                         [mock.call(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')])
        self.assertEqual(comps.filter_groups.call_args_list, [mock.call(variant.groups)])
        self.assertEqual(comps.filter_environments.mock_calls,
                         [mock.call(variant.environments)])
        self.assertEqual(comps.write_comps.mock_calls, [mock.call()])
        self.assertEqual(
            compose.log_warning.call_args_list,
            [mock.call(init.UNMATCHED_GROUP_MSG % ('Server', 'x86_64', 'foo')),
             mock.call(init.UNMATCHED_GROUP_MSG % ('Server', 'x86_64', 'bar'))])

    @mock.patch('pungi.phases.init.run')
    @mock.patch('pungi.phases.init.CompsWrapper')
    def test_run_in_debug(self, CompsWrapper, run):
        compose = DummyCompose(self.topdir, {})
        compose.DEBUG = True
        variant = compose.variants['Server']
        touch(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')

        init.write_variant_comps(compose, 'x86_64', variant)

        self.assertEqual(run.mock_calls, [])
        self.assertEqual(CompsWrapper.call_args_list,
                         [mock.call(self.topdir + '/work/x86_64/comps/comps-Server.x86_64.xml')])
        comps = CompsWrapper.return_value
        self.assertEqual(comps.filter_groups.mock_calls, [mock.call(variant.groups)])
        self.assertEqual(comps.filter_environments.mock_calls,
                         [mock.call(variant.environments)])
        self.assertEqual(comps.write_comps.mock_calls, [])


class TestGetLookasideGroups(PungiTestCase):
    def test_toplevel_variant(self):
        compose = DummyCompose(self.topdir, {})
        self.assertItemsEqual(
            init.get_lookaside_groups(compose, compose.variants["Server"]), []
        )

    def test_classic_addon(self):
        compose = DummyCompose(self.topdir, {})
        compose.setup_addon()
        compose.variants["Server"].groups = [{"name": "foo"}]
        self.assertItemsEqual(
            init.get_lookaside_groups(compose, compose.all_variants["Server-HA"]),
            ["foo"],
        )

    def test_variant_as_lookaside(self):
        compose = DummyCompose(
            self.topdir, {"variant_as_lookaside": [("Server", "Client")]}
        )
        compose.variants["Client"].groups = [{"name": "foo"}]
        self.assertItemsEqual(
            init.get_lookaside_groups(compose, compose.variants["Server"]),
            ["foo"],
        )


@mock.patch("shutil.copytree")
@mock.patch("pungi.phases.init.get_dir_from_scm")
class TestWriteModuleDefaults(PungiTestCase):

    def test_clone_git(self, gdfs, ct):
        conf = {"scm": "git", "repo": "https://pagure.io/pungi.git", "dir": "."}
        compose = DummyCompose(self.topdir, {"module_defaults_dir": conf})

        init.write_module_defaults(compose)

        self.assertEqual(
            gdfs.call_args_list, [mock.call(conf, mock.ANY, logger=mock.ANY)]
        )
        self.assertEqual(
            ct.call_args_list,
            [
                mock.call(
                    gdfs.call_args_list[0][0][1],
                    os.path.join(self.topdir, "work/global/module_defaults"),
                )
            ],
        )

    def test_clone_file_scm(self, gdfs, ct):
        conf = {"scm": "file", "dir": "defaults"}
        compose = DummyCompose(self.topdir, {"module_defaults_dir": conf})
        compose.config_dir = "/home/releng/configs"

        init.write_module_defaults(compose)

        self.assertEqual(
            gdfs.call_args_list,
            [
                mock.call(
                    {"scm": "file", "dir": "/home/releng/configs/defaults"},
                    mock.ANY,
                    logger=mock.ANY,
                )
            ],
        )
        self.assertEqual(
            ct.call_args_list,
            [
                mock.call(
                    gdfs.call_args_list[0][0][1],
                    os.path.join(self.topdir, "work/global/module_defaults"),
                )
            ],
        )

    def test_clone_file_str(self, gdfs, ct):
        conf = "defaults"
        compose = DummyCompose(self.topdir, {"module_defaults_dir": conf})
        compose.config_dir = "/home/releng/configs"

        init.write_module_defaults(compose)

        self.assertEqual(
            gdfs.call_args_list,
            [mock.call("/home/releng/configs/defaults", mock.ANY, logger=mock.ANY)],
        )
        self.assertEqual(
            ct.call_args_list,
            [
                mock.call(
                    gdfs.call_args_list[0][0][1],
                    os.path.join(self.topdir, "work/global/module_defaults"),
                )
            ],
        )


@unittest.skipUnless(Modulemd, "Skipped test, no module support.")
class TestValidateModuleDefaults(PungiTestCase):

    def _write_defaults(self, defs):
        for mod_name, streams in defs.items():
            for stream in streams:
                mmddef = Modulemd.Defaults.new()
                mmddef.set_version(1)
                mmddef.set_module_name(mod_name)
                mmddef.set_default_stream(stream)
                mmddef.dump(
                    os.path.join(self.topdir, "%s-%s.yaml" % (mod_name, stream))
                )

    def test_valid_files(self):
        self._write_defaults({"httpd": ["1"], "python": ["3.6"]})

        init.validate_module_defaults(self.topdir)

    def test_duplicated_stream(self):
        self._write_defaults({"httpd": ["1"], "python": ["3.6", "3.5"]})

        with self.assertRaises(RuntimeError) as ctx:
            init.validate_module_defaults(self.topdir)

        self.assertIn(
            "Module python has multiple defaults: 3.5, 3.6", str(ctx.exception)
        )

    def test_reports_all(self):
        self._write_defaults({"httpd": ["1", "2"], "python": ["3.6", "3.5"]})

        with self.assertRaises(RuntimeError) as ctx:
            init.validate_module_defaults(self.topdir)

        self.assertIn("Module httpd has multiple defaults: 1, 2", str(ctx.exception))
        self.assertIn(
            "Module python has multiple defaults: 3.5, 3.6", str(ctx.exception)
        )

    def test_handles_non_defaults_file(self):
        self._write_defaults({"httpd": ["1"], "python": ["3.6"]})
        touch(
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

        init.validate_module_defaults(self.topdir)


@mock.patch("pungi.phases.init.CompsWrapper")
class TestValidateComps(unittest.TestCase):
    def test_ok(self, CompsWrapper):
        init.validate_comps("/path")

        self.assertEqual(
            CompsWrapper.mock_calls, [mock.call("/path"), mock.call().validate()]
        )

    def test_fail(self, CompsWrapper):
        CompsWrapper.return_value.validate.side_effect = mk_boom()

        with self.assertRaises(Exception):
            init.validate_comps("/path")

        self.assertEqual(
            CompsWrapper.mock_calls, [mock.call("/path"), mock.call().validate()]
        )


if __name__ == "__main__":
    unittest.main()
