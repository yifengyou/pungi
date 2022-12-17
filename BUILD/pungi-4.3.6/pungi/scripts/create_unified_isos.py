# -*- coding: utf-8 -*-

"""
This script creates unified ISOs for a specified compose.
Unified ISOs are created per architecture and contain all variant packages and
repos.
"""

import argparse


from pungi_utils.unified_isos import UnifiedISO


def parse_args():
    parser = argparse.ArgumentParser(add_help=True)

    parser.add_argument(
        "compose",
        metavar="<compose-path>",
        nargs=1,
        help="path to compose",
    )
    parser.add_argument(
        "--arch",
        metavar="<arch>",
        dest="arches",
        action="append",
        help="only generate ISOs for specified arch",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    iso = UnifiedISO(args.compose[0], arches=args.arches)
    iso.create(delete_temp=True)
