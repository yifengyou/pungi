#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import glob

import distutils.command.sdist
from setuptools import setup


# override default tarball format with bzip2
distutils.command.sdist.sdist.default_format = {"posix": "bztar"}


# recursively scan for python modules to be included
package_root_dirs = ["pungi", "pungi_utils"]
packages = set()
for package_root_dir in package_root_dirs:
    for root, dirs, files in os.walk(package_root_dir):
        if "__init__.py" in files:
            packages.add(root.replace("/", "."))
packages = sorted(packages)


setup(
    name            = "pungi",
    version         = "4.1.38",
    description     = "Distribution compose tool",
    url             = "https://pagure.io/pungi",
    author          = "Dennis Gilmore",
    author_email    = "dgilmore@fedoraproject.org",
    license         = "GPLv2",

    packages        = packages,
    scripts         = [
        'bin/comps_filter',
        'bin/pungi',
        'bin/pungi-config-dump',
        'bin/pungi-config-validate',
        'bin/pungi-create-unified-isos',
        'bin/pungi-fedmsg-notification',
        'bin/pungi-gather',
        'bin/pungi-koji',
        'bin/pungi-make-ostree',
        'bin/pungi-notification-report-progress',
        'bin/pungi-orchestrate',
        'bin/pungi-patch-iso',
        'bin/pungi-wait-for-signed-ostree-handler',

        'contrib/yum-dnf-compare/pungi-compare-depsolving',
    ],
    data_files      = [
        ('/usr/share/pungi', glob.glob('share/*.xsl')),
        ('/usr/share/pungi', glob.glob('share/*.ks')),
        ('/usr/share/pungi', glob.glob('share/*.dtd')),
        ('/usr/share/pungi/multilib', glob.glob('share/multilib/*')),
    ],
    test_suite      = "tests",
    install_requires = [
        "jsonschema",
        "kobo",
        "lxml",
        "productmd",
        "six",
        'dogpile.cache',
        ],
    extras_require={
        ':python_version=="2.7"': [
            'enum34',
            "lockfile",
            'dict.sorted',
        ]
    },
    tests_require = [
        "mock",
        "nose",
        "nose-cov",
        ],
)
