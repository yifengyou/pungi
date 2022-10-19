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

"""
This is a wrapper for a hybrid depsolver that understands how module
dependencies work. It's Funny Solver, because it does funny things.

https://github.com/fedora-modularity/fus

The executable basically provides one iteration of the traditional DNF based
depsolver. It has to be run multiple times to explicitly add multilib packages,
or source packages to include build dependencies (which is not yet supported in
Pungi).
"""


def get_cmd(
    conf_file,
    arch,
    repos,
    lookasides,
    platform=None,
    filter_packages=None,
):
    cmd = ["fus", "--verbose", "--arch", arch]

    # Lookaside repos should be first. If the same package is present in
    # multiple repos, libsolv gives priority to the first repo.
    for idx, repo in enumerate(lookasides):
        cmd.append("--repo=lookaside-%s,lookaside,%s" % (idx, _prep_path(repo)))
    for idx, repo in enumerate(repos):
        cmd.append("--repo=repo-%s,repo,%s" % (idx, _prep_path(repo)))

    if platform:
        cmd.append("--platform=%s" % platform)

    for pkg in sorted(filter_packages or []):
        cmd.append("--exclude=%s" % pkg)

    cmd.append("@%s" % conf_file)

    return cmd


def write_config(conf_file, modules, packages):
    with open(conf_file, "w") as f:
        for module in modules:
            f.write("module(%s)\n" % module)
        for pkg in packages:
            f.write("%s\n" % pkg)


def _prep_path(path):
    """Strip file:// from the path if present."""
    if path.startswith("file://"):
        return path[len("file://"):]
    return path


def parse_output(output):
    """Read output of fus from the given filepath, and return a set of tuples
    (NVR, arch, flags) and a set of module NSVCs.
    """
    packages = set()
    modules = set()
    with open(output) as f:
        for line in f:
            if " " in line or "@" not in line:
                continue
            nevra, _ = line.strip().rsplit("@", 1)
            if not nevra.startswith("module:"):
                flags = set()
                name, arch = nevra.rsplit(".", 1)
                if name.startswith("*"):
                    flags.add("modular")
                    name = name[1:]
                packages.add((name, arch, frozenset(flags)))
            else:
                name, arch = nevra.rsplit(".", 1)
                modules.add(name.split(":", 1)[1])
    return packages, modules
