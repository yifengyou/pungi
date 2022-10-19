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


SIZE_UNITS = {
    "b": 1,
    "k": 1024,
    "M": 1024 ** 2,
    "G": 1024 ** 3,
}


def convert_media_size(size):
    if isinstance(size, str):
        if size[-1] in SIZE_UNITS:
            num = int(size[:-1])
            units = size[-1]
        else:
            num = int(size)
            units = "b"
        result = num * SIZE_UNITS[units]
    else:
        result = int(size)

    if result <= 0:
        raise ValueError("Media size must be a positive number: %s" % size)

    return result


def convert_file_size(size, block_size=2048):
    """round file size to block"""
    blocks = int(size / block_size)
    if size % block_size:
        blocks += 1
    return blocks * block_size


class MediaSplitter(object):
    """
    MediaSplitter splits files so that they fit on a media of given size.

    Each file added to the spliter has a size in bytes that will be rounded to
    the nearest multiple of block size. If the file is sticky, it will be
    included on each disk. The files will be on disks in the same order they
    are added; there is no re-ordering. The number of disk is thus not the
    possible minimum.
    """
    def __init__(self, media_size, compose=None, logger=None):
        self.media_size = media_size
        self.files = []  # to preserve order
        self.file_sizes = {}
        self.sticky_files = set()
        self.compose = compose
        self.logger = logger
        if not self.logger and self.compose:
            self.logger = self.compose._logger

    def add_file(self, name, size, sticky=False):
        name = os.path.normpath(name)
        size = int(size)
        old_size = self.file_sizes.get(name, None)

        if old_size is not None and old_size != size:
            raise ValueError("File size mismatch; file: %s; sizes: %s vs %s" % (name, old_size, size))
        if self.media_size and size > self.media_size:
            raise ValueError("File is larger than media size: %s" % name)

        self.files.append(name)
        self.file_sizes[name] = size
        if sticky:
            self.sticky_files.add(name)

    @property
    def total_size(self):
        return sum(self.file_sizes.values())

    @property
    def total_size_in_blocks(self):
        return sum([convert_file_size(i) for i in list(self.file_sizes.values())])

    def split(self, first_disk=0, all_disks=0):
        all_files = []
        sticky_files = []
        sticky_files_size = 0

        for name in self.files:
            if name in self.sticky_files:
                sticky_files.append(name)
                sticky_files_size += convert_file_size(self.file_sizes[name])
            else:
                all_files.append(name)

        disks = []
        disk = {}
        # as it would be on single medium (sticky_files just once)
        total_size_single = sticky_files_size
        while all_files:
            name = all_files.pop(0)
            size = convert_file_size(self.file_sizes[name])

            if not disks or (self.media_size and disk["size"] + size > self.media_size):
                disk = {"size": sticky_files_size, "files": sticky_files[:]}
                disks.append(disk)

            disk["files"].append(name)
            disk["size"] += size
            total_size_single += size
        if self.compose:
            if self.media_size:
                self.logger.debug("MediaSplitter: free space on single media would be %s. "
                                  "Total size of single medium: %s."
                                  % (self.media_size - total_size_single, total_size_single))
            else:
                self.logger.debug("MediaSplitter: Total size of single medium: %s." % total_size_single)
        return disks
