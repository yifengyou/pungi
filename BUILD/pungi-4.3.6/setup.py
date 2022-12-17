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
    name="pungi",
    version="4.3.6",
    description="Distribution compose tool",
    url="https://pagure.io/pungi",
    author="Dennis Gilmore",
    author_email="dgilmore@fedoraproject.org",
    license="GPLv2",
    packages=packages,
    entry_points={
        "console_scripts": [
            "comps_filter = pungi.scripts.comps_filter:main",
            "pungi = pungi.scripts.pungi:main",
            "pungi-create-unified-isos = pungi.scripts.create_unified_isos:main",
            "pungi-fedmsg-notification = pungi.scripts.fedmsg_notification:main",
            "pungi-patch-iso = pungi.scripts.patch_iso:cli_main",
            "pungi-make-ostree = pungi.ostree:main",
            "pungi-notification-report-progress = pungi.scripts.report_progress:main",
            "pungi-orchestrate = pungi_utils.orchestrator:main",
            "pungi-wait-for-signed-ostree-handler = pungi.scripts.wait_for_signed_ostree_handler:main",  # noqa: E501
            "pungi-koji = pungi.scripts.pungi_koji:cli_main",
            "pungi-gather = pungi.scripts.pungi_gather:cli_main",
            "pungi-config-dump = pungi.scripts.config_dump:cli_main",
            "pungi-config-validate = pungi.scripts.config_validate:cli_main",
        ]
    },
    scripts=["contrib/yum-dnf-compare/pungi-compare-depsolving"],
    data_files=[
        ("/usr/share/pungi", glob.glob("share/*.xsl")),
        ("/usr/share/pungi", glob.glob("share/*.ks")),
        ("/usr/share/pungi", glob.glob("share/*.dtd")),
        ("/usr/share/pungi/multilib", glob.glob("share/multilib/*")),
    ],
    test_suite="tests",
    install_requires=[
        "jsonschema",
        "kobo",
        "lxml",
        "productmd>=1.23",
        "six",
        "dogpile.cache",
    ],
    extras_require={':python_version=="2.7"': ["enum34", "lockfile"]},
    tests_require=["mock", "pytest", "pytest-cov"],
)
