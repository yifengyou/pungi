# -*- coding: utf-8 -*-


# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.


import argparse
import logging

from .tree import Tree
from .installer import Installer


def main(args=None):
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(help="Sub commands")

    treep = subparser.add_parser("tree", help="Compose OSTree repository")
    treep.set_defaults(_class=Tree, func='run')
    treep.add_argument('--repo', metavar='PATH', required=True,
                       help='where to put the OSTree repo (required)')
    treep.add_argument('--treefile', metavar="FILE", required=True,
                       help='treefile for rpm-ostree (required)')
    treep.add_argument('--log-dir', metavar="DIR", required=True,
                       help='where to log output and commitid (required). \
                             Note: commitid file will be written to this dir')
    treep.add_argument('--extra-config', metavar="FILE",
                       help='JSON file contains extra configurations')
    treep.add_argument('--version', metavar="VERSION",
                       help='version string to be added as versioning metadata')
    treep.add_argument('--update-summary', action='store_true',
                       help='update summary metadata')
    treep.add_argument('--ostree-ref', metavar='PATH',
                       help='override ref value from treefile')
    treep.add_argument('--force-new-commit', action='store_true',
                       help='do not use rpm-ostree\'s built-in change detection')

    installerp = subparser.add_parser("installer", help="Create an OSTree installer image")
    installerp.set_defaults(_class=Installer, func='run')
    installerp.add_argument('-p', '--product', metavar='PRODUCT', required=True,
                            help='product name (required)')
    installerp.add_argument('-v', '--version', metavar='VERSION', required=True,
                            help='version identifier (required)')
    installerp.add_argument('-r', '--release', metavar='RELEASE', required=True,
                            help='release information (required)')
    installerp.add_argument('-s', '--source', metavar='REPOSITORY', required=True,
                            action='append',
                            help='source repository (required)')
    installerp.add_argument('-o', '--output', metavar='DIR', required=True,
                            help='path to image output directory (required)')
    installerp.add_argument('--log-dir', metavar='DIR',
                            help='path to log directory')
    installerp.add_argument('--volid', metavar='VOLID',
                            help='volume id')
    installerp.add_argument('--variant', metavar='VARIANT',
                            help='variant name')
    installerp.add_argument('--rootfs-size', metavar='SIZE')
    installerp.add_argument('--nomacboot', action='store_true', default=False)
    installerp.add_argument('--noupgrade', action='store_true', default=False)
    installerp.add_argument('--isfinal', action='store_true', default=False)

    installerp.add_argument('--installpkgs', metavar='PACKAGE', action='append',
                            help='package glob to install before runtime-install.tmpl')
    installerp.add_argument('--add-template', metavar='FILE', action='append',
                            help='Additional template for runtime image')
    installerp.add_argument('--add-template-var', metavar='ADD_TEMPLATE_VARS', action='append',
                            help='Set variable for runtime image template')
    installerp.add_argument('--add-arch-template', metavar='FILE', action='append',
                            help='Additional template for architecture-specific image')
    installerp.add_argument('--add-arch-template-var', metavar='ADD_ARCH_TEMPLATE_VARS', action='append',
                            help='Set variable for architecture-specific image')

    installerp.add_argument('--extra-config', metavar='FILE',
                            help='JSON file contains extra configurations')

    args = parser.parse_args(args)

    logging.basicConfig(format="%(message)s", level=logging.DEBUG)

    _class = args._class()
    _class.set_args(args)
    func = getattr(_class, args.func)
    func()
