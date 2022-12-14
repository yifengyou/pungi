# -*- coding: utf-8 -*-

from __future__ import absolute_import

import sys
import argparse

from pungi.wrappers.comps import CompsFilter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="redirect output to a file")
    parser.add_argument(
        "--arch", required=True, help="filter groups and packages according to an arch"
    )
    parser.add_argument(
        "--arch-only-groups",
        default=False,
        action="store_true",
        help="keep only arch groups, remove the rest",
    )
    parser.add_argument(
        "--arch-only-packages",
        default=False,
        action="store_true",
        help="keep only arch packages, remove the rest",
    )
    parser.add_argument(
        "--arch-only-environments",
        default=False,
        action="store_true",
        help="keep only arch environments, remove the rest",
    )
    parser.add_argument(
        "--remove-categories",
        default=False,
        action="store_true",
        help="remove all categories",
    )
    parser.add_argument(
        "--remove-langpacks",
        default=False,
        action="store_true",
        help="remove the langpacks section",
    )
    parser.add_argument(
        "--remove-translations",
        default=False,
        action="store_true",
        help="remove all translations",
    )
    parser.add_argument(
        "--remove-environments",
        default=False,
        action="store_true",
        help="remove all environment sections",
    )
    parser.add_argument(
        "--keep-empty-group",
        default=[],
        action="append",
        metavar="GROUPID",
        help="keep groups even if they are empty",
    )
    parser.add_argument(
        "--lookaside-group",
        default=[],
        action="append",
        metavar="GROUPID",
        help="keep this group in environments even if they are not defined in the comps",  # noqa: E501
    )
    parser.add_argument(
        "--no-cleanup",
        default=False,
        action="store_true",
        help="don't remove empty groups and categories",
    )
    parser.add_argument(
        "--no-reindent",
        default=False,
        action="store_true",
        help="don't re-indent the output",
    )
    parser.add_argument("comps_file", metavar="COMPS_FILE")
    parser.add_argument(
        "--variant", help="filter groups and packages according to variant name"
    )

    opts = parser.parse_args()

    with open(opts.comps_file, "rb") as file_obj:
        f = CompsFilter(file_obj, reindent=not opts.no_reindent)
    f.filter_packages(opts.arch, opts.variant, opts.arch_only_packages)
    f.filter_groups(opts.arch, opts.variant, opts.arch_only_groups)
    f.filter_environments(opts.arch, opts.variant, opts.arch_only_environments)

    if not opts.no_cleanup:
        f.cleanup(opts.arch, opts.keep_empty_group, opts.lookaside_group)

    if opts.remove_categories:
        f.remove_categories()

    if opts.remove_langpacks:
        f.remove_langpacks()

    if opts.remove_translations:
        f.remove_translations()

    if opts.remove_environments:
        f.remove_environments()

    f.write(open(opts.output, "wb") if opts.output else sys.stdout)
