# -*- coding: utf-8 -*-

import mock

import os

from kobo.shortcuts import force_list

from tests import helpers
from pungi.phases import ostree_installer as ostree
from six.moves import shlex_quote


LOG_PATH = "logs/x86_64/Everything/ostree_installer-1"


class OstreeInstallerPhaseTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.ostree_installer.ThreadPool")
    def test_run(self, ThreadPool):
        cfg = helpers.IterableMock()
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "ostree_installer": [("^Everything$", {"x86_64": cfg})],
                "runroot": True,
                "translate_paths": [(self.topdir + "/work", "http://example.com/work")],
            },
        )

        pool = ThreadPool.return_value

        phase = ostree.OstreeInstallerPhase(
            compose, mock.Mock(), self._make_pkgset_phase(["p1", "p2"])
        )
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.add.call_args_list[0][0][0].baseurls,
            [
                "http://example.com/work/$basearch/repo/p1",
                "http://example.com/work/$basearch/repo/p2",
            ],
        )
        self.assertEqual(
            pool.queue_put.call_args_list,
            [mock.call((compose, compose.variants["Everything"], "x86_64", cfg))],
        )

    @mock.patch("pungi.phases.ostree_installer.ThreadPool")
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = ostree.OstreeInstallerPhase(compose, mock.Mock())
        self.assertTrue(phase.skip())

    def test_validate_conflict_with_buildinstall(self):
        compose = helpers.DummyCompose(
            self.topdir, {"ostree_installer": [("^Server$", {"x86_64": mock.Mock()})]}
        )

        skipmock = mock.Mock()
        skipmock.skip.return_value = False
        phase = ostree.OstreeInstallerPhase(compose, skipmock)
        with self.assertRaises(ValueError) as ctx:
            phase.validate()

        self.assertEqual(
            str(ctx.exception),
            "Can not generate ostree installer for Server.x86_64:"
            " it has buildinstall running already and the files"
            " would clash.",
        )

    def test_validate_buildinstall_skipped(self):
        compose = helpers.DummyCompose(
            self.topdir, {"ostree_installer": [("^Server$", {"x86_64": mock.Mock()})]}
        )

        phase = ostree.OstreeInstallerPhase(compose, mock.Mock(_skipped=True))
        phase.validate()

    def test_validate_overwrite_enabled(self):
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "ostree_installer_overwrite": True,
                "ostree_installer": [("^Server$", {"x86_64": mock.Mock()})],
            },
        )

        phase = ostree.OstreeInstallerPhase(compose, mock.Mock(_skipped=False))
        phase.validate()


class OstreeThreadTest(helpers.PungiTestCase):
    def setUp(self):
        super(OstreeThreadTest, self).setUp()
        self.compose = helpers.DummyCompose(
            self.topdir,
            {
                "release_name": "Fedora",
                "release_version": "Rawhide",
                "koji_profile": "koji",
                "runroot_tag": "rrt",
                "image_volid_formats": ["{release_short}-{variant}-{arch}"],
                "translate_paths": [(self.topdir + "/work", "http://example.com/work")],
            },
        )

    def assertImageAdded(self, compose, ImageCls, iso):
        image = ImageCls.return_value
        self.assertEqual(image.path, "Everything/x86_64/iso/image-name")
        self.assertEqual(image.mtime, 13579)
        self.assertEqual(image.size, 1024)
        self.assertEqual(image.arch, "x86_64")
        self.assertEqual(image.type, "dvd-ostree")
        self.assertEqual(image.format, "iso")
        self.assertEqual(image.disc_number, 1)
        self.assertEqual(image.disc_count, 1)
        self.assertEqual(image.bootable, True)
        self.assertEqual(image.implant_md5, iso.get_implanted_md5.return_value)
        self.assertEqual(
            compose.im.add.mock_calls, [mock.call("Everything", "x86_64", image)]
        )

    def assertRunrootCall(
        self,
        koji,
        sources,
        release,
        isfinal=False,
        extra=[],
        extra_pkgs=[],
        weight=None,
    ):
        lorax_cmd = [
            "lorax",
            "--product=Fedora",
            "--version=Rawhide",
            "--release=%s" % release,
        ]

        for s in force_list(sources):
            lorax_cmd.append(shlex_quote("--source=%s" % s))

        lorax_cmd.append("--variant=Everything")
        lorax_cmd.append("--nomacboot")

        if isfinal:
            lorax_cmd.append("--isfinal")

        lorax_cmd.append("--buildarch=x86_64")
        lorax_cmd.append("--volid=test-Everything-x86_64")

        if extra:
            lorax_cmd.extend(extra)

        outdir = self.topdir + "/work/x86_64/Everything/ostree_installer"
        lorax_cmd.append(outdir)

        self.assertEqual(
            koji.get_runroot_cmd.call_args_list,
            [
                mock.call(
                    "rrt",
                    "x86_64",
                    "rm -rf %s && %s" % (outdir, " ".join(lorax_cmd)),
                    channel=None,
                    mounts=[self.topdir],
                    packages=["pungi", "lorax", "ostree"] + extra_pkgs,
                    use_shell=True,
                    weight=weight,
                    chown_paths=[outdir],
                )
            ],
        )
        self.assertEqual(
            koji.run_runroot_cmd.call_args_list,
            [
                mock.call(
                    koji.get_runroot_cmd.return_value,
                    log_file=os.path.join(self.topdir, LOG_PATH, "runroot.log"),
                )
            ],
        )

    def assertIsoLinked(self, link, get_file_size, get_mtime, final_iso_path):
        self.assertEqual(
            link.call_args_list,
            [
                mock.call(
                    self.topdir
                    + "/work/x86_64/Everything/ostree_installer/images/boot.iso",
                    final_iso_path,
                )
            ],
        )
        self.assertEqual(get_file_size.call_args_list, [mock.call(final_iso_path)])
        self.assertEqual(get_mtime.call_args_list, [mock.call(final_iso_path)])

    def assertAllCopied(self, copy_all):
        self.assertEqual(
            self.compose.get_image_name.call_args_list,
            [
                mock.call(
                    "x86_64", self.compose.variants["Everything"], disc_type="ostree"
                )
            ],
        )
        self.assertTrue(os.path.isdir(self.topdir + "/work/x86_64/Everything/"))
        self.assertFalse(
            os.path.isdir(self.topdir + "/work/x86_64/Everything/ostree_installer")
        )
        self.assertEqual(
            copy_all.call_args_list,
            [
                mock.call(
                    "{0}/work/x86_64/Everything/ostree_installer".format(self.topdir),
                    "{0}/compose/Everything/x86_64/os".format(self.topdir),
                )
            ],
        )

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        self.compose.supported = False
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
            "release": "20160321.n.0",
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        self.assertRunrootCall(
            koji,
            [
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ],
            cfg["release"],
            extra=["--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH)],
        )
        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    @mock.patch("pungi.phases.ostree_installer.move_all")
    def test_run_koji_plugin(
        self,
        move_all,
        KojiWrapper,
        link,
        iso,
        get_file_size,
        get_mtime,
        ImageCls,
        copy_all,
    ):
        self.compose.supported = False
        self.compose.conf["ostree_installer_use_koji_plugin"] = True
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
            "release": "20160321.n.0",
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        args = {
            "product": "Fedora",
            "version": "Rawhide",
            "release": "20160321.n.0",
            "sources": [
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ],
            "variant": "Everything",
            "nomacboot": True,
            "volid": "test-Everything-x86_64",
            "buildarch": "x86_64",
            "installpkgs": None,
            "add-template": [],
            "add-arch-template": [],
            "add-template-var": None,
            "add-arch-template-var": None,
            "rootfs-size": None,
            "isfinal": False,
            "outputdir": self.topdir + "/work/x86_64/Everything/ostree_installer",
        }
        self.assertEqual(
            koji.get_pungi_buildinstall_cmd.mock_calls,
            [
                mock.call(
                    "rrt",
                    "x86_64",
                    args,
                    channel=None,
                    packages=["pungi", "lorax", "ostree"],
                    mounts=[self.topdir],
                    weight=None,
                    chown_uid=os.getuid(),
                )
            ],
        )
        self.assertEqual(
            koji.run_runroot_cmd.mock_calls,
            [
                mock.call(
                    koji.get_pungi_buildinstall_cmd.return_value,
                    log_file=os.path.join(self.topdir, LOG_PATH, "runroot.log"),
                )
            ],
        )
        self.assertEqual(
            move_all.mock_calls,
            [
                mock.call(
                    self.topdir + "/work/x86_64/Everything/ostree_installer/results",
                    self.topdir + "/work/x86_64/Everything/ostree_installer",
                    rm_src_dir=True,
                ),
                mock.call(
                    self.topdir + "/work/x86_64/Everything/ostree_installer/logs",
                    os.path.join(self.topdir, LOG_PATH),
                    rm_src_dir=True,
                ),
            ],
        )

        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_external_source(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "http://example.com/repo/$arch/",
            "release": "20160321.n.0",
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        self.assertRunrootCall(
            koji,
            (
                "http://example.com/repo/x86_64/",
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ),
            cfg["release"],
            isfinal=True,
            extra=["--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH)],
        )
        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_with_repo_key(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "release": "20160321.n.0",
            "repo": [
                "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
                "https://example.com/extra-repo1.repo",
                "https://example.com/extra-repo2.repo",
            ],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        sources = [
            "https://example.com/extra-repo1.repo",
            "https://example.com/extra-repo2.repo",
            "http://example.com/repo/1",
            "http://example.com/work/$basearch/comps_repo_Everything",
        ]

        self.assertRunrootCall(
            koji,
            sources,
            cfg["release"],
            isfinal=True,
            extra=["--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH)],
        )

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_with_multiple_variant_repos(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "release": "20160321.n.0",
            "repo": [
                "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
                "Server",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
                "https://example.com/extra-repo1.repo",
                "https://example.com/extra-repo2.repo",
            ],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        sources = [
            "https://example.com/extra-repo1.repo",
            "https://example.com/extra-repo2.repo",
            "http://example.com/repo/1",
            "http://example.com/work/$basearch/comps_repo_Everything",
        ]

        self.assertRunrootCall(
            koji,
            sources,
            cfg["release"],
            isfinal=True,
            extra=["--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH)],
        )

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_without_comps(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        self.compose.has_comps = False
        pool = mock.Mock()
        cfg = {
            "release": "20160321.n.0",
            "repo": [],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        sources = ["http://example.com/repo/1"]

        self.assertRunrootCall(
            koji,
            sources,
            cfg["release"],
            isfinal=True,
            extra=["--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH)],
        )

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.wrappers.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_fail_with_relative_template_path_but_no_repo(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",
            "release": "20160321.n.0",
            "add_template": ["some-file.txt"],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        with self.assertRaises(RuntimeError) as ctx:
            t.process(
                (self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1
            )

        self.assertIn("template_repo", str(ctx.exception))

    @mock.patch("pungi.wrappers.scm.get_dir_from_scm")
    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_clone_templates(
        self,
        KojiWrapper,
        link,
        iso,
        get_file_size,
        get_mtime,
        ImageCls,
        copy_all,
        get_dir_from_scm,
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
            "release": "20160321.n.0",
            "add_template": ["some_file.txt"],
            "add_arch_template": ["other_file.txt"],
            "template_repo": "git://example.com/templates.git",
            "template_branch": "f24",
            "extra_runroot_pkgs": ["templatedep"],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"
        templ_dir = self.topdir + "/work/x86_64/Everything/lorax_templates"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        self.assertEqual(
            get_dir_from_scm.call_args_list,
            [
                mock.call(
                    {
                        "scm": "git",
                        "repo": "git://example.com/templates.git",
                        "branch": "f24",
                        "dir": ".",
                    },
                    templ_dir,
                    compose=self.compose,
                )
            ],
        )
        self.assertRunrootCall(
            koji,
            [
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ],
            cfg["release"],
            isfinal=True,
            extra=[
                "--add-template=%s/some_file.txt" % templ_dir,
                "--add-arch-template=%s/other_file.txt" % templ_dir,
                "--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH),
            ],
            extra_pkgs=["templatedep"],
        )
        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_with_explicitly_generated_release(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo  # noqa: E501
            "release": "!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN",
            "installpkgs": ["fedora-productimg-atomic"],
            "add_template": [
                "/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl"
            ],
            "add_template_var": [
                "ostree_osname=fedora-atomic",
                "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
            ],
            "add_arch_template": [
                "/spin-kickstarts/atomic-installer/lorax-embed-repo.tmpl"
            ],
            "add_arch_template_var": [
                "ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",  # noqa: E501
                "ostree_osname=fedora-atomic",
                "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
            ],
        }
        self.compose.conf["runroot_weights"] = {"ostree_installer": 123}
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        self.assertRunrootCall(
            koji,
            [
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ],
            "20151203.t.0",
            isfinal=True,
            extra=[
                "--installpkgs=fedora-productimg-atomic",
                "--add-template=/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl",  # noqa: E501
                "--add-arch-template=/spin-kickstarts/atomic-installer/lorax-embed-repo.tmpl",  # noqa: E501
                "--add-template-var=ostree_osname=fedora-atomic",
                "--add-template-var=ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",  # noqa: E501
                "--add-arch-template-var=ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",  # noqa: E501
                "--add-arch-template-var=ostree_osname=fedora-atomic",
                "--add-arch-template-var=ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",  # noqa: E501
                "--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH),
            ],
            weight=123,
        )
        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_run_with_implicit_release(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",  # this variant-type repo is deprecated, in result will be replaced with default repo. # noqa: E501
            "release": None,
            "installpkgs": ["fedora-productimg-atomic"],
            "add_template": [
                "/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl"
            ],
            "add_template_var": [
                "ostree_osname=fedora-atomic",
                "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
            ],
            "add_arch_template": [
                "/spin-kickstarts/atomic-installer/lorax-embed-repo.tmpl"
            ],
            "add_arch_template_var": [
                "ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",  # noqa: E501
                "ostree_osname=fedora-atomic",
                "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
            ],
        }
        self.compose.conf["runroot_weights"] = {"ostree_installer": 123}
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "task_id": 1234,
            "retcode": 0,
            "output": "Foo bar\n",
        }
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        final_iso_path = self.topdir + "/compose/Everything/x86_64/iso/image-name"

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)

        self.assertRunrootCall(
            koji,
            [
                "http://example.com/repo/1",
                "http://example.com/work/$basearch/comps_repo_Everything",
            ],
            "20151203.t.0",
            isfinal=True,
            extra=[
                "--installpkgs=fedora-productimg-atomic",
                "--add-template=/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl",  # noqa: E501
                "--add-arch-template=/spin-kickstarts/atomic-installer/lorax-embed-repo.tmpl",  # noqa: E501
                "--add-template-var=ostree_osname=fedora-atomic",
                "--add-template-var=ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",  # noqa: E501
                "--add-arch-template-var=ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",  # noqa: E501
                "--add-arch-template-var=ostree_osname=fedora-atomic",
                "--add-arch-template-var=ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",  # noqa: E501
                "--logfile=%s/%s/lorax.log" % (self.topdir, LOG_PATH),
            ],
            weight=123,
        )
        self.assertIsoLinked(link, get_file_size, get_mtime, final_iso_path)
        self.assertImageAdded(self.compose, ImageCls, iso)
        self.assertAllCopied(copy_all)

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_fail_crash(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {"repo": "Everything", "release": None, "failable": ["x86_64"]}
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = helpers.boom

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)
        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Ostree installer (variant Everything, arch x86_64) failed, but going on anyway."  # noqa: E501
                ),
                mock.call("BOOM"),
            ]
        )

    @mock.patch("pungi.util.copy_all")
    @mock.patch("productmd.images.Image")
    @mock.patch("pungi.util.get_mtime")
    @mock.patch("pungi.util.get_file_size")
    @mock.patch("pungi.phases.ostree_installer.iso")
    @mock.patch("os.link")
    @mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
    def test_fail_runroot_fail(
        self, KojiWrapper, link, iso, get_file_size, get_mtime, ImageCls, copy_all
    ):
        pool = mock.Mock()
        cfg = {
            "repo": "Everything",
            "release": None,
            "failable": ["*"],
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            "output": "Failed",
            "task_id": 1234,
            "retcode": 1,
        }

        t = ostree.OstreeInstallerThread(pool, ["http://example.com/repo/1"])

        t.process((self.compose, self.compose.variants["Everything"], "x86_64", cfg), 1)
        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Ostree installer (variant Everything, arch x86_64) failed, but going on anyway."  # noqa: E501
                ),
                mock.call(
                    "Runroot task failed: 1234. See %s/%s/runroot.log for more details."
                    % (self.topdir, LOG_PATH)
                ),
            ]
        )
