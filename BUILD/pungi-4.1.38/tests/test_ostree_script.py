#!/usr/bin/env python
# -*- coding: utf-8 -*-


import json
import os
import sys

import mock
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bin'))

from tests import helpers
from pungi import ostree


class OstreeTreeScriptTest(helpers.PungiTestCase):

    def setUp(self):
        super(OstreeTreeScriptTest, self).setUp()
        self.repo = os.path.join(self.topdir, "atomic")

    def _make_dummy_config_dir(self, path):
        helpers.touch(os.path.join(path, 'fedora-atomic-docker-host.json'),
                      json.dumps({'ref': 'fedora-atomic/25/x86_64',
                                  'repos': ['fedora-rawhide', 'fedora-24', 'fedora-23']}))
        helpers.touch(os.path.join(path, 'fedora-atomic-docker-host.yaml'),
                      yaml.dump({'ref': 'fedora-atomic/25/x86_64',
                                 'repos': ['fedora-rawhide', 'fedora-24', 'fedora-23']}))
        helpers.touch(os.path.join(path, 'fedora-rawhide.repo'),
                      '[fedora-rawhide]\nmirrorlist=mirror-mirror-on-the-wall')
        helpers.touch(os.path.join(path, 'fedora-24.repo'),
                      '[fedora-24]\nmetalink=who-is-the-fairest-of-them-all')
        helpers.touch(os.path.join(path, 'fedora-23.repo'),
                      '[fedora-23]\nbaseurl=why-not-zoidberg?')

    def assertCorrectCall(self, mock_run, extra_calls=[], extra_args=[]):
        self.assertItemsEqual(
            mock_run.call_args_list,
            [
                mock.call(
                    [
                        "rpm-ostree",
                        "compose",
                        "tree",
                        "--repo=%s" % self.repo,
                        "--write-commitid-to=%s" % (self.topdir + "/logs/Atomic/commitid.log"),
                        "--touch-if-changed=%s.stamp" % (self.topdir + "/logs/Atomic/commitid.log"),
                    ] + extra_args + [
                        self.topdir + "/fedora-atomic-docker-host.json"
                    ],
                    logfile=self.topdir + "/logs/Atomic/create-ostree-repo.log",
                    show_cmd=True,
                    stdout=True,
                )
            ] + extra_calls
        )

    @mock.patch('kobo.shortcuts.run')
    def test_full_run(self, run):
        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
        ])

        self.assertCorrectCall(run)

    @mock.patch('kobo.shortcuts.run')
    def test_run_on_existing_empty_dir(self, run):
        os.mkdir(self.repo)

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
        ])

        self.assertCorrectCall(run)

    @mock.patch('kobo.shortcuts.run')
    def test_run_on_initialized_repo(self, run):
        helpers.touch(os.path.join(self.repo, 'initialized'))

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
        ])

        self.assertCorrectCall(run)

    @mock.patch('kobo.shortcuts.run')
    def test_update_summary(self, run):
        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
            '--update-summary',
        ])

        self.assertCorrectCall(
            run,
            extra_calls=[
                mock.call(
                    ["ostree", "summary", "-u", "--repo=%s" % self.repo],
                    logfile=self.topdir + "/logs/Atomic/ostree-summary.log",
                    show_cmd=True,
                    stdout=True,
                )
            ]
        )

    @mock.patch('kobo.shortcuts.run')
    def test_versioning_metadata(self, run):
        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
            '--version=24',
        ])

        self.assertCorrectCall(run, extra_args=["--add-metadata-string=version=24"])

    @mock.patch('kobo.shortcuts.run')
    def test_ostree_ref(self, run):
        self._make_dummy_config_dir(self.topdir)
        treefile = os.path.join(self.topdir, 'fedora-atomic-docker-host.json')

        with open(treefile, 'r') as f:
            treefile_content = json.load(f)
        original_repos = treefile_content['repos']
        original_ref = treefile_content['ref']
        replacing_ref = original_ref + '-changed'

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s' % treefile,
            '--ostree-ref=%s' % replacing_ref,
        ])

        with open(treefile, 'r') as f:
            treefile_content = json.load(f)
        new_repos = treefile_content['repos']
        new_ref = treefile_content['ref']

        # ref value in treefile should be overrided with new ref
        self.assertEqual(replacing_ref, new_ref)
        # repos should stay unchanged
        self.assertEqual(original_repos, new_repos)

    @mock.patch('kobo.shortcuts.run')
    def test_run_with_yaml_file(self, run):
        self._make_dummy_config_dir(self.topdir)
        treefile = os.path.join(self.topdir, 'fedora-atomic-docker-host.yaml')

        with open(treefile, 'r') as f:
            # Read initial content from YAML file
            treefile_content = yaml.safe_load(f)
        original_repos = treefile_content['repos']
        original_ref = treefile_content['ref']
        replacing_ref = original_ref + '-changed'

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s' % treefile,
            '--ostree-ref=%s' % replacing_ref,
        ])

        with open(treefile.replace(".yaml", ".json"), 'r') as f:
            # There is now a tweaked JSON file
            treefile_content = json.load(f)
        new_repos = treefile_content['repos']
        new_ref = treefile_content['ref']

        # ref value in treefile should be overrided with new ref
        self.assertEqual(replacing_ref, new_ref)
        # repos should stay unchanged
        self.assertEqual(original_repos, new_repos)

    @mock.patch('kobo.shortcuts.run')
    def test_force_new_commit(self, run):
        helpers.touch(os.path.join(self.repo, 'initialized'))

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s/fedora-atomic-docker-host.json' % self.topdir,
            '--force-new-commit',
        ])

        self.assertCorrectCall(run, extra_args=["--force-nocache"])

    @mock.patch('kobo.shortcuts.run')
    def test_extra_config_with_extra_repos(self, run):
        configdir = os.path.join(self.topdir, 'config')
        self._make_dummy_config_dir(configdir)
        treefile = os.path.join(configdir, 'fedora-atomic-docker-host.json')

        extra_config_file = os.path.join(self.topdir, 'extra_config.json')
        extra_config = {
            "repo": [
                {
                    "name": "server",
                    "baseurl": "http://www.example.com/Server/repo",
                },
                {
                    "name": "optional",
                    "baseurl": "http://example.com/repo/x86_64/optional",
                    "exclude": "systemd-container",
                    "gpgcheck": False
                },
                {
                    "name": "extra",
                    "baseurl": "http://example.com/repo/x86_64/extra",
                }
            ]
        }
        helpers.touch(extra_config_file, json.dumps(extra_config))

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s' % treefile,
            '--extra-config=%s' % extra_config_file,
        ])

        pungi_repo = os.path.join(configdir, "pungi.repo")
        self.assertTrue(os.path.isfile(pungi_repo))
        with open(pungi_repo, 'r') as f:
            content = f.read().strip()
            result_template = (
                "[repo-0]",
                "name=repo-0",
                "baseurl=http://example.com/repo/x86_64/extra",
                "gpgcheck=0",
                "[repo-1]",
                "name=repo-1",
                "baseurl=http://example.com/repo/x86_64/optional",
                "exclude=systemd-container",
                "gpgcheck=0",
                "[repo-2]",
                "name=repo-2",
                "baseurl=http://www.example.com/Server/repo",
                "gpgcheck=0",
            )
            result = '\n'.join(result_template).strip()
            self.assertEqual(content, result)

        treeconf = json.load(open(treefile, 'r'))
        repos = treeconf['repos']
        self.assertEqual(len(repos), 3)
        for name in ("repo-0", "repo-1", "repo-2"):
            self.assertIn(name, repos)

    @mock.patch('kobo.shortcuts.run')
    def test_extra_config_with_keep_original_sources(self, run):

        configdir = os.path.join(self.topdir, 'config')
        self._make_dummy_config_dir(configdir)
        treefile = os.path.join(configdir, 'fedora-atomic-docker-host.json')

        extra_config_file = os.path.join(self.topdir, 'extra_config.json')
        extra_config = {
            "repo": [
                {
                    "name": "server",
                    "baseurl": "http://www.example.com/Server/repo",
                },
                {
                    "name": "optional",
                    "baseurl": "http://example.com/repo/x86_64/optional",
                    "exclude": "systemd-container",
                    "gpgcheck": False
                },
                {
                    "name": "extra",
                    "baseurl": "http://example.com/repo/x86_64/extra",
                }
            ],
            "keep_original_sources": True
        }
        helpers.touch(extra_config_file, json.dumps(extra_config))

        ostree.main([
            'tree',
            '--repo=%s' % self.repo,
            '--log-dir=%s' % os.path.join(self.topdir, 'logs', 'Atomic'),
            '--treefile=%s' % treefile,
            '--extra-config=%s' % extra_config_file,
        ])

        treeconf = json.load(open(treefile, 'r'))
        repos = treeconf['repos']
        self.assertEqual(len(repos), 6)
        for name in ['fedora-rawhide', 'fedora-24', 'fedora-23',
                     'repo-0', 'repo-1', 'repo-2']:
            self.assertIn(name, repos)


class OstreeInstallerScriptTest(helpers.PungiTestCase):
    def setUp(self):
        super(OstreeInstallerScriptTest, self).setUp()
        self.product = "dummyproduct"
        self.version = "1.0"
        self.release = "20160101.t.0"
        self.output = os.path.join(self.topdir, 'output')
        self.logdir = os.path.join(self.topdir, 'logs')
        self.volid = '%s-%s' % (self.product, self.version)
        self.variant = 'dummy'
        self.rootfs_size = None

    @mock.patch('kobo.shortcuts.run')
    def test_run_with_args(self, run):
        args = ['installer',
                '--product=%s' % self.product,
                '--version=%s' % self.version,
                '--release=%s' % self.release,
                '--output=%s' % self.output,
                '--variant=%s' % self.variant,
                '--rootfs-size=%s' % self.rootfs_size,
                '--nomacboot',
                '--isfinal']
        args.append('--source=%s' % 'http://www.example.com/dummy/repo')
        args.append('--installpkgs=dummy-foo')
        args.append('--installpkgs=dummy-bar')
        args.append('--add-template=/path/to/lorax.tmpl')
        args.append('--add-template-var=ostree_osname=dummy')
        args.append('--add-arch-template=/path/to/lorax-embed.tmpl')
        args.append('--add-arch-template-var=ostree_repo=http://www.example.com/ostree')
        ostree.main(args)
        self.maxDiff = None
        self.assertItemsEqual(run.mock_calls,
                              [mock.call(['lorax',
                                          '--product=dummyproduct',
                                          '--version=1.0',
                                          '--release=20160101.t.0',
                                          '--source=http://www.example.com/dummy/repo',
                                          '--variant=dummy',
                                          '--nomacboot',
                                          '--isfinal',
                                          '--installpkgs=dummy-foo',
                                          '--installpkgs=dummy-bar',
                                          '--add-template=/path/to/lorax.tmpl',
                                          '--add-arch-template=/path/to/lorax-embed.tmpl',
                                          '--add-template-var=ostree_osname=dummy',
                                          '--add-arch-template-var=ostree_repo=http://www.example.com/ostree',
                                          '--rootfs-size=None',
                                          self.output])])

    @mock.patch('kobo.shortcuts.run')
    def test_run_with_extra_config_file(self, run):
        extra_config_file = os.path.join(self.topdir, 'extra_config.json')
        helpers.touch(extra_config_file,
                      json.dumps({'repo': 'http://www.example.com/another/repo',
                                  'installpkgs': ['dummy-foo', 'dummy-bar'],
                                  'add_template': ['/path/to/lorax.tmpl'],
                                  'add_template_var': ['ostree_osname=dummy-atomic',
                                                       'ostree_ref=dummy/x86_64/docker'],
                                  'add_arch_template': ['/path/to/lorax-embed.tmpl'],
                                  'add_arch_template_var': ['ostree_osname=dummy-atomic',
                                                            'ostree_repo=http://www.example.com/ostree']}))
        args = ['installer',
                '--product=%s' % self.product,
                '--version=%s' % self.version,
                '--release=%s' % self.release,
                '--output=%s' % self.output,
                '--variant=%s' % self.variant,
                '--rootfs-size=%s' % self.rootfs_size,
                '--nomacboot',
                '--isfinal']
        args.append('--source=%s' % 'http://www.example.com/dummy/repo')
        args.append('--extra-config=%s' % extra_config_file)
        ostree.main(args)
        self.maxDiff = None
        self.assertItemsEqual(run.mock_calls,
                              [mock.call(['lorax',
                                          '--product=dummyproduct',
                                          '--version=1.0',
                                          '--release=20160101.t.0',
                                          '--source=http://www.example.com/dummy/repo',
                                          '--variant=dummy',
                                          '--nomacboot',
                                          '--isfinal',
                                          '--installpkgs=dummy-foo',
                                          '--installpkgs=dummy-bar',
                                          '--add-template=/path/to/lorax.tmpl',
                                          '--add-arch-template=/path/to/lorax-embed.tmpl',
                                          '--add-template-var=ostree_osname=dummy-atomic',
                                          '--add-template-var=ostree_ref=dummy/x86_64/docker',
                                          '--add-arch-template-var=ostree_osname=dummy-atomic',
                                          '--add-arch-template-var=ostree_repo=http://www.example.com/ostree',
                                          '--rootfs-size=None',
                                          self.output])])
