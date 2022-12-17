# -*- coding: utf-8 -*-

import mock

import six

import os

from pungi.phases.image_build import ImageBuildPhase, CreateImageBuildThread
from tests.helpers import DummyCompose, PungiTestCase, boom


class TestImageBuildPhase(PungiTestCase):
    def setUp(self):
        super(TestImageBuildPhase, self).setUp()
        self.maxDiff = None

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": [("docker", "tar.xz")],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "failable": ["x86_64"],
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Client|Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        client_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Client/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Client/$arch/os",
                    "variant": compose.variants["Client"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["x86_64"],
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Client/docker_Fedora-Docker-Base_amd64.cfg",
            "image_dir": self.topdir + "/compose/Client/%(arch)s/images",
            "relative_image_dir": "Client/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        server_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Server/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Server/$arch/os",
                    "variant": compose.variants["Server"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["x86_64"],
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Server/docker_Fedora-Docker-Base_amd64-x86_64.cfg",
            "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
            "relative_image_dir": "Server/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        six.assertCountEqual(
            self,
            phase.pool.queue_put.mock_calls,
            [
                mock.call((compose, client_args, phase.buildinstall_phase)),
                mock.call((compose, server_args, phase.buildinstall_phase)),
            ],
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_phase_global_options(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build_ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "image_build_release": "!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN",
                "image_build_target": "f24",
                "image_build_version": "Rawhide",
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        server_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Server/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Server/$arch/os",
                    "variant": compose.variants["Server"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "release": "20151203.t.0",
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Server/docker_Fedora-Docker-Base_amd64-x86_64.cfg",
            "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
            "relative_image_dir": "Server/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        self.assertEqual(
            phase.pool.queue_put.mock_calls,
            [mock.call((compose, server_args, phase.buildinstall_phase))],
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_phase_missing_version(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": "docker",
                "name": "Fedora-Docker-Base",
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build_ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "image_build_release": "!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN",
                "image_build_target": "f24",
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        server_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Server/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Server/$arch/os",
                    "variant": compose.variants["Server"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "25",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "release": "20151203.t.0",
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Server/docker_Fedora-Docker-Base_amd64-x86_64.cfg",
            "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
            "relative_image_dir": "Server/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        self.assertEqual(
            phase.pool.queue_put.mock_calls,
            [mock.call((compose, server_args, phase.buildinstall_phase))],
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_filter_all_variants(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {
                    "^Client|Server$": [
                        {
                            "image-build": {
                                "format": ["docker"],
                                "name": "Fedora-Docker-Base",
                                "target": "f24",
                                "version": "Rawhide",
                                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                                "kickstart": "fedora-docker-base.ks",
                                "distro": "Fedora-20",
                                "disk_size": 3,
                                "arches": ["non-existing"],
                            }
                        }
                    ]
                },
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertFalse(phase.pool.add.called)
        self.assertFalse(phase.pool.queue_put.called)

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_set_install_tree(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "arches": ["x86_64"],
                "install_tree_from": "Server-optional",
            }
        }

        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )
        compose.setup_optional()

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.assertDictEqual(
            args[0][1],
            {
                "original_image_conf": original_image_conf,
                "image_conf": {
                    "image-build": {
                        "install_tree": self.topdir
                        + "/compose/Server-optional/$arch/os",
                        "kickstart": "fedora-docker-base.ks",
                        "format": ["docker"],
                        "repo": self.topdir + "/compose/Server/$arch/os",
                        "variant": compose.variants["Server"],
                        "target": "f24",
                        "disk_size": 3,
                        "name": "Fedora-Docker-Base",
                        "arches": ["x86_64"],
                        "version": "Rawhide",
                        "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                        "distro": "Fedora-20",
                    }
                },
                "conf_file": self.topdir
                + "/work/image-build/Server/docker_Fedora-Docker-Base_x86_64.cfg",
                "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
                "relative_image_dir": "Server/%(arch)s/images",
                "link_type": "hardlink-or-copy",
                "scratch": False,
            },
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_set_install_tree_from_path(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "arches": ["x86_64"],
                "install_tree_from": "/my/tree",
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
                "translate_paths": [("/my", "http://example.com")],
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.assertDictEqual(
            args[0][1],
            {
                "original_image_conf": original_image_conf,
                "image_conf": {
                    "image-build": {
                        "install_tree": "http://example.com/tree",
                        "kickstart": "fedora-docker-base.ks",
                        "format": ["docker"],
                        "repo": self.topdir + "/compose/Server/$arch/os",
                        "variant": compose.variants["Server"],
                        "target": "f24",
                        "disk_size": 3,
                        "name": "Fedora-Docker-Base",
                        "arches": ["x86_64"],
                        "version": "Rawhide",
                        "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                        "distro": "Fedora-20",
                    }
                },
                "conf_file": self.topdir
                + "/work/image-build/Server/docker_Fedora-Docker-Base_x86_64.cfg",
                "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
                "relative_image_dir": "Server/%(arch)s/images",
                "link_type": "hardlink-or-copy",
                "scratch": False,
            },
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_set_extra_repos(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "arches": ["x86_64"],
                "repo_from": ["Everything", "Server-optional"],
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )
        compose.setup_optional()

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.assertDictEqual(
            args[0][1],
            {
                "original_image_conf": original_image_conf,
                "image_conf": {
                    "image-build": {
                        "install_tree": self.topdir + "/compose/Server/$arch/os",
                        "kickstart": "fedora-docker-base.ks",
                        "format": ["docker"],
                        "repo": ",".join(
                            [
                                self.topdir + "/compose/Everything/$arch/os",
                                self.topdir + "/compose/Server-optional/$arch/os",
                                self.topdir + "/compose/Server/$arch/os",
                            ]
                        ),
                        "variant": compose.variants["Server"],
                        "target": "f24",
                        "disk_size": 3,
                        "name": "Fedora-Docker-Base",
                        "arches": ["x86_64"],
                        "version": "Rawhide",
                        "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                        "distro": "Fedora-20",
                    }
                },
                "conf_file": self.topdir
                + "/work/image-build/Server/docker_Fedora-Docker-Base_x86_64.cfg",
                "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
                "relative_image_dir": "Server/%(arch)s/images",
                "link_type": "hardlink-or-copy",
                "scratch": False,
            },
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_set_external_install_tree(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "arches": ["x86_64"],
                "install_tree_from": "http://example.com/install-tree/",
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.assertDictEqual(
            args[0][1],
            {
                "original_image_conf": original_image_conf,
                "image_conf": {
                    "image-build": {
                        "install_tree": "http://example.com/install-tree/",
                        "kickstart": "fedora-docker-base.ks",
                        "format": ["docker"],
                        "repo": ",".join([self.topdir + "/compose/Server/$arch/os"]),
                        "variant": compose.variants["Server"],
                        "target": "f24",
                        "disk_size": 3,
                        "name": "Fedora-Docker-Base",
                        "arches": ["x86_64"],
                        "version": "Rawhide",
                        "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                        "distro": "Fedora-20",
                    }
                },
                "conf_file": self.topdir
                + "/work/image-build/Server/docker_Fedora-Docker-Base_x86_64.cfg",
                "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
                "relative_image_dir": "Server/%(arch)s/images",
                "link_type": "hardlink-or-copy",
                "scratch": False,
            },
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_create_release(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {
                    "^Server$": [
                        {
                            "image-build": {
                                "format": ["docker"],
                                "name": "Fedora-Docker-Base",
                                "target": "f24",
                                "version": "Rawhide",
                                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                                "kickstart": "fedora-docker-base.ks",
                                "distro": "Fedora-20",
                                "disk_size": 3,
                                "arches": ["x86_64"],
                                "release": None,
                            }
                        }
                    ]
                },
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(
            args[0][1].get("image_conf", {}).get("image-build", {}).get("release"),
            "20151203.t.0",
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_create_release_with_explicit_config(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {
                    "^Server$": [
                        {
                            "image-build": {
                                "format": ["docker"],
                                "name": "Fedora-Docker-Base",
                                "target": "f24",
                                "version": "Rawhide",
                                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                                "kickstart": "fedora-docker-base.ks",
                                "distro": "Fedora-20",
                                "disk_size": 3,
                                "arches": ["x86_64"],
                                "release": "!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN",
                            }
                        }
                    ]
                },
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(
            args[0][1].get("image_conf", {}).get("image-build", {}).get("release"),
            "20151203.t.0",
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_scratch_build(self, ThreadPool):
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {
                    "^Server$": [
                        {
                            "image-build": {
                                "format": ["docker"],
                                "name": "Fedora-Docker-Base",
                                "target": "f24",
                                "version": "Rawhide",
                                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                                "kickstart": "fedora-docker-base.ks",
                                "distro": "Fedora-20",
                                "disk_size": 3,
                                "arches": ["x86_64"],
                                "scratch": True,
                            }
                        }
                    ]
                },
                "koji_profile": "koji",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertTrue(args[0][1].get("scratch"))

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_image_build_optional(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "failable": ["x86_64"],
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server-optional$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )
        compose.setup_optional()

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        server_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Server/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Server-optional/$arch/os",
                    "variant": compose.all_variants["Server-optional"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["x86_64"],
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Server-optional/docker_Fedora-Docker-Base_x86_64.cfg",
            "image_dir": self.topdir + "/compose/Server-optional/%(arch)s/images",
            "relative_image_dir": "Server-optional/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        self.assertEqual(
            phase.pool.queue_put.mock_calls,
            [mock.call((compose, server_args, phase.buildinstall_phase))],
        )

    @mock.patch("pungi.phases.image_build.ThreadPool")
    def test_failable_star(self, ThreadPool):
        original_image_conf = {
            "image-build": {
                "format": ["docker"],
                "name": "Fedora-Docker-Base",
                "target": "f24",
                "version": "Rawhide",
                "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",  # noqa: E501
                "kickstart": "fedora-docker-base.ks",
                "distro": "Fedora-20",
                "disk_size": 3,
                "failable": ["*"],
            }
        }
        compose = DummyCompose(
            self.topdir,
            {
                "image_build": {"^Server$": [original_image_conf]},
                "koji_profile": "koji",
            },
        )
        compose.setup_optional()

        self.assertValidConfig(compose.conf)

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        server_args = {
            "original_image_conf": original_image_conf,
            "image_conf": {
                "image-build": {
                    "install_tree": self.topdir + "/compose/Server/$arch/os",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker"],
                    "repo": self.topdir + "/compose/Server/$arch/os",
                    "variant": compose.all_variants["Server"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["amd64", "x86_64"],
                }
            },
            "conf_file": self.topdir
            + "/work/image-build/Server/docker_Fedora-Docker-Base_amd64-x86_64.cfg",
            "image_dir": self.topdir + "/compose/Server/%(arch)s/images",
            "relative_image_dir": "Server/%(arch)s/images",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        self.assertEqual(
            phase.pool.queue_put.mock_calls,
            [mock.call((compose, server_args, phase.buildinstall_phase))],
        )


class TestCreateImageBuildThread(PungiTestCase):
    @mock.patch("pungi.phases.image_build.get_mtime")
    @mock.patch("pungi.phases.image_build.get_file_size")
    @mock.patch("pungi.phases.image_build.KojiWrapper")
    @mock.patch("pungi.phases.image_build.Linker")
    def test_process(self, Linker, KojiWrapper, get_file_size, get_mtime):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "image_conf": {
                "image-build": {
                    "install_tree": "/ostree/$arch/Client",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker", "qcow2"],
                    "repo": "/ostree/$arch/Client",
                    "variant": compose.variants["Client"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "subvariant": "KDE",
                }
            },
            "conf_file": "amd64,x86_64-Client-Fedora-Docker-Base-docker",
            "image_dir": self.topdir + "/compose/Client/%(arch)s/images",
            "relative_image_dir": "image_dir/Client/%(arch)s",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 0,
            "output": None,
            "task_id": 1234,
        }
        koji_wrapper.get_image_paths.return_value = {
            "amd64": [
                "/koji/task/1235/tdl-amd64.xml",
                "/koji/task/1235/Fedora-Docker-Base-20160103.amd64.qcow2",
                "/koji/task/1235/Fedora-Docker-Base-20160103.amd64.tar.gz",
            ],
            "x86_64": [
                "/koji/task/1235/tdl-x86_64.xml",
                "/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.qcow2",
                "/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.tar.gz",
            ],
        }

        linker = Linker.return_value
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        t = CreateImageBuildThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, None), 1)

        self.assertEqual(
            koji_wrapper.get_image_build_cmd.call_args_list,
            [
                mock.call(
                    cmd["image_conf"],
                    conf_file_dest="amd64,x86_64-Client-Fedora-Docker-Base-docker",
                    scratch=False,
                )
            ],
        )

        self.assertEqual(
            koji_wrapper.run_blocking_cmd.call_args_list,
            [
                mock.call(
                    koji_wrapper.get_image_build_cmd.return_value,
                    log_file=self.topdir
                    + "/logs/amd64-x86_64/imagebuild-Client-KDE-docker-qcow2.amd64-x86_64.log",  # noqa: E501
                )
            ],
        )

        six.assertCountEqual(
            self,
            linker.mock_calls,
            [
                mock.call.link(
                    "/koji/task/1235/Fedora-Docker-Base-20160103.amd64.qcow2",
                    self.topdir
                    + "/compose/Client/amd64/images/Fedora-Docker-Base-20160103.amd64.qcow2",  # noqa: E501
                    link_type="hardlink-or-copy",
                ),
                mock.call.link(
                    "/koji/task/1235/Fedora-Docker-Base-20160103.amd64.tar.gz",
                    self.topdir
                    + "/compose/Client/amd64/images/Fedora-Docker-Base-20160103.amd64.tar.gz",  # noqa: E501
                    link_type="hardlink-or-copy",
                ),
                mock.call.link(
                    "/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.qcow2",
                    self.topdir
                    + "/compose/Client/x86_64/images/Fedora-Docker-Base-20160103.x86_64.qcow2",  # noqa: E501
                    link_type="hardlink-or-copy",
                ),
                mock.call.link(
                    "/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.tar.gz",
                    self.topdir
                    + "/compose/Client/x86_64/images/Fedora-Docker-Base-20160103.x86_64.tar.gz",  # noqa: E501
                    link_type="hardlink-or-copy",
                ),
            ],
        )

        image_relative_paths = {
            "image_dir/Client/amd64/Fedora-Docker-Base-20160103.amd64.qcow2": {
                "format": "qcow2",
                "type": "qcow2",
                "arch": "amd64",
            },
            "image_dir/Client/amd64/Fedora-Docker-Base-20160103.amd64.tar.gz": {
                "format": "tar.gz",
                "type": "docker",
                "arch": "amd64",
            },
            "image_dir/Client/x86_64/Fedora-Docker-Base-20160103.x86_64.qcow2": {
                "format": "qcow2",
                "type": "qcow2",
                "arch": "x86_64",
            },
            "image_dir/Client/x86_64/Fedora-Docker-Base-20160103.x86_64.tar.gz": {
                "format": "tar.gz",
                "type": "docker",
                "arch": "x86_64",
            },
        }

        # Assert there are 4 images added to manifest and the arguments are sane
        self.assertEqual(len(compose.im.add.call_args_list), 4)
        for call in compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Client")
            self.assertIn(kwargs["arch"], ("amd64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertIn(image.path, image_relative_paths)
            data = image_relative_paths.pop(image.path)
            self.assertEqual(data["format"], image.format)
            self.assertEqual(data["type"], image.type)
            self.assertEqual("KDE", image.subvariant)

        self.assertTrue(os.path.isdir(self.topdir + "/compose/Client/amd64/images"))
        self.assertTrue(os.path.isdir(self.topdir + "/compose/Client/x86_64/images"))

    @mock.patch("pungi.phases.image_build.KojiWrapper")
    @mock.patch("pungi.phases.image_build.Linker")
    def test_process_handle_fail(self, Linker, KojiWrapper):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "image_conf": {
                "image-build": {
                    "install_tree": "/ostree/$arch/Client",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker", "qcow2"],
                    "repo": "/ostree/$arch/Client",
                    "variant": compose.variants["Client"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["amd64", "x86_64"],
                }
            },
            "conf_file": "amd64,x86_64-Client-Fedora-Docker-Base-docker",
            "image_dir": "/image_dir/Client/%(arch)s",
            "relative_image_dir": "image_dir/Client/%(arch)s",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }
        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 1,
            "output": None,
            "task_id": 1234,
        }

        t = CreateImageBuildThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, None), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Image build (variant Client, arch *, subvariant Client) failed, but going on anyway."  # noqa: E501
                ),
                mock.call(
                    "ImageBuild task failed: 1234. See %s for more details."
                    % (
                        os.path.join(
                            self.topdir,
                            "logs/amd64-x86_64/imagebuild-Client-Client-docker-qcow2.amd64-x86_64.log",  # noqa: E501
                        )
                    )
                ),
            ]
        )

    @mock.patch("pungi.phases.image_build.KojiWrapper")
    @mock.patch("pungi.phases.image_build.Linker")
    def test_process_handle_exception(self, Linker, KojiWrapper):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "image_conf": {
                "image-build": {
                    "install_tree": "/ostree/$arch/Client",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker", "qcow2"],
                    "repo": "/ostree/$arch/Client",
                    "variant": compose.variants["Client"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["amd64", "x86_64"],
                }
            },
            "conf_file": "amd64,x86_64-Client-Fedora-Docker-Base-docker",
            "image_dir": "/image_dir/Client/%(arch)s",
            "relative_image_dir": "image_dir/Client/%(arch)s",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.side_effect = boom

        t = CreateImageBuildThread(pool)
        with mock.patch("time.sleep"):
            t.process((compose, cmd, None), 1)

        pool._logger.error.assert_has_calls(
            [
                mock.call(
                    "[FAIL] Image build (variant Client, arch *, subvariant Client) failed, but going on anyway."  # noqa: E501
                ),
                mock.call("BOOM"),
            ]
        )

    @mock.patch("pungi.phases.image_build.KojiWrapper")
    @mock.patch("pungi.phases.image_build.Linker")
    def test_process_handle_fail_only_one_optional(self, Linker, KojiWrapper):
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        pool = mock.Mock()
        cmd = {
            "image_conf": {
                "image-build": {
                    "install_tree": "/ostree/$arch/Client",
                    "kickstart": "fedora-docker-base.ks",
                    "format": ["docker", "qcow2"],
                    "repo": "/ostree/$arch/Client",
                    "variant": compose.variants["Client"],
                    "target": "f24",
                    "disk_size": 3,
                    "name": "Fedora-Docker-Base",
                    "arches": ["amd64", "x86_64"],
                    "version": "Rawhide",
                    "ksurl": "git://git.fedorahosted.org/git/spin-kickstarts.git",
                    "distro": "Fedora-20",
                    "can_fail": ["amd64"],
                }
            },
            "conf_file": "amd64,x86_64-Client-Fedora-Docker-Base-docker",
            "image_dir": "/image_dir/Client/%(arch)s",
            "relative_image_dir": "image_dir/Client/%(arch)s",
            "link_type": "hardlink-or-copy",
            "scratch": False,
        }

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 1,
            "output": None,
            "task_id": 1234,
        }

        t = CreateImageBuildThread(pool)
        with self.assertRaises(RuntimeError):
            with mock.patch("time.sleep"):
                t.process((compose, cmd, None), 1)
