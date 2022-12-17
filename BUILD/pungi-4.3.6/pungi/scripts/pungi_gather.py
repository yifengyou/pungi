# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function

import argparse
from collections import defaultdict
import os
import sys

import pungi.ks
from pungi.dnf_wrapper import DnfWrapper, Conf
from pungi.gather_dnf import Gather, GatherOptions
from pungi.profiler import Profiler
from pungi.util import temp_dir


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiler",
        action="store_true",
    )
    parser.add_argument(
        "--arch",
        required=True,
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        required=True,
        help="path to kickstart config file",
    )
    parser.add_argument(
        "--download-to",
        metavar="PATH",
        help="download packages to given directory instead of just printing paths",
    )

    group = parser.add_argument_group("Repository options")
    group.add_argument(
        "--lookaside",
        action="append",
        metavar="[REPOID]",
        help="lookaside repositories",
    )

    group = parser.add_argument_group("Gather options")
    group.add_argument(
        "--nodeps",
        action="store_true",
        help="disable resolving dependencies",
    )
    group.add_argument(
        "--selfhosting",
        action="store_true",
        help="build a self-hosting tree by following build dependencies (optional)",
    )
    group.add_argument(
        "--fulltree",
        action="store_true",
        help="build a tree that includes all packages built from corresponding source rpms (optional)",  # noqa: E501
    )
    group.add_argument(
        "--greedy",
        metavar="METHOD",
        # TODO: read choices from library
        choices=["none", "all", "build"],
    )
    group.add_argument(
        "--multilib",
        metavar="[METHOD]",
        action="append",
    )
    group.add_argument(
        "--tempdir",
        metavar="PATH",
        help="path to temp dir (default: /tmp)",
        default="/tmp",
    )
    group.add_argument(
        "--exclude-source",
        action="store_true",
        default=False,
        help="exclude source packages from gathering",
    )
    group.add_argument(
        "--exclude-debug",
        action="store_true",
        default=False,
        help="exclude debug packages from gathering",
    )
    return parser


def main(ns, persistdir, cachedir):
    dnf_conf = Conf(ns.arch)
    dnf_conf.persistdir = persistdir
    dnf_conf.cachedir = cachedir
    dnf_obj = DnfWrapper(dnf_conf)

    gather_opts = GatherOptions()

    if ns.greedy:
        gather_opts.greedy_method = ns.greedy

    if ns.multilib:
        gather_opts.multilib_methods = ns.multilib

    if ns.lookaside:
        gather_opts.lookaside_repos = ns.lookaside

    if ns.fulltree:
        gather_opts.fulltree = True

    if ns.selfhosting:
        gather_opts.selfhosting = True

    if ns.nodeps:
        gather_opts.resolve_deps = False

    if ns.exclude_source:
        gather_opts.exclude_source = True

    if ns.exclude_debug:
        gather_opts.exclude_debug = True

    ksparser = pungi.ks.get_ksparser(ns.config)

    # read repos from ks
    for ks_repo in ksparser.handler.repo.repoList:
        # HACK: lookaside repos first; this is workaround for no repo priority
        # handling in hawkey
        if ks_repo.name not in gather_opts.lookaside_repos:
            continue

        if getattr(ks_repo, "metalink", False):
            dnf_obj.add_repo(
                ks_repo.name,
                ks_repo.baseurl,
                enablegroups=False,
                metalink=ks_repo.metalink,
            )
        elif getattr(ks_repo, "mirrorlist", False):
            dnf_obj.add_repo(
                ks_repo.name,
                ks_repo.baseurl,
                enablegroups=False,
                mirrorlist=ks_repo.mirrorlist,
            )
        else:
            dnf_obj.add_repo(ks_repo.name, ks_repo.baseurl, enablegroups=False)

    for ks_repo in ksparser.handler.repo.repoList:
        if ks_repo.name in gather_opts.lookaside_repos:
            continue
        if getattr(ks_repo, "metalink", False):
            dnf_obj.add_repo(ks_repo.name, ks_repo.baseurl, metalink=ks_repo.metalink)
        elif getattr(ks_repo, "mirrorlist", False):
            dnf_obj.add_repo(
                ks_repo.name, ks_repo.baseurl, mirrorlist=ks_repo.mirrorlist
            )
        else:
            dnf_obj.add_repo(ks_repo.name, ks_repo.baseurl)

    with Profiler("DnfWrapper.fill_sack()"):
        dnf_obj.fill_sack(load_system_repo=False, load_available_repos=True)
        dnf_obj.read_comps()

    gather_opts.langpacks = dnf_obj.comps_wrapper.get_langpacks()
    gather_opts.multilib_blacklist = ksparser.handler.multilib_blacklist
    gather_opts.multilib_whitelist = ksparser.handler.multilib_whitelist
    gather_opts.prepopulate = ksparser.handler.prepopulate
    gather_opts.fulltree_excludes = ksparser.handler.fulltree_excludes

    g = Gather(dnf_obj, gather_opts)

    packages, conditional_packages = ksparser.get_packages(dnf_obj)
    excluded = ksparser.get_excluded_packages(dnf_obj)

    for i in excluded:
        packages.add("-%s" % i)

    g.gather(packages, conditional_packages)

    if ns.download_to:
        g.download(ns.download_to)
    else:
        print_rpms(g)
    if ns.profiler:
        Profiler.print_results(stream=sys.stderr)


def _get_url(pkg):
    if pkg.baseurl:
        result = os.path.join(pkg.baseurl, pkg.location)
    else:
        result = os.path.join(pkg.repo.baseurl[0], pkg.location)
    return result


def _fmt_flags(flags):
    return "(%s)" % ",".join(sorted(f.name.replace("_", "-") for f in flags))


def deduplicate(gather_obj, items):
    """The set of packages in ``items`` may contain the same package multiple
    times, with different source repos. Since they have the same NVRA, we can
    assume they are identical and should merge their flags.
    """
    result = defaultdict(set)
    for pkg in items:
        flags = gather_obj.result_package_flags.get(pkg, [])
        result[_get_url(pkg)].update(flags)
    return result.items()


def print_rpms(gather_obj):
    for url, flags in deduplicate(gather_obj, gather_obj.result_binary_packages):
        print("RPM%s: %s" % (_fmt_flags(flags), url))

    for url, flags in deduplicate(gather_obj, gather_obj.result_debug_packages):
        print("DEBUGINFO%s: %s" % (_fmt_flags(flags), url))

    for url, flags in deduplicate(gather_obj, gather_obj.result_source_packages):
        print("SRPM%s: %s" % (_fmt_flags(flags), url))


def cli_main():
    parser = get_parser()
    ns = parser.parse_args()

    with temp_dir(dir=ns.tempdir, prefix="pungi_dnf_") as persistdir:
        with temp_dir(dir=ns.tempdir, prefix="pungi_dnf_cache_") as cachedir:
            main(ns, persistdir, cachedir)
