#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    import unittest2 as unittest
except ImportError:
    import unittest

import os
import six
import sys
import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pungi import checks
from tests.helpers import load_config, PKGSET_REPOS


class ConfigTestCase(unittest.TestCase):
    def assertValidation(self, cfg, errors=[], warnings=[]):
        actual_errors, actual_warnings = checks.validate(cfg)
        self.assertItemsEqual(errors, actual_errors)
        self.assertEqual(warnings, actual_warnings)


class PkgsetConfigTestCase(ConfigTestCase):

    def test_validate_minimal_pkgset_koji(self):
        cfg = load_config(
            pkgset_source='koji',
        )

        self.assertValidation(cfg)

    def test_validate_minimal_pkgset_repos(self):
        cfg = load_config(
            pkgset_source='repos',
            pkgset_repos={'x86_64': '/first', 'ppc64': '/second'},
        )

        self.assertValidation(cfg)

    def test_pkgset_mismatch_repos(self):
        cfg = load_config(
            pkgset_source='repos',
            pkgset_koji_tag='f25',
            pkgset_koji_inherit=False,
        )

        self.assertValidation(
            cfg,
            [checks.REQUIRES.format('pkgset_source', 'repos', 'pkgset_repos'),
             checks.CONFLICTS.format('pkgset_source', 'repos', 'pkgset_koji_tag'),
             checks.CONFLICTS.format('pkgset_source', 'repos', 'pkgset_koji_inherit')])

    def test_pkgset_mismatch_koji(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_repos={'whatever': '/foo'},
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('pkgset_source', 'koji', 'pkgset_repos')])

    def test_pkgset_multiple_koji_tags(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_koji_tag=['f25', 'f25-extra'],
            pkgset_koji_inherit=False,
        )
        self.assertValidation(cfg)


class ReleaseConfigTestCase(ConfigTestCase):
    def test_set_release_is_layered(self):
        cfg = load_config(
            PKGSET_REPOS,
            release_is_layered=True
        )

        self.assertValidation(
            cfg,
            warnings=[
                "WARNING: Config option release_is_layered was removed and has no effect; remove it. It's layered if there's configuration for base product."])

    def test_only_config_base_product_name(self):
        cfg = load_config(
            PKGSET_REPOS,
            base_product_name='Prod',
        )

        self.assertValidation(
            cfg,
            [checks.REQUIRES.format('base_product_name', 'Prod', 'base_product_short'),
             checks.REQUIRES.format('base_product_name', 'Prod', 'base_product_version'),
             checks.CONFLICTS.format('base_product_short', None, 'base_product_name'),
             checks.CONFLICTS.format('base_product_version', None, 'base_product_name')])

    def test_only_config_base_product_short(self):
        cfg = load_config(
            PKGSET_REPOS,
            base_product_short='bp',
        )

        self.assertValidation(
            cfg,
            [checks.REQUIRES.format('base_product_short', 'bp', 'base_product_name'),
             checks.REQUIRES.format('base_product_short', 'bp', 'base_product_version'),
             checks.CONFLICTS.format('base_product_name', None, 'base_product_short'),
             checks.CONFLICTS.format('base_product_version', None, 'base_product_short')])

    def test_only_config_base_product_version(self):
        cfg = load_config(
            PKGSET_REPOS,
            base_product_version='1.0',
        )

        self.assertValidation(
            cfg,
            [checks.REQUIRES.format('base_product_version', '1.0', 'base_product_name'),
             checks.REQUIRES.format('base_product_version', '1.0', 'base_product_short'),
             checks.CONFLICTS.format('base_product_name', None, 'base_product_version'),
             checks.CONFLICTS.format('base_product_short', None, 'base_product_version')])


class ImageNameConfigTestCase(ConfigTestCase):
    def test_image_name_simple_string(self):
        cfg = load_config(
            PKGSET_REPOS,
            image_name_format="foobar",
        )

        self.assertValidation(cfg, [])

    def test_image_name_variant_mapping(self):
        cfg = load_config(
            PKGSET_REPOS,
            image_name_format={"^Server$": "foobar"},
        )

        self.assertValidation(cfg, [])


class RunrootConfigTestCase(ConfigTestCase):
    def test_set_runroot_true(self):
        cfg = load_config(
            PKGSET_REPOS,
            runroot=True,
        )

        self.assertValidation(
            cfg,
            warnings=["WARNING: Config option runroot was removed and has no effect; remove it. Please specify 'runroot_method' if you want to enable runroot, otherwise run things locally."])

    def test_set_runroot_false(self):
        cfg = load_config(
            PKGSET_REPOS,
            runroot=False,
        )

        self.assertValidation(
            cfg,
            warnings=["WARNING: Config option runroot was removed and has no effect; remove it. Please specify 'runroot_method' if you want to enable runroot, otherwise run things locally."])


class BuildinstallConfigTestCase(ConfigTestCase):
    def test_bootable_without_method(self):
        cfg = load_config(
            PKGSET_REPOS,
            bootable=True,
        )

        self.assertValidation(
            cfg,
            [checks.REQUIRES.format('bootable', 'True', 'buildinstall_method')])

    def test_non_bootable_with_method(self):
        cfg = load_config(
            PKGSET_REPOS,
            bootable=False,
            buildinstall_method='lorax',
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('bootable', 'False', 'buildinstall_method')])

    def test_buildinstall_method_without_bootable(self):
        cfg = load_config(
            PKGSET_REPOS,
            buildinstall_method='lorax',
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('bootable', 'False', 'buildinstall_method')])

    def test_buildinstall_with_lorax_options(self):
        cfg = load_config(
            PKGSET_REPOS,
            bootable=True,
            buildinstall_method='buildinstall',
            lorax_options=[('^Server$', {})]
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('buildinstall_method', 'buildinstall', 'lorax_options')])

    def test_lorax_with_lorax_options(self):
        cfg = load_config(
            PKGSET_REPOS,
            bootable=True,
            buildinstall_method='lorax',
            lorax_options=[]
        )

        self.assertValidation(cfg)

    def test_lorax_options_without_bootable_and_method(self):
        cfg = load_config(
            PKGSET_REPOS,
            lorax_options=[('^Server$', {})],
            buildinstall_kickstart='foo',
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('buildinstall_method', 'None', 'lorax_options'),
             checks.CONFLICTS.format('buildinstall_method', 'None', 'buildinstall_kickstart')])


class CreaterepoConfigTestCase(ConfigTestCase):
    def test_validate_minimal_pkgset_koji(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_koji_tag="f25",
            product_id_allow_missing=True,
        )

        self.assertValidation(
            cfg,
            [checks.CONFLICTS.format('product_id', 'None', 'product_id_allow_missing')])


class GatherConfigTestCase(ConfigTestCase):
    def test_dnf_backend_is_default_on_py3(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_koji_tag='f27',
        )

        with mock.patch('six.PY2', new=False):
            self.assertValidation(cfg, [])
        self.assertEqual(cfg['gather_backend'], 'dnf')

    def test_yum_backend_is_default_on_py2(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_koji_tag='f27',
        )

        with mock.patch('six.PY2', new=True):
            self.assertValidation(cfg, [])
        self.assertEqual(cfg['gather_backend'], 'yum')

    def test_yum_backend_is_rejected_on_py3(self):
        cfg = load_config(
            pkgset_source='koji',
            pkgset_koji_tag='f27',
            gather_backend='yum',
        )

        with mock.patch('six.PY2', new=False):
            self.assertValidation(
                cfg,
                ["Failed validation in gather_backend: 'yum' is not one of ['dnf']"])


class OSBSConfigTestCase(ConfigTestCase):
    def test_validate(self):
        cfg = load_config(
            PKGSET_REPOS,
            osbs={"^Server$": {
                'url': 'http://example.com',
                'target': 'f25-build',
                'git_branch': 'f25',
            }}
        )

        self.assertValidation(cfg)

    def test_validate_bad_conf(self):
        cfg = load_config(
            PKGSET_REPOS,
            osbs='yes please'
        )

        self.assertNotEqual(checks.validate(cfg), ([], []))


class OstreeConfigTestCase(ConfigTestCase):
    def test_validate(self):
        cfg = load_config(
            PKGSET_REPOS,
            ostree=[
                ("^Atomic$", {
                    "x86_64": {
                        "treefile": "fedora-atomic-docker-host.json",
                        "config_url": "https://git.fedorahosted.org/git/fedora-atomic.git",
                        "repo": "Everything",
                        "ostree_repo": "/mnt/koji/compose/atomic/Rawhide/",
                        "version": '!OSTREE_VERSION_FROM_LABEL_DATE_TYPE_RESPIN',
                    }
                })
            ]
        )

        self.assertValidation(cfg)

    def test_validate_bad_conf(self):
        cfg = load_config(
            PKGSET_REPOS,
            ostree='yes please'
        )

        self.assertNotEqual(checks.validate(cfg), ([], []))


class OstreeInstallerConfigTestCase(ConfigTestCase):
    def test_validate(self):
        cfg = load_config(
            PKGSET_REPOS,
            ostree_installer=[
                ("^Atomic$", {
                    "x86_64": {
                        "repo": "Everything",
                        "release": None,
                        "installpkgs": ["fedora-productimg-atomic"],
                        "add_template": ["/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl"],
                        "add_template_var": [
                            "ostree_osname=fedora-atomic",
                            "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                        ],
                        "add_arch_template": ["/spin-kickstarts/atomic-installer/lorax-embed-repo.tmpl"],
                        "rootfs_size": "3",
                        "add_arch_template_var": [
                            "ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",
                            "ostree_osname=fedora-atomic",
                            "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                        ]
                    }
                })
            ]
        )

        self.assertValidation(cfg)

    def test_validate_bad_conf(self):
        cfg = load_config(
            PKGSET_REPOS,
            ostree_installer=[
                ("^Atomic$", {
                    "x86_64": {
                        "repo": "Everything",
                        "release": None,
                        "installpkgs": ["fedora-productimg-atomic"],
                        "add_template": ["/spin-kickstarts/atomic-installer/lorax-configure-repo.tmpl"],
                        "add_template_var": [
                            "ostree_osname=fedora-atomic",
                            "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                        ],
                        "add_arch_template": 15,
                        "add_arch_template_var": [
                            "ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",
                            "ostree_osname=fedora-atomic",
                            "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                        ]
                    }
                })
            ]
        )

        self.assertNotEqual(checks.validate(cfg), ([], []))


class LiveMediaConfigTestCase(ConfigTestCase):
    @mock.patch("pungi.util.resolve_git_url")
    def test_global_config_validation(self, resolve_git_url):
        cfg = load_config(
            PKGSET_REPOS,
            live_media_ksurl='git://example.com/repo.git#HEAD',
            live_media_target='f24',
            live_media_release='RRR',
            live_media_version='Rawhide',
        )

        resolve_git_url.side_effect = lambda x: x.replace("HEAD", "CAFE")

        self.assertValidation(cfg)
        self.assertEqual(cfg["live_media_ksurl"], "git://example.com/repo.git#CAFE")

    def test_global_config_null_release(self):
        cfg = load_config(
            PKGSET_REPOS,
            live_media_release=None,
        )

        self.assertValidation(cfg)


class TestSuggestions(ConfigTestCase):
    def test_with_a_typo(self):
        cfg = load_config(PKGSET_REPOS,
                          product_pid=None)

        self.assertValidation(cfg, [], [checks.UNKNOWN_SUGGEST.format('product_pid', 'product_id')])


class TestRegexValidation(ConfigTestCase):
    def test_incorrect_regular_expression(self):
        cfg = load_config(PKGSET_REPOS,
                          multilib=[('^*$', {'*': []})])

        msg = 'Failed validation in multilib.0.0: incorrect regular expression: nothing to repeat'
        if six.PY3:
            msg += ' at position 1'
        self.assertValidation(cfg, [msg], [])


class RepoclosureTestCase(ConfigTestCase):
    def test_invalid_backend(self):
        cfg = load_config(
            PKGSET_REPOS,
            repoclosure_backend='fnd',  # Intentionally with a typo
        )

        options = ['yum', 'dnf'] if six.PY2 else ['dnf']
        self.assertValidation(
            cfg,
            ["Failed validation in repoclosure_backend: 'fnd' is not one of %s" % options])


class VariantAsLookasideTestCase(ConfigTestCase):
    def test_empty(self):
        variant_as_lookaside = []
        cfg = load_config(
            PKGSET_REPOS,
            variant_as_lookaside=variant_as_lookaside,
        )
        self.assertValidation(cfg)

    def test_basic(self):
        variant_as_lookaside = [
            ("Client", "Base"),
            ("Server", "Client"),
            ("Everything", "Spin"),
        ]
        cfg = load_config(
            PKGSET_REPOS,
            variant_as_lookaside=variant_as_lookaside,
        )
        self.assertValidation(cfg)


class SkipPhasesTestCase(ConfigTestCase):
    def test_empty(self):
        skip_phases = []
        cfg = load_config(
            PKGSET_REPOS,
            skip_phases=skip_phases,
        )
        self.assertValidation(cfg)

    def test_basic(self):
        skip_phases = [
            "buildinstall",
            "gather",
        ]
        cfg = load_config(
            PKGSET_REPOS,
            skip_phases=skip_phases,
        )
        self.assertValidation(cfg)

    def test_bad_phase_name(self):
        skip_phases = [
            "gather",
            "non-existing-phase_name",
        ]
        cfg = load_config(
            PKGSET_REPOS,
            skip_phases=skip_phases,
        )
        self.assertNotEqual(checks.validate(cfg), ([], []))


if __name__ == '__main__':
    unittest.main()
