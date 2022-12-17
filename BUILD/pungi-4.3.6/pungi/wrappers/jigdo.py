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

import kobo.log
from kobo.shortcuts import force_list


class JigdoWrapper(kobo.log.LoggingBase):
    def get_jigdo_cmd(
        self, image, files, output_dir, cache=None, no_servers=False, report=None
    ):
        """
        files: [{"path", "label", "uri"}]
        """
        cmd = ["jigdo-file", "make-template"]

        cmd.append("--force")  # overrides existing template
        image = os.path.abspath(image)
        cmd.append("--image=%s" % image)

        output_dir = os.path.abspath(output_dir)
        jigdo_file = os.path.join(output_dir, os.path.basename(image)) + ".jigdo"
        cmd.append("--jigdo=%s" % jigdo_file)

        template_file = os.path.join(output_dir, os.path.basename(image)) + ".template"
        cmd.append("--template=%s" % template_file)

        if cache:
            cache = os.path.abspath(cache)
            cmd.append("--cache=%s" % cache)

        if no_servers:
            cmd.append("--no-servers-section")

        if report:
            cmd.append("--report=%s" % report)

        for i in force_list(files):
            # double-slash magic; read man jigdo-file
            if isinstance(i, str):
                i = {"path": i}
            path = os.path.abspath(i["path"]).rstrip("/") + "//"
            cmd.append(path)

            label = i.get("label", None)
            if label is not None:
                cmd.append("--label=%s=%s" % (label, path.rstrip("/")))

            uri = i.get("uri", None)
            if uri is not None:
                cmd.append("--uri=%s=%s" % (label, uri))

        return cmd
