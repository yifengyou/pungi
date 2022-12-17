# -*- coding: utf-8 -*-

import argparse
import mock
import os

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import tempfile
import shutil
import subprocess
import six

from pungi import compose
from pungi import util

from tests.helpers import touch, PungiTestCase, mk_boom


class TestGitRefResolver(unittest.TestCase):
    @mock.patch("pungi.util.run")
    def test_successful_resolve(self, run):
        run.return_value = (0, "CAFEBABE\tHEAD\n")

        url = util.resolve_git_url("https://git.example.com/repo.git?somedir#HEAD")

        self.assertEqual(url, "https://git.example.com/repo.git?somedir#CAFEBABE")
        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
            universal_newlines=True,
        )

    @mock.patch("pungi.util.run")
    def test_successful_resolve_branch(self, run):
        run.return_value = (0, "CAFEBABE\trefs/heads/f24\n")

        url = util.resolve_git_url(
            "https://git.example.com/repo.git?somedir#origin/f24"
        )

        self.assertEqual(url, "https://git.example.com/repo.git?somedir#CAFEBABE")
        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "refs/heads/f24"],
            universal_newlines=True,
        )

    def test_resolve_ref_with_commit_id(self):
        ref = util.resolve_git_ref("https://git.example.com/repo.git", "a" * 40)
        self.assertEqual(ref, "a" * 40)

    @mock.patch("pungi.util.run")
    def test_resolve_ref_multiple_matches(self, run):
        run.return_value = (
            0,
            "CAFEBABE\trefs/heads/master\nBABECAFE\trefs/remotes/origin/master",
        )

        ref = util.resolve_git_ref("https://git.example.com/repo.git", "master")

        self.assertEqual(ref, "CAFEBABE")
        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "master"],
            universal_newlines=True,
        )

    @mock.patch("pungi.util.run")
    def test_resolve_ref_with_remote_head(self, run):
        run.return_value = (0, "CAFEBABE\tHEAD\nBABECAFE\trefs/remotes/origin/HEAD")

        ref = util.resolve_git_ref("https://git.example.com/repo.git", "HEAD")

        self.assertEqual(ref, "CAFEBABE")
        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
            universal_newlines=True,
        )

    @mock.patch("pungi.util.run")
    def test_resolve_missing_spec(self, run):
        url = util.resolve_git_url("https://git.example.com/repo.git")

        self.assertEqual(url, "https://git.example.com/repo.git")
        self.assertEqual(run.mock_calls, [])

    @mock.patch("pungi.util.run")
    def test_resolve_non_head_spec(self, run):
        url = util.resolve_git_url("https://git.example.com/repo.git#some-tag")

        self.assertEqual(url, "https://git.example.com/repo.git#some-tag")
        self.assertEqual(run.mock_calls, [])

    @mock.patch("pungi.util.run")
    def test_resolve_ambiguous(self, run):
        run.return_value = (0, "CAFEBABE\tF11\nDEADBEEF\tF10\n")

        with self.assertRaises(RuntimeError):
            util.resolve_git_url("https://git.example.com/repo.git?somedir#HEAD")

        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
            universal_newlines=True,
        )

    @mock.patch("pungi.util.run")
    def test_resolve_keep_empty_query_string(self, run):
        run.return_value = (0, "CAFEBABE\tHEAD\n")

        url = util.resolve_git_url("https://git.example.com/repo.git?#HEAD")

        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
            universal_newlines=True,
        )
        self.assertEqual(url, "https://git.example.com/repo.git?#CAFEBABE")

    @mock.patch("pungi.util.run")
    def test_resolve_strip_git_plus_prefix(self, run):
        run.return_value = (0, "CAFEBABE\tHEAD\n")

        url = util.resolve_git_url("git+https://git.example.com/repo.git#HEAD")

        run.assert_called_once_with(
            ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
            universal_newlines=True,
        )
        self.assertEqual(url, "git+https://git.example.com/repo.git#CAFEBABE")

    @mock.patch("pungi.util.run")
    def test_resolve_no_branch_in_remote(self, run):
        run.return_value = (0, "")

        with self.assertRaises(RuntimeError) as ctx:
            util.resolve_git_url(
                "https://git.example.com/repo.git?somedir#origin/my-branch"
            )

        run.assert_called_once_with(
            [
                "git",
                "ls-remote",
                "https://git.example.com/repo.git",
                "refs/heads/my-branch",
            ],
            universal_newlines=True,
        )
        self.assertIn("ref does not exist in remote repo", str(ctx.exception))

    @mock.patch("time.sleep")
    @mock.patch("pungi.util.run")
    def test_retry(self, run, sleep):
        run.side_effect = [RuntimeError("Boom"), (0, "CAFEBABE\tHEAD\n")]

        url = util.resolve_git_url("https://git.example.com/repo.git?somedir#HEAD")

        self.assertEqual(url, "https://git.example.com/repo.git?somedir#CAFEBABE")
        self.assertEqual(sleep.call_args_list, [mock.call(30)])
        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    ["git", "ls-remote", "https://git.example.com/repo.git", "HEAD"],
                    universal_newlines=True,
                )
            ]
            * 2,
        )

    @mock.patch("pungi.util.resolve_git_ref")
    @mock.patch("pungi.util.resolve_git_url")
    def test_resolver_offline(self, mock_resolve_url, mock_resolve_ref):
        resolver = util.GitUrlResolver(offline=True)
        self.assertEqual(
            resolver("http://example.com/repo.git#HEAD"),
            "http://example.com/repo.git#HEAD",
        )
        self.assertEqual(mock_resolve_url.call_args_list, [])
        self.assertEqual(mock_resolve_ref.call_args_list, [])

    @mock.patch("pungi.util.resolve_git_ref")
    @mock.patch("pungi.util.resolve_git_url")
    def test_resolver_offline_branch(self, mock_resolve_url, mock_resolve_ref):
        resolver = util.GitUrlResolver(offline=True)
        self.assertEqual(
            resolver("http://example.com/repo.git", "master"),
            "master",
        )
        self.assertEqual(mock_resolve_url.call_args_list, [])
        self.assertEqual(mock_resolve_ref.call_args_list, [])

    @mock.patch("pungi.util.resolve_git_ref")
    @mock.patch("pungi.util.resolve_git_url")
    def test_resolver_caches_calls(self, mock_resolve_url, mock_resolve_ref):
        url1 = "http://example.com/repo.git#HEAD"
        url2 = "http://example.com/repo.git#master"
        url3 = "http://example.com/repo.git"
        ref1 = "foo"
        ref2 = "bar"
        mock_resolve_url.side_effect = ["1", "2"]
        mock_resolve_ref.side_effect = ["cafe", "beef"]
        resolver = util.GitUrlResolver()
        self.assertEqual(resolver(url1), "1")
        self.assertEqual(resolver(url1), "1")
        self.assertEqual(resolver(url3, ref1), "cafe")
        self.assertEqual(resolver(url3, ref2), "beef")
        self.assertEqual(resolver(url2), "2")
        self.assertEqual(resolver(url3, ref1), "cafe")
        self.assertEqual(resolver(url1), "1")
        self.assertEqual(resolver(url3, ref2), "beef")
        self.assertEqual(resolver(url2), "2")
        self.assertEqual(resolver(url3, ref2), "beef")
        self.assertEqual(
            mock_resolve_url.call_args_list, [mock.call(url1), mock.call(url2)]
        )
        self.assertEqual(
            mock_resolve_ref.call_args_list,
            [mock.call(url3, ref1), mock.call(url3, ref2)],
        )

    @mock.patch("pungi.util.resolve_git_url")
    def test_resolver_caches_failure(self, mock_resolve):
        url = "http://example.com/repo.git#HEAD"
        mock_resolve.side_effect = mk_boom(util.GitUrlResolveError, "failed")
        resolver = util.GitUrlResolver()
        with self.assertRaises(util.GitUrlResolveError):
            resolver(url)
        with self.assertRaises(util.GitUrlResolveError):
            resolver(url)
        self.assertEqual(mock_resolve.call_args_list, [mock.call(url)])


class TestGetVariantData(unittest.TestCase):
    def test_get_simple(self):
        conf = {"foo": {"^Client$": 1}}
        result = util.get_variant_data(conf, "foo", mock.Mock(uid="Client"))
        self.assertEqual(result, [1])

    def test_get_make_list(self):
        conf = {"foo": {"^Client$": [1, 2], "^.*$": 3}}
        result = util.get_variant_data(conf, "foo", mock.Mock(uid="Client"))
        six.assertCountEqual(self, result, [1, 2, 3])

    def test_not_matching_arch(self):
        conf = {"foo": {"^Client$": [1, 2]}}
        result = util.get_variant_data(conf, "foo", mock.Mock(uid="Server"))
        self.assertEqual(result, [])

    def test_handle_missing_config(self):
        result = util.get_variant_data({}, "foo", mock.Mock(uid="Client"))
        self.assertEqual(result, [])

    def test_get_save_pattern(self):
        conf = {"foo": {"^Client$": 1, "^NotClient$": 2}}
        patterns = set()
        result = util.get_variant_data(
            conf, "foo", mock.Mock(uid="Client"), keys=patterns
        )
        self.assertEqual(result, [1])
        self.assertEqual(patterns, set(["^Client$"]))


class TestVolumeIdGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_volid(self, ci):
        all_keys = [
            (
                ["arch", "compose_id", "date", "disc_type"],
                "x86_64-compose_id-20160107-",
            ),
            (
                ["label", "label_major_version", "release_short", "respin"],
                "RC-1.0-1-rel_short2-2",
            ),
            (["type", "type_suffix", "variant", "version"], "nightly-.n-Server-6.0"),
        ]
        for keys, expected in all_keys:
            format = "-".join(["%(" + k + ")s" for k in keys])
            conf = {
                "release_short": "rel_short2",
                "release_version": "6.0",
                "image_volid_formats": [format],
                "image_volid_layered_product_formats": [],
                "volume_id_substitutions": {},
                "restricted_volid": False,
            }
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

            c = compose.Compose(conf, self.tmp_dir)

            volid = util.get_volid(c, "x86_64", variant, disc_type=False)

            self.assertEqual(volid, expected)

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_restricted_volid(self, ci):
        all_keys = [
            (
                ["arch", "compose_id", "date", "disc_type"],
                "x86_64-compose_id-20160107-",
            ),
            (
                ["label", "label_major_version", "release_short", "respin"],
                "RC-1-0-1-rel_short2-2",
            ),
            (["type", "type_suffix", "variant", "version"], "nightly--n-Server-6-0"),
        ]
        for keys, expected in all_keys:
            format = "-".join(["%(" + k + ")s" for k in keys])
            conf = {
                "release_short": "rel_short2",
                "release_version": "6.0",
                "image_volid_formats": [format],
                "image_volid_layered_product_formats": [],
                "volume_id_substitutions": {},
                "restricted_volid": True,
            }
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

            c = compose.Compose(conf, self.tmp_dir)

            volid = util.get_volid(c, "x86_64", variant, disc_type=False)

            self.assertEqual(volid, expected)

    @mock.patch("pungi.compose.ComposeInfo")
    def test_get_volid_too_long(self, ci):
        conf = {
            "release_short": "rel_short2",
            "release_version": "6.0",
            "image_volid_formats": [
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # 34 chars
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",  # 33 chars
            ],
            "image_volid_layered_product_formats": [],
            "volume_id_substitutions": {},
        }
        variant = mock.Mock(uid="Server", type="variant")
        c = compose.Compose(conf, self.tmp_dir)

        with self.assertRaises(ValueError) as ctx:
            util.get_volid(c, "x86_64", variant, disc_type=False)

        self.assertIn("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", str(ctx.exception))
        self.assertIn("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", str(ctx.exception))

    @mock.patch("pungi.compose.ComposeInfo")
    def test_apply_substitutions(self, ci):
        all_keys = [
            (
                "Fedora-WorkstationOstree-ostree-x86_64-rawhide",
                "Fedora-WS-ostree-x86_64-rawhide",
            ),
            (
                "Fedora-WorkstationOstree-ostree-x86_64-Rawhide",
                "Fedora-WS-ostree-x86_64-rawh",
            ),
            ("x86_64-compose_id-20160107", "x86_64-compose_id-20160107"),
            ("x86_64-compose_id-20160107-Alpha", "x86_64-compose_id-20160107-A"),
            # These test the case where one substitution is a subset
            # of the other, but sorts alphabetically ahead of it, to
            # make sure we're correctly sorting by length
            ("Fedora-zzzaaaaaazzz-Rawhide", "Fedora-zzz-rawh"),
            ("Fedora-aaaaaa-Rawhide", "Fedora-aaa-rawh"),
        ]
        for volid, expected in all_keys:
            conf = {
                "volume_id_substitutions": {
                    "Rawhide": "rawh",
                    "WorkstationOstree": "WS",
                    "Workstation": "WS",
                    "Alpha": "A",
                    "zzzaaaaaazzz": "zzz",
                    "aaaaaa": "aaa",
                }
            }
            c = compose.Compose(conf, self.tmp_dir)
            transformed_volid = util._apply_substitutions(c, volid)
            self.assertEqual(transformed_volid, expected)


class TestFindOldCompose(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_finds_single(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.0/STATUS", "FINISHED")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertEqual(old, self.tmp_dir + "/Fedora-Rawhide-20160229.0")

    def test_ignores_in_progress(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.0/STATUS", "STARTED")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertIsNone(old)

    def test_only_considers_allowed_status(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.0/STATUS", "FINISHED")
        old = util.find_old_compose(
            self.tmp_dir, "Fedora", "Rawhide", "", allowed_statuses=["DOOMED"]
        )
        self.assertIsNone(old)

    def test_finds_latest(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160228.0/STATUS", "DOOMED")
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.0/STATUS", "FINISHED")
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.1/STATUS", "FINISHED_INCOMPLETE")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertEqual(old, self.tmp_dir + "/Fedora-Rawhide-20160229.1")

    def test_find_correct_type(self):
        touch(self.tmp_dir + "/Fedora-26-updates-20160229.0/STATUS", "FINISHED")
        touch(self.tmp_dir + "/Fedora-26-updates-testing-20160229.0/STATUS", "FINISHED")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "26", "-updates")
        self.assertEqual(old, self.tmp_dir + "/Fedora-26-updates-20160229.0")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "26", "-updates-testing")
        self.assertEqual(old, self.tmp_dir + "/Fedora-26-updates-testing-20160229.0")

    def test_find_latest_with_two_digit_respin(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160228.n.9/STATUS", "FINISHED")
        touch(self.tmp_dir + "/Fedora-Rawhide-20160228.n.10/STATUS", "FINISHED")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertEqual(old, self.tmp_dir + "/Fedora-Rawhide-20160228.n.10")

    def test_finds_ignores_other_files(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160229.0", "not a compose")
        touch(
            self.tmp_dir + "/Fedora-Rawhide-20160228.0/STATUS/file",
            "also not a compose",
        )
        touch(self.tmp_dir + "/Fedora-24-20160229.0/STATUS", "FINISHED")
        touch(self.tmp_dir + "/Another-Rawhide-20160229.0/STATUS", "FINISHED")
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertIsNone(old)

    def test_search_in_file(self):
        touch(self.tmp_dir + "/file")
        old = util.find_old_compose(self.tmp_dir + "/file", "Fedora", "Rawhide", "")
        self.assertIsNone(old)

    def test_do_not_skip_symlink(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-20160228.n.10/STATUS", "FINISHED")
        os.symlink(
            self.tmp_dir + "/Fedora-Rawhide-20160228.n.10",
            self.tmp_dir + "/Fedora-Rawhide-20160229.n.0",
        )
        old = util.find_old_compose(self.tmp_dir, "Fedora", "Rawhide", "")
        self.assertEqual(old, self.tmp_dir + "/Fedora-Rawhide-20160229.n.0")

    def test_finds_layered_product(self):
        touch(self.tmp_dir + "/Fedora-Rawhide-Base-1-20160229.0/STATUS", "FINISHED")
        old = util.find_old_compose(
            self.tmp_dir,
            "Fedora",
            "Rawhide",
            "",
            base_product_short="Base",
            base_product_version="1",
        )
        self.assertEqual(old, self.tmp_dir + "/Fedora-Rawhide-Base-1-20160229.0")


class TestHelpers(PungiTestCase):
    def test_process_args(self):
        self.assertEqual(util.process_args("--opt=%s", None), [])
        self.assertEqual(util.process_args("--opt=%s", []), [])
        self.assertEqual(
            util.process_args("--opt=%s", ["foo", "bar"]), ["--opt=foo", "--opt=bar"]
        )
        self.assertEqual(util.process_args("--opt=%s", "foo"), ["--opt=foo"])

    def test_makedirs(self):
        util.makedirs(self.topdir + "/foo/bar/baz")
        self.assertTrue(os.path.isdir(self.topdir + "/foo/bar/baz"))

    def test_makedirs_on_existing(self):
        os.makedirs(self.topdir + "/foo/bar/baz")
        try:
            util.makedirs(self.topdir + "/foo/bar/baz")
        except OSError:
            self.fail("makedirs raised exception on existing directory")


class TestLevenshtein(unittest.TestCase):
    def test_edit_dist_empty_str(self):
        self.assertEqual(util.levenshtein("", ""), 0)

    def test_edit_dist_same_str(self):
        self.assertEqual(util.levenshtein("aaa", "aaa"), 0)

    def test_edit_dist_one_change(self):
        self.assertEqual(util.levenshtein("aab", "aaa"), 1)

    def test_edit_dist_different_words(self):
        self.assertEqual(util.levenshtein("kitten", "sitting"), 3)


class TestRecursiveFileList(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_flat_file_list(self):
        """Build a directory containing files and assert they are listed."""
        expected_files = sorted(["file1", "file2", "file3"])
        for expected_file in [os.path.join(self.tmp_dir, f) for f in expected_files]:
            touch(expected_file)

        actual_files = sorted(util.recursive_file_list(self.tmp_dir))
        self.assertEqual(expected_files, actual_files)

    def test_nested_file_list(self):
        """Build a directory containing files and assert they are listed."""
        expected_files = sorted(["file1", "subdir/file2", "sub/subdir/file3"])
        for expected_file in [os.path.join(self.tmp_dir, f) for f in expected_files]:
            touch(expected_file)

        actual_files = sorted(util.recursive_file_list(self.tmp_dir))
        self.assertEqual(expected_files, actual_files)


class TestTempFiles(unittest.TestCase):
    def test_temp_dir_ok(self):
        with util.temp_dir() as tmp:
            self.assertTrue(os.path.isdir(tmp))
        self.assertFalse(os.path.exists(tmp))

    def test_temp_dir_fail(self):
        with self.assertRaises(RuntimeError):
            with util.temp_dir() as tmp:
                self.assertTrue(os.path.isdir(tmp))
                raise RuntimeError("BOOM")
        self.assertFalse(os.path.exists(tmp))

    def test_temp_dir_in_non_existing_dir(self):
        with util.temp_dir() as playground:
            root = os.path.join(playground, "missing")
            with util.temp_dir(dir=root) as tmp:
                self.assertTrue(os.path.isdir(tmp))
            self.assertTrue(os.path.isdir(root))
            self.assertFalse(os.path.exists(tmp))


class TestUnmountCmd(unittest.TestCase):
    def _fakeProc(self, ret, err="", out=""):
        proc = mock.Mock(returncode=ret)
        proc.communicate.return_value = (out, err)
        return proc

    @mock.patch("subprocess.Popen")
    def test_unmount_cmd_success(self, mockPopen):
        cmd = "unmount"
        mockPopen.side_effect = [self._fakeProc(0, "")]
        util.run_unmount_cmd(cmd)
        self.assertEqual(
            mockPopen.call_args_list,
            [
                mock.call(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )
            ],
        )

    @mock.patch("subprocess.Popen")
    def test_unmount_cmd_fail_other_reason(self, mockPopen):
        cmd = "unmount"
        mockPopen.side_effect = [self._fakeProc(1, "It is broken")]
        with self.assertRaises(RuntimeError) as ctx:
            util.run_unmount_cmd(cmd)
        self.assertEqual(
            str(ctx.exception), "Unhandled error when running 'unmount': 'It is broken'"
        )
        self.assertEqual(
            mockPopen.call_args_list,
            [
                mock.call(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )
            ],
        )

    @mock.patch("time.sleep")
    @mock.patch("subprocess.Popen")
    def test_unmount_cmd_fail_then_retry(self, mockPopen, mock_sleep):
        cmd = "unmount"
        mockPopen.side_effect = [
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(0, ""),
        ]
        util.run_unmount_cmd(cmd)
        self.assertEqual(
            mockPopen.call_args_list,
            [
                mock.call(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )
            ]
            * 3,
        )
        self.assertEqual(mock_sleep.call_args_list, [mock.call(0), mock.call(1)])

    @mock.patch("time.sleep")
    @mock.patch("subprocess.Popen")
    def test_unmount_cmd_fail_then_retry_and_fail(self, mockPopen, mock_sleep):
        cmd = "unmount"
        mockPopen.side_effect = [
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(1, "Device or resource busy"),
        ]
        with self.assertRaises(RuntimeError) as ctx:
            util.run_unmount_cmd(cmd, max_retries=3)
        self.assertEqual(
            mockPopen.call_args_list,
            [
                mock.call(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )
            ]
            * 3,
        )
        self.assertEqual(
            mock_sleep.call_args_list, [mock.call(0), mock.call(1), mock.call(2)]
        )
        self.assertEqual(
            str(ctx.exception), "Failed to run 'unmount': Device or resource busy."
        )

    @mock.patch("time.sleep")
    @mock.patch("subprocess.Popen")
    def test_fusermount_fail_then_retry_and_fail_with_debug(
        self, mockPopen, mock_sleep
    ):
        logger = mock.Mock()
        mockPopen.side_effect = [
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(1, "Device or resource busy"),
            self._fakeProc(0, out="list of files"),
            self._fakeProc(0, out="It is very busy"),
            self._fakeProc(1, out="lsof output"),
        ]
        with self.assertRaises(RuntimeError) as ctx:
            util.run_unmount_cmd(
                ["fusermount", "-u", "/path"],
                path="/path",
                max_retries=3,
                logger=logger,
            )
        cmd = ["fusermount", "-u", "/path"]
        expected = [
            mock.call(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
            mock.call(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
            mock.call(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
            mock.call(
                ["ls", "-lA", "/path"],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
            mock.call(
                ["fuser", "-vm", "/path"],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
            mock.call(
                ["lsof", "+D", "/path"],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ),
        ]
        self.assertEqual(mockPopen.call_args_list, expected)
        self.assertEqual(
            mock_sleep.call_args_list, [mock.call(0), mock.call(1), mock.call(2)]
        )
        self.assertEqual(
            str(ctx.exception),
            "Failed to run ['fusermount', '-u', '/path']: Device or resource busy.",
        )
        self.assertEqual(
            logger.mock_calls,
            [
                mock.call.debug(
                    "`%s` exited with %s and following output:\n%s",
                    "ls -lA /path",
                    0,
                    "list of files",
                ),
                mock.call.debug(
                    "`%s` exited with %s and following output:\n%s",
                    "fuser -vm /path",
                    0,
                    "It is very busy",
                ),
                mock.call.debug(
                    "`%s` exited with %s and following output:\n%s",
                    "lsof +D /path",
                    1,
                    "lsof output",
                ),
            ],
        )


class TranslatePathTestCase(unittest.TestCase):
    def test_does_nothing_without_config(self):
        compose = mock.Mock(conf={"translate_paths": []})
        ret = util.translate_path(compose, "/mnt/koji/compose/rawhide/XYZ")
        self.assertEqual(ret, "/mnt/koji/compose/rawhide/XYZ")

    def test_translates_prefix(self):
        compose = mock.Mock(
            conf={"translate_paths": [("/mnt/koji", "http://example.com")]}
        )
        ret = util.translate_path(compose, "/mnt/koji/compose/rawhide/XYZ")
        self.assertEqual(ret, "http://example.com/compose/rawhide/XYZ")

    def test_does_not_translate_not_matching(self):
        compose = mock.Mock(
            conf={"translate_paths": [("/mnt/koji", "http://example.com")]}
        )
        ret = util.translate_path(compose, "/mnt/fedora_koji/compose/rawhide/XYZ")
        self.assertEqual(ret, "/mnt/fedora_koji/compose/rawhide/XYZ")


class GetRepoFuncsTestCase(unittest.TestCase):
    @mock.patch("pungi.compose.ComposeInfo")
    def setUp(self, ci):
        self.tmp_dir = tempfile.mkdtemp()
        conf = {"translate_paths": [(self.tmp_dir, "http://example.com")]}
        ci.return_value.compose.respin = 0
        ci.return_value.compose.id = "RHEL-8.0-20180101.n.0"
        ci.return_value.compose.date = "20160101"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.0"
        ci.return_value.compose.label_major_version = "1"

        compose_dir = os.path.join(self.tmp_dir, ci.return_value.compose.id)
        self.compose = compose.Compose(conf, compose_dir)
        server_variant = mock.Mock(uid="Server", type="variant")
        client_variant = mock.Mock(uid="Client", type="variant")
        self.compose.all_variants = {
            "Server": server_variant,
            "Client": client_variant,
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_get_repo_url_from_normal_url(self):
        url = util.get_repo_url(self.compose, "http://example.com/repo")
        self.assertEqual(url, "http://example.com/repo")

    def test_get_repo_url_from_path(self):
        url = util.get_repo_url(self.compose, os.path.join(self.tmp_dir, "repo"))
        self.assertEqual(url, "http://example.com/repo")

    def test_get_repo_url_from_variant_uid(self):
        url = util.get_repo_url(self.compose, "Server")
        self.assertEqual(
            url, "http://example.com/RHEL-8.0-20180101.n.0/compose/Server/$basearch/os"
        )

    def test_get_repo_url_from_repo_dict(self):
        repo = {"baseurl": "http://example.com/repo"}
        url = util.get_repo_url(self.compose, repo)
        self.assertEqual(url, "http://example.com/repo")

        repo = {"baseurl": "Server"}
        url = util.get_repo_url(self.compose, repo)
        self.assertEqual(
            url, "http://example.com/RHEL-8.0-20180101.n.0/compose/Server/$basearch/os"
        )

    def test_get_repo_urls(self):
        repos = [
            "http://example.com/repo",
            "Server",
            {"baseurl": "Client"},
            {"baseurl": "ftp://example.com/linux/repo"},
        ]

        expect = [
            "http://example.com/repo",
            "http://example.com/RHEL-8.0-20180101.n.0/compose/Server/$basearch/os",
            "http://example.com/RHEL-8.0-20180101.n.0/compose/Client/$basearch/os",
            "ftp://example.com/linux/repo",
        ]

        self.assertEqual(util.get_repo_urls(self.compose, repos), expect)

    def test_get_repo_dict_from_normal_url(self):
        repo_dict = util.get_repo_dict("http://example.com/repo")
        expect = {
            "name": "http:__example.com_repo",
            "baseurl": "http://example.com/repo",
        }
        self.assertEqual(repo_dict, expect)

    def test_get_repo_dict_from_variant_uid(self):
        repo_dict = util.get_repo_dict("Server")  # this repo format is deprecated
        expect = {}
        self.assertEqual(repo_dict, expect)

    def test_get_repo_dict_from_repo_dict(self):
        repo = {"baseurl": "Server"}  # this repo format is deprecated
        expect = {}
        repo_dict = util.get_repo_dict(repo)
        self.assertEqual(repo_dict, expect)

    def test_get_repo_dicts(self):
        repos = [
            "http://example.com/repo",
            "Server",  # this repo format is deprecated (and will not be included into final repo_dict)  # noqa: E501
            {"baseurl": "Client"},  # this repo format is deprecated
            {"baseurl": "ftp://example.com/linux/repo"},
            {"name": "testrepo", "baseurl": "ftp://example.com/linux/repo"},
        ]
        expect = [
            {"name": "http:__example.com_repo", "baseurl": "http://example.com/repo"},
            {
                "name": "ftp:__example.com_linux_repo",
                "baseurl": "ftp://example.com/linux/repo",
            },
            {"name": "testrepo", "baseurl": "ftp://example.com/linux/repo"},
        ]
        repos = util.get_repo_dicts(repos)
        self.assertEqual(repos, expect)


class TestVersionGenerator(unittest.TestCase):
    def setUp(self):
        ci = mock.MagicMock()
        ci.respin = 0
        ci.id = "RHEL-8.0-20180101.0"
        ci.release.version = "8"
        ci.type = "nightly"
        ci.type_suffix = ""
        ci.label = "RC-1.0"
        ci.label_major_version = "1"

        self.compose = mock.MagicMock()
        self.compose.ci_base = ci
        self.compose.compose_respin = 0
        self.compose.compose_date = "20160101"

    def test_unknown_generator(self):
        compose = mock.Mock()
        with self.assertRaises(RuntimeError) as ctx:
            util.version_generator(compose, "!GIMME_VERSION")

        self.assertEqual(
            str(ctx.exception), "Unknown version generator '!GIMME_VERSION'"
        )

    def test_passthrough_value(self):
        compose = mock.Mock()
        self.assertEqual(util.version_generator(compose, "1.2.3"), "1.2.3")

    def test_passthrough_none(self):
        compose = mock.Mock()
        self.assertEqual(util.version_generator(compose, None), None)

    def test_release_from_version_date_respin(self):
        self.assertEqual(
            util.version_generator(self.compose, "!VERSION_FROM_VERSION_DATE_RESPIN"),
            "8.20160101.0",
        )

    def test_release_from_date_respin(self):
        self.assertEqual(
            util.version_generator(self.compose, "!RELEASE_FROM_DATE_RESPIN"),
            "20160101.0",
        )

    def test_version_from_version(self):
        self.assertEqual(
            util.version_generator(self.compose, "!VERSION_FROM_VERSION"),
            "8",
        )


class TestTZOffset(unittest.TestCase):
    @mock.patch("time.daylight", new=False)
    @mock.patch("time.altzone", new=7200)
    @mock.patch("time.timezone", new=3600)
    @mock.patch("time.localtime", new=lambda: mock.Mock(tm_isdst=0))
    def test_zone_without_dst(self):
        self.assertEqual(util.get_tz_offset(), "-01:00")

    @mock.patch("time.daylight", new=True)
    @mock.patch("time.altzone", new=7200)
    @mock.patch("time.timezone", new=3600)
    @mock.patch("time.localtime", new=lambda: mock.Mock(tm_isdst=0))
    def test_with_active_dst(self):
        self.assertEqual(util.get_tz_offset(), "-01:00")

    @mock.patch("time.daylight", new=True)
    @mock.patch("time.altzone", new=-9000)
    @mock.patch("time.timezone", new=-3600)
    @mock.patch("time.localtime", new=lambda: mock.Mock(tm_isdst=1))
    def test_with_inactive_dst(self):
        self.assertEqual(util.get_tz_offset(), "+02:30")

    @mock.patch("time.daylight", new=False)
    @mock.patch("time.altzone", new=0)
    @mock.patch("time.timezone", new=0)
    @mock.patch("time.localtime", new=lambda: mock.Mock(tm_isdst=0))
    def test_utc(self):
        self.assertEqual(util.get_tz_offset(), "+00:00")


class TestParseKojiEvent(PungiTestCase):
    def test_number(self):
        self.assertEqual(util.parse_koji_event("1234"), 1234)

    def test_correct_path(self):
        touch(
            os.path.join(self.topdir, "work/global/koji-event"),
            '{"id": 19769058, "ts": 1527641311.22855}',
        )

        self.assertEqual(util.parse_koji_event(self.topdir), 19769058)

    def test_bad_path(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            util.parse_koji_event(self.topdir)


class TestCopyAll(PungiTestCase):
    def setUp(self):
        super(TestCopyAll, self).setUp()
        self.src = os.path.join(self.topdir, "src")
        self.dst = os.path.join(self.topdir, "dst")
        util.makedirs(self.src)

    def test_preserve_symlink(self):
        touch(os.path.join(self.src, "target"))
        os.symlink("target", os.path.join(self.src, "symlink"))

        util.copy_all(self.src, self.dst)

        self.assertTrue(os.path.isfile(os.path.join(self.dst, "target")))
        self.assertTrue(os.path.islink(os.path.join(self.dst, "symlink")))
        self.assertEqual(os.readlink(os.path.join(self.dst, "symlink")), "target")

    def test_copy_broken_symlink(self):
        os.symlink("broken", os.path.join(self.src, "symlink"))

        util.copy_all(self.src, self.dst)

        self.assertTrue(os.path.islink(os.path.join(self.dst, "symlink")))
        self.assertEqual(os.readlink(os.path.join(self.dst, "symlink")), "broken")


class TestMoveAll(PungiTestCase):
    def setUp(self):
        super(TestMoveAll, self).setUp()
        self.src = os.path.join(self.topdir, "src")
        self.dst = os.path.join(self.topdir, "dst")
        util.makedirs(self.src)

    def test_move_all(self):
        touch(os.path.join(self.src, "target"))
        util.move_all(self.src, self.dst)

        self.assertTrue(os.path.isfile(os.path.join(self.dst, "target")))
        self.assertTrue(os.path.exists(os.path.join(self.src)))
        self.assertFalse(os.path.isfile(os.path.join(self.src, "target")))

    def test_move_all_rm_src_dir(self):
        touch(os.path.join(self.src, "target"))
        util.move_all(self.src, self.dst, rm_src_dir=True)

        self.assertTrue(os.path.isfile(os.path.join(self.dst, "target")))
        self.assertFalse(os.path.exists(os.path.join(self.src)))
        self.assertFalse(os.path.isfile(os.path.join(self.src, "target")))


@mock.patch("six.moves.urllib.request.urlretrieve")
class TestAsLocalFile(PungiTestCase):
    def test_local_file(self, urlretrieve):
        with util.as_local_file("/tmp/foo") as fn:
            self.assertEqual(fn, "/tmp/foo")
        self.assertEqual(urlretrieve.call_args_list, [])

    def test_http(self, urlretrieve):
        url = "http://example.com/repodata/repomd.xml"

        def my_mock(url_):
            self.assertEqual(url, url_)
            self.filename = os.path.join(self.topdir, "my-file")
            touch(self.filename)
            return self.filename, {}

        urlretrieve.side_effect = my_mock

        with util.as_local_file(url) as fn:
            self.assertEqual(fn, self.filename)
            self.assertTrue(os.path.exists(self.filename))
        self.assertFalse(os.path.exists(self.filename))

    def test_file_url(self, urlretrieve):
        with util.as_local_file("file:///tmp/foo") as fn:
            self.assertEqual(fn, "/tmp/foo")
        self.assertEqual(urlretrieve.call_args_list, [])
