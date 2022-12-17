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


import json
import logging
import os
import shutil

import yaml

from pungi.arch_utils import getBaseArch
from pungi.util import makedirs


def make_log_file(log_dir, filename):
    """Return path to log file with given name, if log_dir is set."""
    if not log_dir:
        return None
    makedirs(log_dir)
    return os.path.join(log_dir, "%s.log" % filename)


def get_ref_from_treefile(treefile, arch=None, logger=None):
    """
    Return ref name by parsing the tree config file. Replacing ${basearch} with
    the basearch of the architecture we are running on or of the passed in arch.
    """
    logger = logger or logging.getLogger(__name__)
    if os.path.isfile(treefile):
        with open(treefile, "r") as f:
            try:
                # rpm-ostree now supports YAML
                #   https://github.com/projectatomic/rpm-ostree/pull/1377
                if treefile.endswith(".yaml"):
                    parsed = yaml.safe_load(f)
                else:
                    parsed = json.load(f)
                return parsed["ref"].replace("${basearch}", getBaseArch(arch))
            except Exception as e:
                logger.error("Unable to get ref from treefile: %s" % e)
    else:
        logger.error("Unable to open treefile")
    return None


def get_commitid_from_commitid_file(commitid_file):
    """Return commit id which is read from the commitid file"""
    if not os.path.exists(commitid_file + ".stamp"):
        # The stamp does not exist, so no new commit.
        return None
    with open(commitid_file, "r") as f:
        return f.read().replace("\n", "")


def tweak_treeconf(
    treeconf, source_repos=None, keep_original_sources=False, update_dict=None
):
    """
    Update tree config file by adding new repos, and remove existing repos
    from the tree config file if 'keep_original_sources' is not enabled.
    Additionally, other values can be passed to method by 'update_dict' parameter to
    update treefile content.
    """

    # backup the old tree config
    shutil.copy2(treeconf, "{0}.bak".format(treeconf))

    treeconf_dir = os.path.dirname(treeconf)
    with open(treeconf, "r") as f:
        # rpm-ostree now supports YAML, but we'll end up converting it to JSON.
        # https://github.com/projectatomic/rpm-ostree/pull/1377
        if treeconf.endswith(".yaml"):
            treeconf_content = yaml.safe_load(f)
            treeconf = treeconf.replace(".yaml", ".json")
        else:
            treeconf_content = json.load(f)

    repos = []
    if source_repos:
        # Sort to ensure reliable ordering
        source_repos = sorted(source_repos, key=lambda x: x["name"])
        # Now, since pungi includes timestamps in the repo names which
        # currently defeats rpm-ostree's change detection, let's just
        # use repos named 'repo-<number>'.
        # https://pagure.io/pungi/issue/811
        with open("{0}/pungi.repo".format(treeconf_dir), "w") as f:
            for i, repo in enumerate(source_repos):
                name = "repo-{0}".format(i)
                f.write("[%s]\n" % name)
                f.write("name=%s\n" % name)
                f.write("baseurl=%s\n" % repo["baseurl"])
                exclude = repo.get("exclude", None)
                if exclude:
                    f.write("exclude=%s\n" % exclude)
                gpgcheck = "1" if repo.get("gpgcheck", False) else "0"
                f.write("gpgcheck=%s\n" % gpgcheck)

                repos.append(name)

    original_repos = treeconf_content.get("repos", [])
    if keep_original_sources:
        treeconf_content["repos"] = original_repos + repos
    else:
        treeconf_content["repos"] = repos

    # update content with config values from dictionary (for example 'ref')
    if isinstance(update_dict, dict):
        treeconf_content.update(update_dict)

    # update tree config to add new repos
    with open(treeconf, "w") as f:
        json.dump(treeconf_content, f, indent=4)
    return treeconf
