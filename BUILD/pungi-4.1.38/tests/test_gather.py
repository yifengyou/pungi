# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest


import os
import tempfile
import shutil
import six
import sys
import logging

from six.moves import cStringIO

HERE = os.path.dirname(__file__)
BINDIR = (os.path.join(HERE, '..', 'bin'))
sys.path.insert(0, os.path.join(HERE, '..'))
os.environ['PATH'] = '%s:%s' % (BINDIR, os.environ['PATH'])

from pungi.wrappers.pungi import PungiWrapper
try:
    from pungi.dnf_wrapper import DnfWrapper, Conf
    from pungi.gather_dnf import Gather, GatherOptions, PkgFlag
    HAS_DNF = True
except ImportError:
    HAS_DNF = False

if six.PY2:
    HAS_YUM = True
else:
    HAS_YUM = False


def convert_pkg_map(data):
    """
    Go through the mapping, extract only paths and convert them to just
    basenames.
    """
    result = {}
    for pkg_type in data:
        result[pkg_type] = sorted(set([os.path.basename(pkg['path'])
                                       for pkg in data[pkg_type]]))
    return result


class DepsolvingBase(object):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_compose_")
        self.repo = os.path.join(os.path.dirname(__file__), "fixtures/repos/repo")
        self.lookaside = os.path.join(os.path.dirname(__file__),
                                      "fixtures/repos/repo-krb5-lookaside")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_kernel(self):
        packages = [
            "dummy-kernel",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",  # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_kernel_fulltree(self):
        packages = [
            "dummy-kernel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",          # Important
            "dummy-kernel-headers-3.1.0-1.x86_64.rpm",
            "dummy-kernel-doc-3.1.0-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_kernel_fulltree_excludes(self):
        packages = [
            "dummy-kernel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True,
                          fulltree_excludes=['dummy-kernel'])

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_kernel_doc_fulltree(self):
        packages = [
            "dummy-kernel-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",          # Important
            "dummy-kernel-headers-3.1.0-1.x86_64.rpm",
            "dummy-kernel-doc-3.1.0-1.noarch.rpm",      # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash_noarch_pulls_64bit(self):
        packages = [
            "dummy-glibc.+",
            "dummy-bash-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertNotIn("dummy-bash-4.2.37-6.ppc.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.ppc64.rpm",            # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",       # Important
            "dummy-filesystem-4.2.37-6.ppc64.rpm",
            "dummy-glibc-2.14-5.ppc.rpm",
            "dummy-glibc-2.14-5.ppc64.rpm",
            "dummy-glibc-common-2.14-5.ppc64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.ppc64.rpm",
            "dummy-bash-debugsource-4.2.37-6.ppc64.rpm",
            "dummy-glibc-debuginfo-2.14-5.ppc.rpm",
            "dummy-glibc-debuginfo-2.14-5.ppc64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.ppc.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.ppc64.rpm",
        ])

    def test_foo32_doc_fulltree(self):
        packages = [
            "dummy-foo32-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-foo32-1-1.i686.rpm",                 # Important
            "dummy-foo32-doc-1-1.noarch.rpm",           # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-foo32-1-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash_exclude_debuginfo(self):
        packages = [
            'dummy-bash',
            '-dummy-bash-debuginfo',
            '-dummy-bash-debugsource',
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_exclude_debuginfo(self):
        packages = [
            'dummy-bash.+',
            '-dummy-bash-debuginfo',
            '-dummy-bash-debugsource',
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_s390x(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none", arch="s390x")

        self.assertNotIn("dummy-bash-4.2.37-5.s390.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.s390x.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.s390.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.s390x.rpm",            # Important
            "dummy-filesystem-4.2.37-6.s390x.rpm",
            "dummy-glibc-2.14-5.s390x.rpm",
            "dummy-glibc-common-2.14-5.s390x.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.s390x.rpm",
            "dummy-bash-debugsource-4.2.37-6.s390x.rpm",
            "dummy-glibc-debuginfo-2.14-5.s390x.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.s390x.rpm",
        ])

    def test_bash_greedy(self):
        # we want only the latest package version
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_older(self):
        packages = [
            "dummy-bash-4.2.37-5",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-5.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_system_release(self):
        packages = [
            "dummy-filesystem",
            "system-release",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-release-client-workstation-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-workstation-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-server-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-server-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-notes-1.2-1.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_system_release_greedy(self):
        packages = [
            "system-release",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertNotIn("dummy-release-notes-1.2-1.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-client-1.0.0-1.i686.rpm",                # Important
            "dummy-release-client-1.0.0-1.x86_64.rpm",              # Important
            "dummy-release-client-workstation-1.0.0-1.i686.rpm",    # Important
            "dummy-release-client-workstation-1.0.0-1.x86_64.rpm",  # Important
            "dummy-release-server-1.0.0-1.i686.rpm",                # Important
            "dummy-release-server-1.0.0-1.x86_64.rpm",              # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-client-1.0.0-1.src.rpm",
            "dummy-release-client-workstation-1.0.0-1.src.rpm",
            "dummy-release-server-1.0.0-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_smtpdaemon(self):
        packages = [
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-postfix-2.9.2-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.x86_64.rpm",             # Important
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_sendmail(self):
        packages = [
            "dummy-vacation",
            "dummy-sendmail",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-postfix-2.9.2-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-postfix-2.9.2-2.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-sendmail-8.14.5-12.x86_64.rpm",          # Important
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_greedy_all(self):
        packages = [
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.i686.rpm",               # Important
            "dummy-postfix-2.9.2-2.x86_64.rpm",             # Important
            "dummy-sendmail-8.14.5-12.i686.rpm",            # Important
            "dummy-sendmail-8.14.5-12.x86_64.rpm",          # Important
            "dummy-vacation-1.2.7.1-1.i686.rpm",
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.i686.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.i686.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.i686.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_greedy_all_explicit_postfix(self):
        # Postfix provides smtpdaemon, but we still want sendmail in because we
        # are greedy.
        packages = [
            "dummy-postfix",
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.i686.rpm",
            "dummy-postfix-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-8.14.5-12.i686.rpm",
            "dummy-sendmail-8.14.5-12.x86_64.rpm",
            "dummy-vacation-1.2.7.1-1.i686.rpm",
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.i686.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.i686.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.i686.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_greedy_all_explicit_sendmail(self):
        # Same as above, but the other way around.
        packages = [
            "dummy-sendmail",
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.i686.rpm",
            "dummy-postfix-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-8.14.5-12.i686.rpm",
            "dummy-sendmail-8.14.5-12.x86_64.rpm",
            "dummy-vacation-1.2.7.1-1.i686.rpm",
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.i686.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.i686.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.i686.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_firefox(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("Dummy-firefox-16.0.1-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", selfhosting=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",          # Important
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",   # Important
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting_with_krb5_lookaside(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, lookaside=self.lookaside, selfhosting=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-debuginfo-1.10-5.x86_64.rpm", pkg_map["debuginfo"])
        self.assertNotIn("dummy-krb5-1.10-5.src.rpm", pkg_map["srpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_old_dep_in_lookaside_is_not_pulled_in(self):
        # main repo:
        #   dummy-cockpit-docker-141-1 depends on dummy-cockpit-system
        #   dummy-cockpit-system-141-1
        # lookaside:
        #   dummy-cockpit-system-138-1
        #
        # By default newer version should be pulled in.
        self.repo = os.path.join(os.path.dirname(__file__), "fixtures/repos/cockpit")
        self.lookaside = os.path.join(os.path.dirname(__file__),
                                      "fixtures/repos/cockpit-lookaside")
        packages = [
            'dummy-cockpit-docker',
        ]
        pkg_map = self.go(packages, None, lookaside=self.lookaside)

        self.assertEqual(self.broken_deps, {})
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-cockpit-docker-141-1.noarch.rpm",
            "dummy-cockpit-system-141-1.noarch.rpm",
        ])

    def test_does_not_exclude_from_lookaside(self):
        # main repo:
        #   dummy-cockpit-docker-141-1 depends on dummy-cockpit-system
        #   dummy-cockpit-system-141-1
        # lookaside:
        #   dummy-cockpit-system-138-1
        #
        # The -system package is excluded and the dependency should be
        # satisfied by the older version in lookaside. No broken dependencies
        # should be reported.
        self.repo = os.path.join(os.path.dirname(__file__), "fixtures/repos/cockpit")
        self.lookaside = os.path.join(os.path.dirname(__file__),
                                      "fixtures/repos/cockpit-lookaside")
        packages = [
            'dummy-cockpit-docker',
            '-dummy-cockpit-system',
        ]
        pkg_map = self.go(packages, None, lookaside=self.lookaside)

        self.assertEqual(self.broken_deps, {})
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-cockpit-docker-141-1.noarch.rpm",
        ])

    def test_firefox_fulltree(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting_fulltree(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", selfhosting=True, fulltree=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "dummy-krb5-workstation-1.10-5.x86_64.rpm",     # Important
            "dummy-nscd-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_krb5_fulltree(self):
        packages = [
            "dummy-krb5",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "dummy-krb5-workstation-1.10-5.x86_64.rpm",     # Important
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
        ])

    def test_bash_multilib(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        # 'dummy-bash' req already satisfied by bash.i686
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_wildcard_with_multilib_blacklist(self):
        packages = [
            "dummy-glibc*",
        ]
        pkg_map = self.go(packages, None, multilib_blacklist=['dummy-glibc*'])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_exclude(self):
        # test if excluding a package really works
        # NOTE: dummy-bash-doc would pull x86_64 bash in (we want noarch pulling 64bit deps in composes)
        packages = [
            "dummy-bash.+",
            "-dummy-bash-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-doc-4.2.37-6.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_exclude_source(self):
        packages = [
            "dummy-bash.+",
            "-dummy-bash.src",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-bash-4.2.37-6.src.rpm", pkg_map["srpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_greedy(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.i686.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    @unittest.skip('This test is broken')
    def test_bash_multilib_nogreedy(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            # "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            # "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            # "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            # "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_filter_greedy(self):
        packages = [
            "dummy-bash",
            "-dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.i686.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_filter_greedy(self):
        packages = [
            "dummy-filesystem",
            "dummy-bash.+",
            "-dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_ipw3945_kmod(self):
        # every package name is different
        packages = [
            "dummy-kmod-ipw3945",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kmod-ipw3945-1.2.0-4.20.x86_64.rpm",         # Important
            "dummy-kmod-ipw3945-xen-1.2.0-4.20.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-ipw3945-kmod-1.2.0-4.20.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-ipw3945-kmod-debuginfo-1.2.0-4.20.x86_64.rpm",
        ])

    def test_multilib_method_devel_runtime(self):
        packages = [
            "dummy-lvm2-devel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False,
                          multilib_methods=["devel", "runtime"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-2.02.84-4.x86_64.rpm",
            "dummy-lvm2-devel-2.02.84-4.i686.rpm",          # Important
            "dummy-lvm2-devel-2.02.84-4.x86_64.rpm",        # Important
            "dummy-lvm2-libs-2.02.84-4.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-lvm2-2.02.84-4.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.i686.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.x86_64.rpm",
        ])

    def test_selinux_policy_base(self):
        packages = [
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",           # Important
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",   # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_base_greedy_build(self):
        packages = [
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="ppc64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",               # Important
            "dummy-selinux-policy-minimal-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",       # Important
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm"
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_base_existing_provides(self):
        packages = [
            "dummy-selinux-policy-targeted",
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertNotIn("dummy-selinux-policy-mls-3.10.0-121.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",               # Important
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm",  # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_doc_fulltree(self):
        packages = [
            "dummy-selinux-policy-doc"
        ]
        pkg_map = self.go(packages, None, fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-selinux-policy-doc-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-minimal-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-selinux-policy-3.10.0-121.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_AdobeReader_enu_nosrc(self):
        packages = [
            "dummy-AdobeReader_enu",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-AdobeReader_enu-9.5.1-1.i486.rpm",       # Important
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-AdobeReader_enu-9.5.1-1.nosrc.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_imsettings(self):
        packages = [
            "dummy-imsettings",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="x86_64")

        self.assertNotIn("dummy-imsettings-gnome-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers qt over gnome (shorter name)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-qt-1.2.9-1.x86_64.rpm",       # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop(self):
        packages = [
            "dummy-imsettings",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, arch="x86_64")

        self.assertNotIn("dummy-imsettings-qt-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers gnome over qt (condrequires in @basic-desktop)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-gnome-1.2.9-1.x86_64.rpm",    # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop_nodeps(self):
        packages = [
            "dummy-imsettings",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, nodeps=True,
                          arch="x86_64")

        self.assertNotIn("dummy-imsettings-gnome-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-imsettings-qt-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers gnome over qt (condrequires in @basic-desktop)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop_and_qt(self):
        packages = [
            "dummy-imsettings",
            "dummy-imsettings-qt",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, arch="x86_64")

        # prefers gnome over qt (condrequires in @basic-desktop)
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-gnome-1.2.9-1.x86_64.rpm",    # Important
            "dummy-imsettings-qt-1.2.9-1.x86_64.rpm",       # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash_nodeps(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none", nodeps=True)

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
        ])

    def test_bash_fulltree_nodeps(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, nodeps=True, fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-bash-debugsource-4.2.37-6.x86_64.rpm",
        ])

    def test_lookaside_empty(self):
        # if the input repo and lookaside repo are the same, output must be empty
        packages = [
            "*",
        ]
        pkg_map = self.go(packages, None, lookaside=self.repo,
                          nodeps=True, fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [])
        self.assertItemsEqual(pkg_map["srpm"], [])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_exclude_wildcards(self):
        packages = [
            "dummy-bash",
            "-dummy-bas*",
            "dummy-glibc",
        ]
        pkg_map = self.go(packages, None,
                          greedy="none", nodeps=True, fulltree=True)

        # neither dummy-bash or dummy-basesystem is pulled in
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_atlas_greedy_none(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build(self):
        packages = [
            "dummy-atlas",
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build_multilib_devel(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="build", multilib_methods=["devel", "runtime"],
                          fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build_multilib_devel_32bit(self):
        packages = [
            "dummy-atlas-devel.+",
        ]
        pkg_map = self.go(packages, None, greedy="build", multilib_methods=["devel", "runtime"],
                          fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_all(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.i686.rpm",
            "dummy-atlas-3dnow-3.8.4-7.i686.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-sse-3.8.4-7.i686.rpm",
            "dummy-atlas-sse2-3.8.4-7.i686.rpm",
            "dummy-atlas-sse3-3.8.4-7.i686.rpm",

            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_skype(self):
        packages = [
            "dummy-skype",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-skype-4.2.0.13-1.i586.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
        ])
        # no SRPM for skype
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
        ])

    def test_prepopulate(self):
        packages = [
            "dummy-glibc",
        ]
        prepopulate = [
            "dummy-bash.i686",
            "dummy-lvm2.x86_64",
        ]

        pkg_map = self.go(packages, None, prepopulate=prepopulate)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-2.02.84-4.x86_64.rpm",
            "dummy-lvm2-libs-2.02.84-4.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-lvm2-2.02.84-4.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debugsource-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.x86_64.rpm",
        ])

    def test_langpacks(self):
        packages = [
            "dummy-release-notes",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-notes-1.2-1.noarch.rpm",
            "dummy-release-notes-cs-CZ-1.2-1.noarch.rpm",
            "dummy-release-notes-en-US-1.2-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-notes-1.2-1.src.rpm",
            "dummy-release-notes-cs-CZ-1.2-1.src.rpm",
            "dummy-release-notes-en-US-1.2-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_multilib_whitelist(self):
        # whitelist must work regardless if multilib_method is specified or not
        packages = [
            "dummy-glibc",
        ]

        pkg_map = self.go(packages, None, multilib_whitelist=["dummy-glibc"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_noarch_debuginfo(self):
        packages = [
            "dummy-mingw32-qt5-qtbase",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-mingw32-qt5-qtbase-5.6.0-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-mingw-qt5-qtbase-5.6.0-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-mingw32-qt5-qtbase-debuginfo-5.6.0-1.noarch.rpm",
        ])

    def test_input_by_wildcard(self):
        packages = [
            "dummy-release-notes-*",
            # Yum matches globs against NVR, DNF against names; let's exclude
            # the extra package to unify the behaviour.
            "-dummy-release-notes",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-notes-cs-CZ-1.2-1.noarch.rpm",
            "dummy-release-notes-en-US-1.2-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-notes-cs-CZ-1.2-1.src.rpm",
            "dummy-release-notes-en-US-1.2-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_requires_pre_post(self):
        packages = [
            "dummy-perl"
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-perl-1.0.0-1.x86_64.rpm",
            "dummy-perl-macros-1.0.0-1.x86_64.rpm",     # Requires(pre)
            "dummy-perl-utils-1.0.0-1.x86_64.rpm",      # Requires(post)
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-perl-1.0.0-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_multilib_exclude_pattern_does_not_match_noarch(self):
        packages = [
            'dummy-release-notes-en-US',
            '-dummy-release-notes-en*.+',
        ]

        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-notes-en-US-1.2-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-notes-en-US-1.2-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
        ])


@unittest.skipUnless(HAS_YUM, 'YUM only available on Python 2')
class PungiYumDepsolvingTestCase(DepsolvingBase, unittest.TestCase):

    def setUp(self):
        super(PungiYumDepsolvingTestCase, self).setUp()
        self.ks = os.path.join(self.tmp_dir, "ks")
        self.out = os.path.join(self.tmp_dir, "out")
        self.cwd = os.path.join(self.tmp_dir, "cwd")
        os.mkdir(self.cwd)
        self.old_cwd = os.getcwd()
        os.chdir(self.cwd)

        logger = logging.getLogger('Pungi')
        if not logger.handlers:
            formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            console.setLevel(logging.INFO)
            logger.addHandler(console)

    def tearDown(self):
        os.chdir(self.old_cwd)
        super(PungiYumDepsolvingTestCase, self).tearDown()

    def go(self, packages, groups, lookaside=None, prepopulate=None,
           fulltree_excludes=None, multilib_blacklist=None,
           multilib_whitelist=None, **kwargs):
        """
        Write a kickstart with given packages and groups, then run the
        depsolving and parse the output.
        """
        p = PungiWrapper()
        repos = {"repo": self.repo}
        if lookaside:
            repos['lookaside'] = lookaside
            kwargs['lookaside_repos'] = ['lookaside']
        p.write_kickstart(self.ks, repos, groups, packages, prepopulate=prepopulate,
                          multilib_whitelist=multilib_whitelist,
                          multilib_blacklist=multilib_blacklist,
                          fulltree_excludes=fulltree_excludes)
        kwargs.setdefault('cache_dir', self.tmp_dir)
        # Unless the test specifies an arch, we need to default to x86_64.
        # Otherwise the arch of current machine will be used, which will cause
        # failure most of the time.
        kwargs.setdefault('arch', 'x86_64')

        p.run_pungi(self.ks, self.tmp_dir, 'DP', **kwargs)
        with open(self.out, "r") as f:
            pkg_map, self.broken_deps, _ = p.parse_log(f)
        return convert_pkg_map(pkg_map)


def convert_dnf_packages(pkgs, flags):
    convert_table = {
        # Hawkey returns nosrc package as src
        'dummy-AdobeReader_enu-9.5.1-1.src': 'dummy-AdobeReader_enu-9.5.1-1.nosrc',
    }
    result = set()
    for p in pkgs:
        name = str(p)
        name = convert_table.get(name, name)
        if PkgFlag.lookaside in flags.get(p, []):
            # Package is coming from lookaside repo, we don't want those in
            # output.
            continue
        result.add(name + '.rpm')
    return sorted(result)


@unittest.skipUnless(HAS_DNF, 'Dependencies are not available')
class DNFDepsolvingTestCase(DepsolvingBase, unittest.TestCase):
    def setUp(self):
        super(DNFDepsolvingTestCase, self).setUp()
        self.cachedir = os.path.join(self.tmp_dir, 'pungi_dnf_cache')
        self.get_langpacks = False

        logger = logging.getLogger('gather_dnf')
        if not logger.handlers:
            formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            console.setLevel(logging.INFO)
            logger.addHandler(console)

        self.maxDiff = None

    def go(self, packages, groups, lookaside=None, **kwargs):
        arch = kwargs.pop('arch', 'x86_64')
        if 'greedy' in kwargs:
            kwargs['greedy_method'] = kwargs.pop('greedy')
        if 'nodeps' in kwargs:
            kwargs['resolve_deps'] = not kwargs.pop('nodeps')
        if lookaside:
            kwargs['lookaside_repos'] = ['lookaside']

        self.dnf = self.dnf_instance(arch, lookaside=lookaside, persistdir=self.tmp_dir)

        if self.get_langpacks:
            kwargs['langpacks'] = self.dnf.comps_wrapper.get_langpacks()

        groups = groups or []
        exclude_groups = []
        _, conditional_packages = self.dnf.comps_wrapper.get_comps_packages(groups, exclude_groups)
        self.g = Gather(self.dnf, GatherOptions(**kwargs))

        self.g.logger.handlers = [h for h in self.g.logger.handlers
                                  if h.name != 'capture-logs']
        log_output = cStringIO()
        handler = logging.StreamHandler(log_output)
        handler.name = 'capture-logs'
        handler.setLevel(logging.WARNING)
        self.g.logger.addHandler(handler)

        self.g.gather(packages, conditional_packages)
        log_output.seek(0)
        _, self.broken_deps, _ = PungiWrapper().parse_log(log_output)

        return {
            'debuginfo': convert_dnf_packages(self.g.result_debug_packages,
                                              self.g.result_package_flags),
            'srpm': convert_dnf_packages(self.g.result_source_packages,
                                         self.g.result_package_flags),
            'rpm': convert_dnf_packages(self.g.result_binary_packages,
                                        self.g.result_package_flags),
        }

    def dnf_instance(self, base_arch, exclude=None, lookaside=False, persistdir=None):
        conf = Conf(base_arch)
        conf.persistdir = persistdir
        conf.cachedir = self.cachedir
        if exclude:
            conf.exclude = exclude
        dnf = DnfWrapper(conf)
        if lookaside:
            dnf.add_repo("lookaside", lookaside, lookaside=True)
        dnf.add_repo("test-repo", self.repo)
        dnf.fill_sack(load_system_repo=False, load_available_repos=True)
        dnf.read_comps()
        return dnf

    def assertFlags(self, nvra, expected_flags):
        assert isinstance(nvra, str)
        assert isinstance(expected_flags, list)
        expected_flags = set(expected_flags)

        found = False
        for pkg, flags in self.g.result_package_flags.items():
            if nvra == "%s-%s-%s.%s" % (pkg.name, pkg.version, pkg.release, pkg.arch):
                self.assertEqual(
                    flags, expected_flags,
                    "pkg: %s; flags: %s; expected flags: %s" % (nvra, flags, expected_flags))
                found = True
        if not found:
            flags = set()
            self.assertEqual(
                flags, expected_flags,
                "pkg: %s; flags: %s; expected flags: %s" % (nvra, flags, expected_flags))

    def test_langpacks(self):
        self.get_langpacks = True
        super(DNFDepsolvingTestCase, self).test_langpacks()

    @unittest.skip('DNF code does not support NVR as input')
    def test_bash_older(self):
        pass

    def test_whitelist_old_version(self):
        # There are two version of dummy-bash in the package set; let's
        # whitelist only the older one and its dependencies.
        packages = [
            "dummy-bash",
        ]
        package_whitelist = [
            "dummy-basesystem-10.0-6",
            "dummy-bash-debuginfo-4.2.37-5",
            "dummy-bash-4.2.37-5",
            "dummy-filesystem-4.2.37-6",
            "dummy-glibc-common-2.14-5",
            "dummy-glibc-debuginfo-common-2.14-5",
            "dummy-glibc-debuginfo-2.14-5",
            "dummy-glibc-2.14-5",
        ]
        pkg_map = self.go(packages, None, greedy="none", package_whitelist=package_whitelist)

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-5.x86_64.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_firefox_selfhosting_with_krb5_lookaside(self):
        super(DNFDepsolvingTestCase, self).test_firefox_selfhosting_with_krb5_lookaside()
        self.assertFlags("dummy-krb5-devel-1.10-5.x86_64", [PkgFlag.lookaside])
        self.assertFlags("dummy-krb5-1.10-5.src", [PkgFlag.lookaside])
        self.assertFlags("dummy-krb5-debuginfo-1.10-5.x86_64", [PkgFlag.lookaside])

    def test_package_whitelist(self):
        packages = ['*']
        whitelist = [
            'dummy-bash-4.2.37-6',
        ]

        pkg_map = self.go(packages, None, package_whitelist=whitelist)

        self.assertItemsEqual(pkg_map["rpm"], [
            'dummy-bash-4.2.37-6.x86_64.rpm',
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            'dummy-bash-4.2.37-6.src.rpm',
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
        ])
