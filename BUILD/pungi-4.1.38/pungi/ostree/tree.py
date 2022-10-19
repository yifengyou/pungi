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
import json
from kobo import shortcuts

from pungi.util import makedirs
from .base import OSTree
from .utils import (make_log_file, tweak_treeconf,
                    get_ref_from_treefile, get_commitid_from_commitid_file)


class Tree(OSTree):
    def _make_tree(self):
        """Compose OSTree tree"""
        log_file = make_log_file(self.logdir, 'create-ostree-repo')
        cmd = [
            "rpm-ostree",
            "compose",
            "tree",
            "--repo=%s" % self.repo,
            "--write-commitid-to=%s" % self.commitid_file,
            # Touch the file if a new commit was created. This can help us tell
            # if the commitid file is missing because no commit was created or
            # because something went wrong.
            "--touch-if-changed=%s.stamp" % self.commitid_file,
        ]
        if self.version:
            # Add versioning metadata
            cmd.append('--add-metadata-string=version=%s' % self.version)
        # Note renamed from rpm-ostree --force-nocache since it's a better
        # name; more clearly describes what we're doing here.
        if self.force_new_commit:
            cmd.append('--force-nocache')
        cmd.append(self.treefile)

        shortcuts.run(cmd, show_cmd=True, stdout=True, logfile=log_file)

    def _update_summary(self):
        """Update summary metadata"""
        log_file = make_log_file(self.logdir, 'ostree-summary')
        shortcuts.run(['ostree', 'summary', '-u', '--repo=%s' % self.repo],
                      show_cmd=True, stdout=True, logfile=log_file)

    def _update_ref(self):
        """
        Update the ref.

        '--write-commitid-to' is specified when compose the tree, so we need
        to update the ref by ourselves. ref is retrieved from treefile and
        commitid is retrieved from the committid file.
        """
        tag_ref = True
        if self.extra_config:
            tag_ref = self.extra_config.get('tag_ref', True)
        if not tag_ref:
            print('Not updating ref as configured')
            return
        ref = get_ref_from_treefile(self.treefile)
        commitid = get_commitid_from_commitid_file(self.commitid_file)
        print('Ref: %r, Commit ID: %r' % (ref, commitid))
        if ref and commitid:
            print('Updating ref')
            # Let's write the tag out ourselves
            heads_dir = os.path.join(self.repo, 'refs', 'heads')
            if not os.path.exists(heads_dir):
                raise RuntimeError('Refs/heads did not exist in ostree repo')

            ref_path = os.path.join(heads_dir, ref)
            makedirs(os.path.dirname(ref_path))
            with open(ref_path, 'w') as f:
                f.write(commitid + '\n')

    def run(self):
        self.repo = self.args.repo
        self.treefile = self.args.treefile
        self.version = self.args.version
        self.logdir = self.args.log_dir
        self.update_summary = self.args.update_summary
        self.extra_config = self.args.extra_config
        self.ostree_ref = self.args.ostree_ref
        self.force_new_commit = self.args.force_new_commit

        if self.extra_config or self.ostree_ref:
            if self.extra_config:
                self.extra_config = json.load(open(self.extra_config, 'r'))
                repos = self.extra_config.get('repo', [])
                keep_original_sources = self.extra_config.get('keep_original_sources', False)
            else:
                # missing extra_config mustn't affect tweak_treeconf call
                repos = []
                keep_original_sources = True

            update_dict = {}
            if self.ostree_ref:
                # override ref value in treefile
                update_dict['ref'] = self.ostree_ref

            self.treefile = tweak_treeconf(
                self.treefile,
                source_repos=repos,
                keep_original_sources=keep_original_sources,
                update_dict=update_dict
            )

        self.commitid_file = make_log_file(self.logdir, 'commitid')

        self._make_tree()
        self._update_ref()
        if self.update_summary:
            self._update_summary()
