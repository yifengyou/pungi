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
The .discinfo file contains metadata about media.
Following fields are part of the .discinfo file,
one record per line:
- timestamp
- release
- architecture
- disc number (optional)
"""


__all__ = (
    "read_discinfo",
    "write_discinfo",
    "write_media_repo",
)


import os
import time


def write_discinfo(file_path, description, arch, disc_numbers=None, timestamp=None):
    """
    Write a .discinfo file:
    """
    disc_numbers = disc_numbers or ["ALL"]
    if not isinstance(disc_numbers, list):
        raise TypeError(
            "Invalid type: disc_numbers type is %s; expected: <list>"
            % type(disc_numbers)
        )
    if not timestamp:
        timestamp = os.environ.get("SOURCE_DATE_EPOCH", "%f" % time.time())
    with open(file_path, "w") as f:
        f.write("%s\n" % timestamp)
        f.write("%s\n" % description)
        f.write("%s\n" % arch)
        if disc_numbers:
            f.write("%s\n" % ",".join([str(i) for i in disc_numbers]))
    return timestamp


def read_discinfo(file_path):
    result = {}
    with open(file_path, "r") as f:
        result["timestamp"] = f.readline().strip()
        result["description"] = f.readline().strip()
        result["arch"] = f.readline().strip()
        disc_numbers = f.readline().strip()
    if not disc_numbers:
        result["disc_numbers"] = None
    elif disc_numbers == "ALL":
        result["disc_numbers"] = ["ALL"]
    else:
        result["disc_numbers"] = [int(i) for i in disc_numbers.split(",")]
    return result


def write_media_repo(file_path, description, timestamp):
    """
    Write media.repo file for the disc to be used on installed system.
    PackageKit uses this.
    """
    data = [
        "[InstallMedia]",
        "name=%s" % description,
        "mediaid=%s" % timestamp,
        "metadata_expire=-1",
        "gpgcheck=0",
        "cost=500",
        "",
    ]

    with open(file_path, "w") as repo_file:
        repo_file.write("\n".join(data))
    return timestamp
