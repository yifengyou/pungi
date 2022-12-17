# -*- coding: utf-8 -*-

import os
import six

from pungi.wrappers import repoclosure as rc

from . import helpers


class RepoclosureWrapperTestCase(helpers.BaseTestCase):
    def test_minimal_command(self):
        self.assertEqual(
            rc.get_repoclosure_cmd(), ["/usr/bin/repoclosure", "--tempcache"]
        )

    def test_minimal_dnf_command(self):
        self.assertEqual(rc.get_repoclosure_cmd(backend="dnf"), ["dnf", "repoclosure"])

    def test_unknown_backend(self):
        with self.assertRaises(RuntimeError) as ctx:
            rc.get_repoclosure_cmd(backend="rpm")

        self.assertEqual(str(ctx.exception), "Unknown repoclosure backend: rpm")

    def test_multiple_arches(self):
        self.assertEqual(
            rc.get_repoclosure_cmd(arch=["x86_64", "i686", "noarch"]),
            [
                "/usr/bin/repoclosure",
                "--tempcache",
                "--arch=x86_64",
                "--arch=i686",
                "--arch=noarch",
            ],
        )

    def test_full_command(self):
        repos = {"my-repo": "/mnt/koji/repo"}
        lookaside = {"fedora": "http://kojipkgs.fp.o/repo"}

        cmd = rc.get_repoclosure_cmd(arch="x86_64", repos=repos, lookaside=lookaside)
        self.assertEqual(cmd[0], "/usr/bin/repoclosure")
        six.assertCountEqual(
            self,
            cmd[1:],
            [
                "--tempcache",
                "--arch=x86_64",
                "--repofrompath=my-repo,file:///mnt/koji/repo",
                "--repofrompath=fedora,http://kojipkgs.fp.o/repo",
                "--repoid=my-repo",
                "--lookaside=fedora",
            ],
        )

    def test_full_dnf_command(self):
        repos = {"my-repo": "/mnt/koji/repo"}
        lookaside = {"fedora": "http://kojipkgs.fp.o/repo"}

        cmd = rc.get_repoclosure_cmd(
            backend="dnf", arch="x86_64", repos=repos, lookaside=lookaside
        )
        self.assertEqual(cmd[:2], ["dnf", "repoclosure"])
        six.assertCountEqual(
            self,
            cmd[2:],
            [
                "--arch=x86_64",
                "--forcearch=x86_64",
                "--repofrompath=my-repo,file:///mnt/koji/repo",
                "--repofrompath=fedora,http://kojipkgs.fp.o/repo",
                "--repo=my-repo",
                "--check=my-repo",
                "--repo=fedora",
            ],
        )

    def test_dnf_command_with_multiple_arches(self):
        repos = {"my-repo": "/mnt/koji/repo"}
        lookaside = {"fedora": "http://kojipkgs.fp.o/repo"}

        cmd = rc.get_repoclosure_cmd(
            backend="dnf",
            arch=["x86_64", "i686", "noarch"],
            repos=repos,
            lookaside=lookaside,
        )
        self.assertEqual(cmd[:2], ["dnf", "repoclosure"])
        six.assertCountEqual(
            self,
            cmd[2:],
            [
                "--arch=x86_64",
                "--arch=i686",
                "--arch=noarch",
                "--forcearch=x86_64",
                "--repofrompath=my-repo,file:///mnt/koji/repo",
                "--repofrompath=fedora,http://kojipkgs.fp.o/repo",
                "--repo=my-repo",
                "--check=my-repo",
                "--repo=fedora",
            ],
        )

    def test_expand_repo(self):
        repos = {
            "local": "/mnt/koji/repo",
            "remote": "http://kojipkgs.fp.o/repo",
        }
        cmd = rc.get_repoclosure_cmd(repos=repos)
        self.assertEqual(cmd[0], "/usr/bin/repoclosure")
        six.assertCountEqual(
            self,
            cmd[1:],
            [
                "--tempcache",
                "--repofrompath=local,file:///mnt/koji/repo",
                "--repofrompath=remote,http://kojipkgs.fp.o/repo",
                "--repoid=local",
                "--repoid=remote",
            ],
        )

    def test_expand_lookaside(self):
        repos = {
            "local": "/mnt/koji/repo",
            "remote": "http://kojipkgs.fp.o/repo",
        }
        cmd = rc.get_repoclosure_cmd(lookaside=repos)
        self.assertEqual(cmd[0], "/usr/bin/repoclosure")
        six.assertCountEqual(
            self,
            cmd[1:],
            [
                "--tempcache",
                "--repofrompath=local,file:///mnt/koji/repo",
                "--repofrompath=remote,http://kojipkgs.fp.o/repo",
                "--lookaside=local",
                "--lookaside=remote",
            ],
        )


class FusExtractorTestCase(helpers.PungiTestCase):
    def setUp(self):
        super(FusExtractorTestCase, self).setUp()
        self.input1 = os.path.join(self.topdir, "in1")
        self.input2 = os.path.join(self.topdir, "in2")
        self.output = os.path.join(self.topdir, "out")

    def test_no_match(self):
        helpers.touch(self.input1, "fus-DEBUG: Installing foo\n")
        rc.extract_from_fus_logs([self.input1], self.output)
        self.assertFileContent(self.output, "")

    def test_error(self):
        helpers.touch(
            self.input1,
            "fus-DEBUG: Installing bar\nProblem 1/1\n - nothing provides foo\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            rc.extract_from_fus_logs([self.input1], self.output)

        self.assertIn(self.output, str(ctx.exception))

        self.assertFileContent(self.output, "Problem 1/1\n - nothing provides foo\n")

    def test_errors_in_multiple_files(self):
        helpers.touch(
            self.input1,
            "fus-DEBUG: Installing bar\nProblem 1/1\n - nothing provides foo\n",
        )
        helpers.touch(
            self.input2,
            "fus-DEBUG: Installing baz\nProblem 1/1\n - nothing provides quux\n",
        )
        with self.assertRaises(RuntimeError) as ctx:
            rc.extract_from_fus_logs([self.input1, self.input2], self.output)

        self.assertIn(self.output, str(ctx.exception))

        self.assertFileContent(
            self.output,
            "Problem 1/1\n - nothing provides foo\nProblem 1/1\n - nothing provides quux\n",  # noqa: E501
        )
