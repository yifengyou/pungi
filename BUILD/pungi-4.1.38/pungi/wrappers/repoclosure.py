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


import os

from kobo.shortcuts import force_list


def get_repoclosure_cmd(backend='yum', arch=None, repos=None, lookaside=None):
    cmds = {
        'yum': {'cmd': ['/usr/bin/repoclosure'], 'repoarg': '--repoid=%s', 'lookaside': '--lookaside=%s'},
        'dnf': {'cmd': ['dnf', 'repoclosure'], 'repoarg': '--repo=%s', 'lookaside': '--repo=%s'},
    }
    try:
        cmd = cmds[backend]['cmd']
    except KeyError:
        raise RuntimeError('Unknown repoclosure backend: %s' % backend)

    # There are options that are not exposed here, because we don't need
    # them.

    for i in force_list(arch or []):
        cmd.append("--arch=%s" % i)

    repos = repos or {}
    for repo_id, repo_path in repos.items():
        cmd.append("--repofrompath=%s,%s" % (repo_id, _to_url(repo_path)))
        cmd.append(cmds[backend]['repoarg'] % repo_id)
        if backend == 'dnf':
            # For dnf we want to add all repos with the --repo option (which
            # enables only those and not any system repo), and the repos to
            # check are also listed with the --check option.
            cmd.append('--check=%s' % repo_id)

    lookaside = lookaside or {}
    for repo_id, repo_path in lookaside.items():
        cmd.append("--repofrompath=%s,%s" % (repo_id, _to_url(repo_path)))
        cmd.append(cmds[backend]['lookaside'] % repo_id)

    return cmd


def _to_url(path):
    if "://" not in path:
        return "file://%s" % os.path.abspath(path)
    return path


def extract_from_fus_log(input, output):
    """Extract depsolver error messages from fus log and write them to output
    file.
    """
    has_error = False
    with open(input) as fin:
        with open(output, "w") as fout:
            for line in fin:
                if line.startswith("Problem ") or line.startswith(" "):
                    fout.write(line)
                    has_error = True
    if has_error:
        raise RuntimeError("Broken dependencies! See %s for details" % output)
