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
from kobo import shortcuts

from .base import OSTree
from ..wrappers import lorax


class Installer(OSTree):
    def _merge_config(self, config):
        self.installpkgs.extend(config.get('installpkgs', []))
        self.add_template.extend(config.get("add_template", []))
        self.add_template_var.extend(config.get("add_template_var"))
        self.add_arch_template.extend(config.get("add_arch_template", []))
        self.add_arch_template_var.extend(config.get("add_arch_template_var", []))

    def run(self):
        self.product = self.args.product
        self.version = self.args.version
        self.release = self.args.release
        self.sources = self.args.source
        self.output = self.args.output

        self.logdir = self.args.log_dir
        self.volid = self.args.volid
        self.variant = self.args.variant
        self.rootfs_size = self.args.rootfs_size
        self.nomacboot = self.args.nomacboot
        self.noupgrade = self.args.noupgrade
        self.isfinal = self.args.isfinal

        self.installpkgs = self.args.installpkgs or []
        self.add_template = self.args.add_template or []
        self.add_template_var = self.args.add_template_var or []
        self.add_arch_template = self.args.add_arch_template or []
        self.add_arch_template_var = self.args.add_arch_template_var or []

        self.extra_config = self.args.extra_config
        if self.extra_config:
            self.extra_config = json.load(open(self.extra_config, 'r'))
            self._merge_config(self.extra_config)

        lorax_wrapper = lorax.LoraxWrapper()
        cmd = lorax_wrapper.get_lorax_cmd(
            self.product,
            self.version,
            self.release,
            self.sources,
            self.output,
            variant=self.variant,
            nomacboot=self.nomacboot,
            volid=self.volid,
            buildinstallpackages=self.installpkgs,
            add_template=self.add_template,
            add_template_var=self.add_template_var,
            add_arch_template=self.add_arch_template,
            add_arch_template_var=self.add_arch_template_var,
            rootfs_size=self.rootfs_size,
            is_final=self.isfinal,
            log_dir=self.logdir
        )
        shortcuts.run(cmd)
