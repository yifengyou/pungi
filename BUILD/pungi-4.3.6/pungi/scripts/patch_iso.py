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
import sys

from pungi_utils import patch_iso


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print debugging information"
    )
    parser.add_argument(
        "--supported",
        choices=("true", "false"),
        help="Override supported bit on the ISO",
    )
    parser.add_argument("--volume-id", help="Override volume ID on the ISO")
    parser.add_argument(
        "--force-arch", help="Treat the ISO as bootable on given architecture"
    )
    parser.add_argument(
        "--work-dir", help="Set custom working directory. Default: /tmp/", default=None
    )
    parser.add_argument(
        "target", metavar="TARGET_ISO", help="which file to write the result to"
    )
    parser.add_argument("source", metavar="SOURCE_ISO", help="source ISO to work with")
    parser.add_argument(
        "dirs",
        nargs="+",
        metavar="GRAFT_DIR",
        help="extra directories to graft on the ISO",
    )
    opts = parser.parse_args(args)

    level = logging.DEBUG if opts.verbose else logging.INFO
    format = "%(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=format)
    log = logging.getLogger()

    patch_iso.run(log, opts)


def cli_main():
    if main():
        sys.exit(1)
