# -*- coding: utf-8 -*-

import itertools
import json
from functools import wraps
import operator
import os
import shutil
import subprocess
import sys
from textwrap import dedent

import mock
import six
from six.moves import configparser

from parameterized import parameterized

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.helpers import BaseTestCase, PungiTestCase, touch, FIXTURE_DIR
from pungi_utils import orchestrator as o


class TestConfigSubstitute(PungiTestCase):
    def setUp(self):
        super(TestConfigSubstitute, self).setUp()
        self.fp = os.path.join(self.topdir, "config.conf")

    @parameterized.expand(
        [
            ("hello = 'world'", "hello = 'world'"),
            ("hello = '{{foo}}'", "hello = 'bar'"),
            ("hello = '{{  foo}}'", "hello = 'bar'"),
            ("hello = '{{foo  }}'", "hello = 'bar'"),
        ]
    )
    def test_substitutions(self, initial, expected):
        touch(self.fp, initial)
        o.fill_in_config_file(self.fp, {"foo": "bar"})
        with open(self.fp) as f:
            self.assertEqual(expected, f.read())

    def test_missing_key(self):
        touch(self.fp, "hello = '{{unknown}}'")
        with self.assertRaises(RuntimeError) as ctx:
            o.fill_in_config_file(self.fp, {})
        self.assertEqual(
            "Unknown placeholder 'unknown' in config.conf", str(ctx.exception)
        )


class TestSafeGetList(BaseTestCase):
    @parameterized.expand(
        [
            ("", []),
            ("foo", ["foo"]),
            ("foo,bar", ["foo", "bar"]),
            ("foo  bar", ["foo", "bar"]),
        ]
    )
    def test_success(self, value, expected):
        cf = configparser.RawConfigParser()
        cf.add_section("general")
        cf.set("general", "key", value)
        self.assertEqual(o._safe_get_list(cf, "general", "key"), expected)

    def test_default(self):
        cf = configparser.RawConfigParser()
        cf.add_section("general")
        self.assertEqual(o._safe_get_list(cf, "general", "missing", "hello"), "hello")


class TestComposePart(PungiTestCase):
    def test_from_minimal_config(self):
        cf = configparser.RawConfigParser()
        cf.add_section("test")
        cf.set("test", "config", "my.conf")

        part = o.ComposePart.from_config(cf, "test", "/tmp/config")
        deps = "set()" if six.PY3 else "set([])"
        self.assertEqual(str(part), "test")
        self.assertEqual(
            repr(part),
            "ComposePart('test', '/tmp/config/my.conf', 'READY', "
            "just_phase=[], skip_phase=[], dependencies=%s)" % deps,
        )
        self.assertFalse(part.failable)

    def test_from_full_config(self):
        cf = configparser.RawConfigParser()
        cf.add_section("test")
        cf.set("test", "config", "my.conf")
        cf.set("test", "depends_on", "base")
        cf.set("test", "skip_phase", "skip")
        cf.set("test", "just_phase", "just")
        cf.set("test", "failable", "yes")

        part = o.ComposePart.from_config(cf, "test", "/tmp/config")
        deps = "{'base'}" if six.PY3 else "set(['base'])"
        self.assertEqual(
            repr(part),
            "ComposePart('test', '/tmp/config/my.conf', 'WAITING', "
            "just_phase=['just'], skip_phase=['skip'], dependencies=%s)" % deps,
        )
        self.assertTrue(part.failable)

    def test_get_cmd(self):
        conf = o.Config(
            "/tgt/", "production", "RC-1.0", "/old", "/cfg", 1234, ["--quiet"]
        )
        part = o.ComposePart(
            "test", "/tmp/my.conf", just_phase=["just"], skip_phase=["skip"]
        )
        part.path = "/compose"

        self.assertEqual(
            part.get_cmd(conf),
            [
                "pungi-koji",
                "--config",
                "/tmp/my.conf",
                "--compose-dir",
                "/compose",
                "--production",
                "--label",
                "RC-1.0",
                "--just-phase",
                "just",
                "--skip-phase",
                "skip",
                "--old-compose",
                "/old/parts",
                "--koji-event",
                "1234",
                "--quiet",
                "--no-latest-link",
            ],
        )

    def test_refresh_status(self):
        part = o.ComposePart("test", "/tmp/my.conf")
        part.path = os.path.join(self.topdir)
        touch(os.path.join(self.topdir, "STATUS"), "FINISHED")
        part.refresh_status()
        self.assertEqual(part.status, "FINISHED")

    def test_refresh_status_missing_file(self):
        part = o.ComposePart("test", "/tmp/my.conf")
        part.path = os.path.join(self.topdir)
        part.refresh_status()
        self.assertEqual(part.status, "DOOMED")

    @parameterized.expand(["FINISHED", "FINISHED_INCOMPLETE"])
    def test_is_finished(self, status):
        part = o.ComposePart("test", "/tmp/my.conf")
        part.status = status
        self.assertTrue(part.is_finished())

    @parameterized.expand(["STARTED", "WAITING"])
    def test_is_not_finished(self, status):
        part = o.ComposePart("test", "/tmp/my.conf")
        part.status = status
        self.assertFalse(part.is_finished())

    @mock.patch("pungi_utils.orchestrator.fill_in_config_file")
    @mock.patch("pungi_utils.orchestrator.get_compose_dir")
    @mock.patch("kobo.conf.PyConfigParser")
    def test_setup_start(self, Conf, gcd, ficf):
        def pth(*path):
            return os.path.join(self.topdir, *path)

        conf = o.Config(
            pth("tgt"), "production", "RC-1.0", "/old", pth("cfg"), None, None
        )
        part = o.ComposePart("test", "/tmp/my.conf")
        parts = {"base": mock.Mock(path="/base", is_finished=lambda: True)}
        Conf.return_value.opened_files = ["foo.conf"]

        part.setup_start(conf, parts)

        self.assertEqual(part.status, "STARTED")
        self.assertEqual(part.path, gcd.return_value)
        self.assertEqual(part.log_file, pth("tgt", "logs", "test.log"))
        self.assertEqual(
            ficf.call_args_list,
            [mock.call("foo.conf", {"part-base": "/base", "configdir": pth("cfg")})],
        )
        self.assertEqual(
            gcd.call_args_list,
            [
                mock.call(
                    pth("tgt/parts"),
                    Conf.return_value,
                    compose_type="production",
                    compose_label="RC-1.0",
                )
            ],
        )

    @parameterized.expand(
        [
            # Nothing blocking, no change
            ([], [], o.Status.READY),
            # Remove last blocker and switch to READY
            (["finished"], [], o.Status.READY),
            # Blocker remaining, stay in WAITING
            (["finished", "block"], ["block"], o.Status.WAITING),
        ]
    )
    def test_unblock_on(self, deps, blockers, status):
        part = o.ComposePart("test", "/tmp/my.conf", dependencies=deps)
        part.unblock_on("finished")
        self.assertItemsEqual(part.blocked_on, blockers)
        self.assertEqual(part.status, status)


class TestStartPart(PungiTestCase):
    @mock.patch("subprocess.Popen")
    def test_start(self, Popen):
        part = mock.Mock(log_file=os.path.join(self.topdir, "log"))
        config = mock.Mock()
        parts = mock.Mock()
        cmd = ["pungi-koji", "..."]

        part.get_cmd.return_value = cmd

        proc = o.start_part(config, parts, part)

        self.assertEqual(
            part.mock_calls,
            [mock.call.setup_start(config, parts), mock.call.get_cmd(config)],
        )
        self.assertEqual(proc, Popen.return_value)
        self.assertEqual(
            Popen.call_args_list,
            [mock.call(cmd, stdout=mock.ANY, stderr=subprocess.STDOUT)],
        )


class TestHandleFinished(BaseTestCase):
    def setUp(self):
        self.config = mock.Mock()
        self.linker = mock.Mock()
        self.parts = {"a": mock.Mock(), "b": mock.Mock()}

    @mock.patch("pungi_utils.orchestrator.update_metadata")
    @mock.patch("pungi_utils.orchestrator.copy_part")
    def test_handle_success(self, cp, um):
        proc = mock.Mock(returncode=0)
        o.handle_finished(self.config, self.linker, self.parts, proc, self.parts["a"])

        self.assertEqual(
            self.parts["a"].mock_calls,
            [mock.call.refresh_status(), mock.call.unblock_on(self.parts["a"].name)],
        )
        self.assertEqual(
            self.parts["b"].mock_calls, [mock.call.unblock_on(self.parts["a"].name)]
        )
        self.assertEqual(
            cp.call_args_list, [mock.call(self.config, self.linker, self.parts["a"])]
        )
        self.assertEqual(um.call_args_list, [mock.call(self.config, self.parts["a"])])

    @mock.patch("pungi_utils.orchestrator.block_on")
    def test_handle_failure(self, bo):
        proc = mock.Mock(returncode=1)
        o.handle_finished(self.config, self.linker, self.parts, proc, self.parts["a"])

        self.assertEqual(self.parts["a"].mock_calls, [mock.call.refresh_status()])

        self.assertEqual(
            bo.call_args_list, [mock.call(self.parts, self.parts["a"].name)]
        )


class TestBlockOn(BaseTestCase):
    def test_single(self):
        parts = {"b": o.ComposePart("b", "b.conf", dependencies=["a"])}

        o.block_on(parts, "a")

        self.assertEqual(parts["b"].status, o.Status.BLOCKED)

    def test_chain(self):
        parts = {
            "b": o.ComposePart("b", "b.conf", dependencies=["a"]),
            "c": o.ComposePart("c", "c.conf", dependencies=["b"]),
            "d": o.ComposePart("d", "d.conf", dependencies=["c"]),
        }

        o.block_on(parts, "a")

        self.assertEqual(parts["b"].status, o.Status.BLOCKED)
        self.assertEqual(parts["c"].status, o.Status.BLOCKED)
        self.assertEqual(parts["d"].status, o.Status.BLOCKED)


class TestUpdateMetadata(PungiTestCase):
    def assertEqualJSON(self, f1, f2):
        with open(f1) as f:
            actual = json.load(f)
        with open(f2) as f:
            expected = json.load(f)
        self.assertEqual(actual, expected)

    def assertEqualMetadata(self, expected):
        expected_dir = os.path.join(FIXTURE_DIR, expected, "compose/metadata")
        for f in os.listdir(expected_dir):
            self.assertEqualJSON(
                os.path.join(self.tgt, "compose/metadata", f),
                os.path.join(expected_dir, f),
            )

    @parameterized.expand(["empty-metadata", "basic-metadata"])
    def test_merge_into_empty(self, fixture):
        self.tgt = os.path.join(self.topdir, "target")

        conf = o.Config(self.tgt, "production", None, None, None, None, [])
        part = o.ComposePart("test", "/tmp/my.conf")
        part.path = os.path.join(FIXTURE_DIR, "DP-1.0-20181001.n.0")

        shutil.copytree(os.path.join(FIXTURE_DIR, fixture), self.tgt)

        o.update_metadata(conf, part)

        self.assertEqualMetadata(fixture + "-merged")


class TestCopyPart(PungiTestCase):
    @mock.patch("pungi_utils.orchestrator.hardlink_dir")
    def test_copy(self, hd):
        self.tgt = os.path.join(self.topdir, "target")
        conf = o.Config(self.tgt, "production", None, None, None, None, [])
        linker = mock.Mock()
        part = o.ComposePart("test", "/tmp/my.conf")
        part.path = os.path.join(FIXTURE_DIR, "DP-1.0-20161013.t.4")

        o.copy_part(conf, linker, part)

        self.assertItemsEqual(
            hd.call_args_list,
            [
                mock.call(
                    linker,
                    os.path.join(part.path, "compose", variant),
                    os.path.join(self.tgt, "compose", variant),
                )
                for variant in ["Client", "Server"]
            ],
        )


class TestHardlinkDir(PungiTestCase):
    def test_hardlinking(self):
        linker = mock.Mock()
        src = os.path.join(self.topdir, "src")
        dst = os.path.join(self.topdir, "dst")
        files = ["file.txt", "nested/deep/another.txt"]

        for f in files:
            touch(os.path.join(src, f))

        o.hardlink_dir(linker, src, dst)

        self.assertItemsEqual(
            linker.queue_put.call_args_list,
            [mock.call((os.path.join(src, f), os.path.join(dst, f))) for f in files],
        )


class TestCheckFinishedProcesses(BaseTestCase):
    def test_nothing_finished(self):
        k1 = mock.Mock(returncode=None)
        v1 = mock.Mock()
        processes = {k1: v1}

        self.assertItemsEqual(o.check_finished_processes(processes), [])

    def test_yields_finished(self):
        k1 = mock.Mock(returncode=None)
        v1 = mock.Mock()
        k2 = mock.Mock(returncode=0)
        v2 = mock.Mock()
        processes = {k1: v1, k2: v2}

        self.assertItemsEqual(o.check_finished_processes(processes), [(k2, v2)])

    def test_yields_failed(self):
        k1 = mock.Mock(returncode=1)
        v1 = mock.Mock()
        processes = {k1: v1}

        self.assertItemsEqual(o.check_finished_processes(processes), [(k1, v1)])


class _Part(object):
    def __init__(self, name, parent=None, fails=False, status=None):
        self.name = name
        self.finished = False
        self.status = o.Status.WAITING if parent else o.Status.READY
        if status:
            self.status = status
        self.proc = mock.Mock(name="proc_%s" % name, pid=hash(self))
        self.parent = parent
        self.fails = fails
        self.failable = False
        self.path = "/path/to/%s" % name
        self.blocked_on = set([parent]) if parent else set()

    def is_finished(self):
        return self.finished or self.status == "FINISHED"

    def __repr__(self):
        return "<_Part(%r, parent=%r)>" % (self.name, self.parent)


def with_mocks(parts, finish_order, wait_results):
    """Setup all mocks and create dict with the parts.
    :param finish_order: nested list: first element contains parts that finish
                         in first iteration, etc.
    :param wait_results: list of names of processes that are returned by wait in each
                         iteration
    """

    def decorator(func):
        @wraps(func)
        def worker(self, lp, update_status, cfp, hf, sp, wait):
            self.parts = dict((p.name, p) for p in parts)
            self.linker = lp.return_value.__enter__.return_value

            update_status.side_effect = self.mock_update
            hf.side_effect = self.mock_finish
            sp.side_effect = self.mock_start

            finish = [[]]
            for grp in finish_order:
                finish.append([(self.parts[p].proc, self.parts[p]) for p in grp])

            cfp.side_effect = finish
            wait.side_effect = [(self.parts[p].proc.pid, 0) for p in wait_results]

            func(self)

            self.assertEqual(lp.call_args_list, [mock.call("hardlink")])

        return worker

    return decorator


@mock.patch("os.wait")
@mock.patch("pungi_utils.orchestrator.start_part")
@mock.patch("pungi_utils.orchestrator.handle_finished")
@mock.patch("pungi_utils.orchestrator.check_finished_processes")
@mock.patch("pungi_utils.orchestrator.update_status")
@mock.patch("pungi_utils.orchestrator.linker_pool")
class TestRunAll(BaseTestCase):
    def setUp(self):
        self.maxDiff = None
        self.conf = mock.Mock(name="global_config")
        self.calls = []

    def mock_update(self, global_config, parts):
        self.assertEqual(global_config, self.conf)
        self.assertEqual(parts, self.parts)
        self.calls.append("update_status")

    def mock_start(self, global_config, parts, part):
        self.assertEqual(global_config, self.conf)
        self.assertEqual(parts, self.parts)
        self.calls.append(("start_part", part.name))
        part.status = o.Status.STARTED
        return part.proc

    @property
    def sorted_calls(self):
        """Sort the consecutive calls of the same function based on the argument."""

        def key(val):
            return val[0] if isinstance(val, tuple) else val

        return list(
            itertools.chain.from_iterable(
                sorted(grp, key=operator.itemgetter(1))
                for _, grp in itertools.groupby(self.calls, key)
            )
        )

    def mock_finish(self, global_config, linker, parts, proc, part):
        self.assertEqual(global_config, self.conf)
        self.assertEqual(linker, self.linker)
        self.assertEqual(parts, self.parts)
        self.calls.append(("handle_finished", part.name))
        for child in parts.values():
            if child.parent == part.name:
                child.status = o.Status.BLOCKED if part.fails else o.Status.READY
        part.status = "DOOMED" if part.fails else "FINISHED"

    @with_mocks(
        [_Part("fst"), _Part("snd", parent="fst")], [["fst"], ["snd"]], ["fst", "snd"]
    )
    def test_sequential(self):
        o.run_all(self.conf, self.parts)

        self.assertEqual(
            self.sorted_calls,
            [
                # First iteration starts fst
                "update_status",
                ("start_part", "fst"),
                # Second iteration handles finish of fst and starts snd
                "update_status",
                ("handle_finished", "fst"),
                ("start_part", "snd"),
                # Third iteration handles finish of snd
                "update_status",
                ("handle_finished", "snd"),
                # Final update of status
                "update_status",
            ],
        )

    @with_mocks([_Part("fst"), _Part("snd")], [["fst", "snd"]], ["fst"])
    def test_parallel(self):
        o.run_all(self.conf, self.parts)

        self.assertEqual(
            self.sorted_calls,
            [
                # First iteration starts both fst and snd
                "update_status",
                ("start_part", "fst"),
                ("start_part", "snd"),
                # Second iteration handles finish of both of them
                "update_status",
                ("handle_finished", "fst"),
                ("handle_finished", "snd"),
                # Final update of status
                "update_status",
            ],
        )

    @with_mocks(
        [_Part("1"), _Part("2", parent="1"), _Part("3", parent="1")],
        [["1"], ["2", "3"]],
        ["1", "2"],
    )
    def test_waits_for_dep_then_parallel_with_simultaneous_end(self):
        o.run_all(self.conf, self.parts)

        self.assertEqual(
            self.sorted_calls,
            [
                # First iteration starts first part
                "update_status",
                ("start_part", "1"),
                # Second iteration starts 2 and 3
                "update_status",
                ("handle_finished", "1"),
                ("start_part", "2"),
                ("start_part", "3"),
                # Both 2 and 3 end in third iteration
                "update_status",
                ("handle_finished", "2"),
                ("handle_finished", "3"),
                # Final update of status
                "update_status",
            ],
        )

    @with_mocks(
        [_Part("1"), _Part("2", parent="1"), _Part("3", parent="1")],
        [["1"], ["3"], ["2"]],
        ["1", "3", "2"],
    )
    def test_waits_for_dep_then_parallel_with_different_end_times(self):
        o.run_all(self.conf, self.parts)

        self.assertEqual(
            self.sorted_calls,
            [
                # First iteration starts first part
                "update_status",
                ("start_part", "1"),
                # Second iteration starts 2 and 3
                "update_status",
                ("handle_finished", "1"),
                ("start_part", "2"),
                ("start_part", "3"),
                # Third iteration sees 3 finish
                "update_status",
                ("handle_finished", "3"),
                # Fourth iteration, 2 finishes
                "update_status",
                ("handle_finished", "2"),
                # Final update of status
                "update_status",
            ],
        )

    @with_mocks(
        [_Part("fst", fails=True), _Part("snd", parent="fst")], [["fst"]], ["fst"]
    )
    def test_blocked(self):
        o.run_all(self.conf, self.parts)

        self.assertEqual(
            self.sorted_calls,
            [
                # First iteration starts first part
                "update_status",
                ("start_part", "fst"),
                # Second iteration handles fail of first part
                "update_status",
                ("handle_finished", "fst"),
                # Final update of status
                "update_status",
            ],
        )


@mock.patch("pungi_utils.orchestrator.get_compose_dir")
class TestGetTargetDir(BaseTestCase):
    def test_with_absolute_path(self, gcd):
        config = {"target": "/tgt", "compose_type": "nightly"}
        cfg = mock.Mock()
        cfg.get.side_effect = lambda _, k: config[k]
        ci = mock.Mock()
        res = o.get_target_dir(cfg, ci, None, reldir="/checkout")
        self.assertEqual(res, gcd.return_value)
        self.assertEqual(
            gcd.call_args_list,
            [mock.call("/tgt", ci, compose_type="nightly", compose_label=None)],
        )

    def test_with_relative_path(self, gcd):
        config = {"target": "tgt", "compose_type": "nightly"}
        cfg = mock.Mock()
        cfg.get.side_effect = lambda _, k: config[k]
        ci = mock.Mock()
        res = o.get_target_dir(cfg, ci, None, reldir="/checkout")
        self.assertEqual(res, gcd.return_value)
        self.assertEqual(
            gcd.call_args_list,
            [
                mock.call(
                    "/checkout/tgt", ci, compose_type="nightly", compose_label=None
                )
            ],
        )


class TestComputeStatus(BaseTestCase):
    @parameterized.expand(
        [
            ([("FINISHED", False)], "FINISHED"),
            ([("FINISHED", False), ("STARTED", False)], "STARTED"),
            ([("FINISHED", False), ("STARTED", False), ("WAITING", False)], "STARTED"),
            ([("FINISHED", False), ("DOOMED", False)], "DOOMED"),
            (
                [("FINISHED", False), ("BLOCKED", True), ("DOOMED", True)],
                "FINISHED_INCOMPLETE",
            ),
            ([("FINISHED", False), ("BLOCKED", False), ("DOOMED", True)], "DOOMED"),
            ([("FINISHED", False), ("DOOMED", True)], "FINISHED_INCOMPLETE"),
            ([("FINISHED", False), ("STARTED", False), ("DOOMED", False)], "STARTED"),
        ]
    )
    def test_cases(self, statuses, expected):
        self.assertEqual(o.compute_status(statuses), expected)


class TestUpdateStatus(PungiTestCase):
    def test_updating(self):
        os.makedirs(os.path.join(self.topdir, "compose/metadata"))
        conf = o.Config(
            self.topdir, "production", "RC-1.0", "/old", "/cfg", 1234, ["--quiet"]
        )
        o.update_status(
            conf,
            {"1": _Part("1", status="FINISHED"), "2": _Part("2", status="STARTED")},
        )
        self.assertFileContent(os.path.join(self.topdir, "STATUS"), "STARTED")
        self.assertFileContent(
            os.path.join(self.topdir, "compose/metadata/parts.json"),
            dedent(
                """\
                {
                  "1": {
                    "path": "/path/to/1",
                    "status": "FINISHED"
                  },
                  "2": {
                    "path": "/path/to/2",
                    "status": "STARTED"
                  }
                }
                """
            ),
        )


@mock.patch("pungi_utils.orchestrator.get_target_dir")
class TestPrepareComposeDir(PungiTestCase):
    def setUp(self):
        super(TestPrepareComposeDir, self).setUp()
        self.conf = mock.Mock(name="config")
        self.main_config = "/some/config"
        self.compose_info = mock.Mock(name="compose_info")

    def test_new_compose(self, gtd):
        def mock_get_target(conf, compose_info, label, reldir):
            self.assertEqual(conf, self.conf)
            self.assertEqual(compose_info, self.compose_info)
            self.assertEqual(label, args.label)
            self.assertEqual(reldir, "/some")
            touch(os.path.join(self.topdir, "work/global/composeinfo-base.json"), "WOO")
            return self.topdir

        gtd.side_effect = mock_get_target
        args = mock.Mock(name="args", spec=["label"])
        retval = o.prepare_compose_dir(
            self.conf, args, self.main_config, self.compose_info
        )
        self.assertEqual(retval, self.topdir)
        self.assertFileContent(
            os.path.join(self.topdir, "compose/metadata/composeinfo.json"), "WOO"
        )
        self.assertTrue(os.path.isdir(os.path.join(self.topdir, "logs")))
        self.assertTrue(os.path.isdir(os.path.join(self.topdir, "parts")))
        self.assertTrue(os.path.isdir(os.path.join(self.topdir, "work/global")))
        self.assertFileContent(
            os.path.join(self.topdir, "STATUS"), "STARTED"
        )

    def test_restarting_compose(self, gtd):
        args = mock.Mock(name="args", spec=["label", "compose_path"])
        retval = o.prepare_compose_dir(
            self.conf, args, self.main_config, self.compose_info
        )
        self.assertEqual(gtd.call_args_list, [])
        self.assertEqual(retval, args.compose_path)


class TestLoadPartsMetadata(PungiTestCase):
    def test_loading(self):
        touch(
            os.path.join(self.topdir, "compose/metadata/parts.json"), '{"foo": "bar"}'
        )
        conf = mock.Mock(target=self.topdir)

        self.assertEqual(o.load_parts_metadata(conf), {"foo": "bar"})


@mock.patch("pungi_utils.orchestrator.load_parts_metadata")
class TestSetupForRestart(BaseTestCase):
    def setUp(self):
        self.conf = mock.Mock(name="global_config")

    def test_restart_ok(self, lpm):
        lpm.return_value = {
            "p1": {"status": "FINISHED", "path": "/p1"},
            "p2": {"status": "DOOMED", "path": "/p2"},
        }
        parts = {"p1": _Part("p1"), "p2": _Part("p2", parent="p1")}

        o.setup_for_restart(self.conf, parts, ["p2"])

        self.assertEqual(parts["p1"].status, "FINISHED")
        self.assertEqual(parts["p1"].path, "/p1")
        self.assertEqual(parts["p2"].status, "READY")
        self.assertEqual(parts["p2"].path, None)

    def test_restart_one_blocked_one_ok(self, lpm):
        lpm.return_value = {
            "p1": {"status": "DOOMED", "path": "/p1"},
            "p2": {"status": "DOOMED", "path": "/p2"},
            "p3": {"status": "WAITING", "path": None},
        }
        parts = {
            "p1": _Part("p1"),
            "p2": _Part("p2", parent="p1"),
            "p3": _Part("p3", parent="p2"),
        }

        o.setup_for_restart(self.conf, parts, ["p1", "p3"])

        self.assertEqual(parts["p1"].status, "READY")
        self.assertEqual(parts["p1"].path, None)
        self.assertEqual(parts["p2"].status, "DOOMED")
        self.assertEqual(parts["p2"].path, "/p2")
        self.assertEqual(parts["p3"].status, "WAITING")
        self.assertEqual(parts["p3"].path, None)

    def test_restart_all_blocked(self, lpm):
        lpm.return_value = {
            "p1": {"status": "DOOMED", "path": "/p1"},
            "p2": {"status": "STARTED", "path": "/p2"},
        }
        parts = {"p1": _Part("p1"), "p2": _Part("p2", parent="p1")}

        with self.assertRaises(RuntimeError):
            o.setup_for_restart(self.conf, parts, ["p2"])

        self.assertEqual(parts["p1"].status, "DOOMED")
        self.assertEqual(parts["p1"].path, "/p1")
        self.assertEqual(parts["p2"].status, "WAITING")
        self.assertEqual(parts["p2"].path, None)


@mock.patch("atexit.register")
@mock.patch("kobo.shortcuts.run")
class TestRunKinit(BaseTestCase):
    def test_without_config(self, run, register):
        conf = mock.Mock()
        conf.getboolean.return_value = False

        o.run_kinit(conf)

        self.assertEqual(run.call_args_list, [])
        self.assertEqual(register.call_args_list, [])

    @mock.patch.dict("os.environ")
    def test_with_config(self, run, register):
        conf = mock.Mock()
        conf.getboolean.return_value = True
        conf.get.side_effect = lambda section, option: option

        o.run_kinit(conf)

        self.assertEqual(
            run.call_args_list,
            [mock.call(["kinit", "-k", "-t", "kerberos_keytab", "kerberos_principal"])],
        )
        self.assertEqual(
            register.call_args_list, [mock.call(os.remove, os.environ["KRB5CCNAME"])]
        )


@mock.patch.dict("os.environ", {}, clear=True)
class TestGetScriptEnv(BaseTestCase):
    def test_without_metadata(self):
        env = o.get_script_env("/foobar")
        self.assertEqual(env, {"COMPOSE_PATH": "/foobar"})

    def test_with_metadata(self):
        compose_dir = os.path.join(FIXTURE_DIR, "DP-1.0-20161013.t.4")
        env = o.get_script_env(compose_dir)
        self.maxDiff = None
        self.assertEqual(
            env,
            {
                "COMPOSE_PATH": compose_dir,
                "COMPOSE_ID": "DP-1.0-20161013.t.4",
                "COMPOSE_DATE": "20161013",
                "COMPOSE_TYPE": "test",
                "COMPOSE_RESPIN": "4",
                "COMPOSE_LABEL": "",
                "RELEASE_ID": "DP-1.0",
                "RELEASE_NAME": "Dummy Product",
                "RELEASE_SHORT": "DP",
                "RELEASE_VERSION": "1.0",
                "RELEASE_TYPE": "ga",
                "RELEASE_IS_LAYERED": "",
            },
        )


class TestRunScripts(BaseTestCase):
    @mock.patch("pungi_utils.orchestrator.get_script_env")
    @mock.patch("kobo.shortcuts.run")
    def test_run_scripts(self, run, get_env):
        commands = """
           date
           env
           """

        o.run_scripts("pref_", "/tmp/compose", commands)

        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    "date",
                    logfile="/tmp/compose/logs/pref_0.log",
                    env=get_env.return_value,
                ),
                mock.call(
                    "env",
                    logfile="/tmp/compose/logs/pref_1.log",
                    env=get_env.return_value,
                ),
            ],
        )


@mock.patch("pungi.notifier.PungiNotifier")
class TestSendNotification(BaseTestCase):
    def test_no_command(self, notif):
        o.send_notification("/foobar", None, None)
        self.assertEqual(notif.mock_calls, [])

    @mock.patch("pungi.util.load_config")
    def test_with_command_and_translate(self, load_config, notif):
        compose_dir = os.path.join(FIXTURE_DIR, "DP-1.0-20161013.t.4")
        load_config.return_value = {
            "translate_paths": [(os.path.dirname(compose_dir), "http://example.com")],
        }
        parts = {"foo": mock.Mock()}

        o.send_notification(compose_dir, "handler", parts)

        self.assertEqual(len(notif.mock_calls), 2)
        self.assertEqual(notif.mock_calls[0], mock.call(["handler"]))
        _, args, kwargs = notif.mock_calls[1]
        self.assertEqual(args, ("status-change", ))
        self.assertEqual(
            kwargs,
            {
                "status": "FINISHED",
                "workdir": compose_dir,
                "location": "http://example.com/DP-1.0-20161013.t.4",
                "compose_id": "DP-1.0-20161013.t.4",
                "compose_date": "20161013",
                "compose_type": "test",
                "compose_respin": "4",
                "compose_label": None,
                "release_id": "DP-1.0",
                "release_name": "Dummy Product",
                "release_short": "DP",
                "release_version": "1.0",
                "release_type": "ga",
                "release_is_layered": False,
            },
        )
        self.assertEqual(load_config.call_args_list, [mock.call(parts["foo"].config)])
