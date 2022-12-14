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

from __future__ import absolute_import
from __future__ import print_function

import os
import selinux
import sys

from argparse import ArgumentParser, Action

from pungi import get_full_version
import pungi.gather
import pungi.config
import pungi.ks


def get_arguments(config):
    parser = ArgumentParser()

    class SetConfig(Action):
        def __call__(self, parser, namespace, value, option_string=None):
            config.set("pungi", self.dest, value)

    parser.add_argument("--version", action="version", version=get_full_version())

    # Pulled in from config file to be cli options as part of pykickstart conversion
    parser.add_argument(
        "--name",
        dest="family",
        type=str,
        action=SetConfig,
        help='the name for your distribution (defaults to "Fedora"), DEPRECATED',
    )
    parser.add_argument(
        "--family",
        dest="family",
        action=SetConfig,
        help='the family name for your distribution (defaults to "Fedora")',
    )
    parser.add_argument(
        "--ver",
        dest="version",
        action=SetConfig,
        help="the version of your distribution (defaults to datestamp)",
    )
    parser.add_argument(
        "--flavor",
        dest="variant",
        action=SetConfig,
        help="the flavor of your distribution spin (optional), DEPRECATED",
    )
    parser.add_argument(
        "--variant",
        dest="variant",
        action=SetConfig,
        help="the variant of your distribution spin (optional)",
    )
    parser.add_argument(
        "--destdir",
        dest="destdir",
        action=SetConfig,
        help="destination directory (defaults to current directory)",
    )
    parser.add_argument(
        "--cachedir",
        dest="cachedir",
        action=SetConfig,
        help="package cache directory (defaults to /var/cache/pungi)",
    )
    parser.add_argument(
        "--bugurl",
        dest="bugurl",
        action=SetConfig,
        help="the url for your bug system (defaults to http://bugzilla.redhat.com)",
    )
    parser.add_argument(
        "--selfhosting",
        action="store_true",
        dest="selfhosting",
        help="build a self-hosting tree by following build dependencies (optional)",
    )
    parser.add_argument(
        "--fulltree",
        action="store_true",
        dest="fulltree",
        help="build a tree that includes all packages built from corresponding source rpms (optional)",  # noqa: E501
    )
    parser.add_argument(
        "--nosource",
        action="store_true",
        dest="nosource",
        help="disable gathering of source packages (optional)",
    )
    parser.add_argument(
        "--nodebuginfo",
        action="store_true",
        dest="nodebuginfo",
        help="disable gathering of debuginfo packages (optional)",
    )
    parser.add_argument(
        "--nodownload",
        action="store_true",
        dest="nodownload",
        help="disable downloading of packages. instead, print the package URLs (optional)",  # noqa: E501
    )
    parser.add_argument(
        "--norelnotes",
        action="store_true",
        dest="norelnotes",
        help="disable gathering of release notes (optional); DEPRECATED",
    )
    parser.add_argument(
        "--nogreedy",
        action="store_true",
        dest="nogreedy",
        help="disable pulling of all providers of package dependencies (optional)",
    )
    parser.add_argument(
        "--nodeps",
        action="store_false",
        dest="resolve_deps",
        default=True,
        help="disable resolving dependencies",
    )
    parser.add_argument(
        "--sourceisos",
        default=False,
        action="store_true",
        dest="sourceisos",
        help="Create the source isos (other arch runs must be done)",
    )
    parser.add_argument(
        "--force",
        default=False,
        action="store_true",
        help="Force reuse of an existing destination directory (will overwrite files)",
    )
    parser.add_argument(
        "--isfinal",
        default=False,
        action="store_true",
        help="Specify this is a GA tree, which causes betanag to be turned off during install",  # noqa: E501
    )
    parser.add_argument(
        "--nohash",
        default=False,
        action="store_true",
        help="disable hashing the Packages trees",
    )
    parser.add_argument(
        "--full-archlist",
        action="store_true",
        help="Use the full arch list for x86_64 (include i686, i386, etc.)",
    )
    parser.add_argument("--arch", help="Override default (uname based) arch")
    parser.add_argument(
        "--greedy", metavar="METHOD", help="Greedy method; none, all, build"
    )
    parser.add_argument(
        "--multilib",
        action="append",
        metavar="METHOD",
        help="Multilib method; can be specified multiple times; recommended: devel, runtime",  # noqa: E501
    )
    parser.add_argument(
        "--lookaside-repo",
        action="append",
        dest="lookaside_repos",
        metavar="NAME",
        help="Specify lookaside repo name(s) (packages will used for depsolving but not be included in the output)",  # noqa: E501
    )
    parser.add_argument(
        "--workdirbase",
        dest="workdirbase",
        action=SetConfig,
        help="base working directory (defaults to destdir + /work)",
    )
    parser.add_argument(
        "--no-dvd",
        default=False,
        action="store_true",
        dest="no_dvd",
        help="Do not make a install DVD/CD only the netinstall image and the tree",
    )
    parser.add_argument("--lorax-conf", help="Path to lorax.conf file (optional)")
    parser.add_argument(
        "-i",
        "--installpkgs",
        default=[],
        action="append",
        metavar="STRING",
        help="Package glob for lorax to install before runtime-install.tmpl runs. (may be listed multiple times)",  # noqa: E501
    )
    parser.add_argument(
        "--multilibconf",
        default=None,
        action=SetConfig,
        help="Path to multilib conf files. Default is /usr/share/pungi/multilib/",
    )

    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=True,
        help="Path to kickstart config file",
    )
    parser.add_argument(
        "--all-stages",
        action="store_true",
        default=True,
        dest="do_all",
        help="Enable ALL stages",
    )
    parser.add_argument(
        "-G",
        action="store_true",
        default=False,
        dest="do_gather",
        help="Flag to enable processing the Gather stage",
    )
    parser.add_argument(
        "-C",
        action="store_true",
        default=False,
        dest="do_createrepo",
        help="Flag to enable processing the Createrepo stage",
    )
    parser.add_argument(
        "-B",
        action="store_true",
        default=False,
        dest="do_buildinstall",
        help="Flag to enable processing the BuildInstall stage",
    )
    parser.add_argument(
        "-I",
        action="store_true",
        default=False,
        dest="do_createiso",
        help="Flag to enable processing the CreateISO stage",
    )
    parser.add_argument(
        "--relnotepkgs",
        dest="relnotepkgs",
        action=SetConfig,
        help="Rpms which contain the release notes",
    )
    parser.add_argument(
        "--relnotefilere",
        dest="relnotefilere",
        action=SetConfig,
        help="Which files are the release notes -- GPL EULA",
    )
    parser.add_argument(
        "--nomacboot",
        action="store_true",
        dest="nomacboot",
        help="disable setting up macboot as no hfs support ",
    )

    parser.add_argument(
        "--rootfs-size",
        dest="rootfs_size",
        action=SetConfig,
        default=False,
        help="Size of root filesystem in GiB. If not specified, use lorax default value",  # noqa: E501
    )

    parser.add_argument(
        "--pungirc",
        dest="pungirc",
        default="~/.pungirc",
        action=SetConfig,
        help="Read pungi options from config file ",
    )

    opts = parser.parse_args()

    if (
        not config.get("pungi", "variant").isalnum()
        and not config.get("pungi", "variant") == ""
    ):
        parser.error("Variant must be alphanumeric")

    if (
        opts.do_gather
        or opts.do_createrepo
        or opts.do_buildinstall
        or opts.do_createiso
    ):
        opts.do_all = False

    if opts.arch and (opts.do_all or opts.do_buildinstall):
        parser.error("Cannot override arch while the BuildInstall stage is enabled")

    # set the iso_basename.
    if not config.get("pungi", "variant") == "":
        config.set(
            "pungi",
            "iso_basename",
            "%s-%s" % (config.get("pungi", "family"), config.get("pungi", "variant")),
        )
    else:
        config.set("pungi", "iso_basename", config.get("pungi", "family"))

    return opts


def main():

    config = pungi.config.Config()
    opts = get_arguments(config)

    # Read the config to create "new" defaults
    # reparse command line options so they take precedence
    config = pungi.config.Config(pungirc=opts.pungirc)
    opts = get_arguments(config)

    # You must be this high to ride if you're going to do root tasks
    if os.geteuid() != 0 and (opts.do_all or opts.do_buildinstall):
        print("You must run pungi as root", file=sys.stderr)
        return 1

    if opts.do_all or opts.do_buildinstall:
        try:
            enforcing = selinux.security_getenforce()
        except Exception:
            print("INFO: selinux disabled")
            enforcing = False
        if enforcing:
            print(
                "WARNING: SELinux is enforcing.  This may lead to a compose with selinux disabled."  # noqa: E501
            )
            print("Consider running with setenforce 0.")

    # Set up the kickstart parser and pass in the kickstart file we were handed
    ksparser = pungi.ks.get_ksparser(ks_path=opts.config)

    if opts.sourceisos:
        config.set("pungi", "arch", "source")

    for part in ksparser.handler.partition.partitions:
        if part.mountpoint == "iso":
            config.set("pungi", "cdsize", str(part.size))

    config.set("pungi", "force", str(opts.force))

    if config.get("pungi", "workdirbase") == "/work":
        config.set("pungi", "workdirbase", "%s/work" % config.get("pungi", "destdir"))
    # Set up our directories
    if not os.path.exists(config.get("pungi", "destdir")):
        try:
            os.makedirs(config.get("pungi", "destdir"))
        except OSError:
            print(
                "Error: Cannot create destination dir %s"
                % config.get("pungi", "destdir"),
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("Warning: Reusing existing destination directory.")

    if not os.path.exists(config.get("pungi", "workdirbase")):
        try:
            os.makedirs(config.get("pungi", "workdirbase"))
        except OSError:
            print(
                "Error: Cannot create working base dir %s"
                % config.get("pungi", "workdirbase"),
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("Warning: Reusing existing working base directory.")

    cachedir = config.get("pungi", "cachedir")

    if not os.path.exists(cachedir):
        try:
            os.makedirs(cachedir)
        except OSError:
            print("Error: Cannot create cache dir %s" % cachedir, file=sys.stderr)
            sys.exit(1)

    # Set debuginfo flag
    if opts.nodebuginfo:
        config.set("pungi", "debuginfo", "False")
    if opts.greedy:
        config.set("pungi", "greedy", opts.greedy)
    else:
        # XXX: compatibility
        if opts.nogreedy:
            config.set("pungi", "greedy", "none")
        else:
            config.set("pungi", "greedy", "all")
    config.set("pungi", "resolve_deps", str(bool(opts.resolve_deps)))
    if opts.isfinal:
        config.set("pungi", "isfinal", "True")
    if opts.nohash:
        config.set("pungi", "nohash", "True")
    if opts.full_archlist:
        config.set("pungi", "full_archlist", "True")
    if opts.arch:
        config.set("pungi", "arch", opts.arch)
    if opts.multilib:
        config.set("pungi", "multilib", " ".join(opts.multilib))
    if opts.lookaside_repos:
        config.set("pungi", "lookaside_repos", " ".join(opts.lookaside_repos))
    if opts.no_dvd:
        config.set("pungi", "no_dvd", "True")
    if opts.nomacboot:
        config.set("pungi", "nomacboot", "True")
    config.set("pungi", "fulltree", str(bool(opts.fulltree)))
    config.set("pungi", "selfhosting", str(bool(opts.selfhosting)))
    config.set("pungi", "nosource", str(bool(opts.nosource)))
    config.set("pungi", "nodebuginfo", str(bool(opts.nodebuginfo)))

    if opts.lorax_conf:
        config.set("lorax", "conf_file", opts.lorax_conf)
    if opts.installpkgs:
        config.set("lorax", "installpkgs", " ".join(opts.installpkgs))

    # Actually do work.
    mypungi = pungi.gather.Pungi(config, ksparser)

    with mypungi.yumlock:
        if not opts.sourceisos:
            if opts.do_all or opts.do_gather or opts.do_buildinstall:
                mypungi._inityum()  # initialize the yum object for things that need it
            if opts.do_all or opts.do_gather:
                mypungi.gather()
                if opts.nodownload:
                    for line in mypungi.list_packages():
                        flags_str = ",".join(line["flags"])
                        if flags_str:
                            flags_str = "(%s)" % flags_str
                        sys.stdout.write("RPM%s: %s\n" % (flags_str, line["path"]))
                    sys.stdout.flush()
                else:
                    mypungi.downloadPackages()
                mypungi.makeCompsFile()
                if not opts.nodebuginfo:
                    mypungi.getDebuginfoList()
                    if opts.nodownload:
                        for line in mypungi.list_debuginfo():
                            flags_str = ",".join(line["flags"])
                            if flags_str:
                                flags_str = "(%s)" % flags_str
                            sys.stdout.write(
                                "DEBUGINFO%s: %s\n" % (flags_str, line["path"])
                            )
                        sys.stdout.flush()
                    else:
                        mypungi.downloadDebuginfo()
                if not opts.nosource:
                    if opts.nodownload:
                        for line in mypungi.list_srpms():
                            flags_str = ",".join(line["flags"])
                            if flags_str:
                                flags_str = "(%s)" % flags_str
                            sys.stdout.write("SRPM%s: %s\n" % (flags_str, line["path"]))
                        sys.stdout.flush()
                    else:
                        mypungi.downloadSRPMs()

                print("RPM size:       %s MiB" % (mypungi.size_packages() / 1024**2))
                if not opts.nodebuginfo:
                    print(
                        "DEBUGINFO size: %s MiB"
                        % (mypungi.size_debuginfo() / 1024**2)
                    )
                if not opts.nosource:
                    print("SRPM size:      %s MiB" % (mypungi.size_srpms() / 1024**2))

    # Furthermore (but without the yumlock...)
    if not opts.sourceisos:
        if opts.do_all or opts.do_createrepo:
            mypungi.doCreaterepo()

        if opts.do_all or opts.do_buildinstall:
            if not opts.norelnotes:
                mypungi.doGetRelnotes()
            mypungi.doBuildinstall()

        if opts.do_all or opts.do_createiso:
            mypungi.doCreateIsos()

    # Do things slightly different for src.
    if opts.sourceisos:
        # we already have all the content gathered
        mypungi.topdir = os.path.join(
            config.get("pungi", "destdir"),
            config.get("pungi", "version"),
            config.get("pungi", "variant"),
            "source",
            "SRPMS",
        )
        mypungi.doCreaterepo(comps=False)
        if opts.do_all or opts.do_createiso:
            mypungi.doCreateIsos()

    print("All done!")
