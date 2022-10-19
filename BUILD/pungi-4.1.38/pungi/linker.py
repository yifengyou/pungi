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


import contextlib
import errno
import os
import shutil

import kobo.log
from kobo.shortcuts import relative_path
from kobo.threads import WorkerThread, ThreadPool

from pungi.util import makedirs


class LinkerPool(ThreadPool):
    def __init__(self, link_type="hardlink-or-copy", logger=None):
        ThreadPool.__init__(self, logger)
        self.link_type = link_type
        self.linker = Linker()

    @classmethod
    def with_workers(cls, num_workers, *args, **kwargs):
        pool = cls(*args, **kwargs)
        for _ in range(num_workers):
            pool.add(LinkerThread(pool))
        return pool


@contextlib.contextmanager
def linker_pool(link_type="hardlink-or-copy", num_workers=10):
    """Create a linker and make sure it is stopped no matter what."""
    linker = LinkerPool.with_workers(num_workers=num_workers, link_type=link_type)
    linker.start()
    try:
        yield linker
    finally:
        linker.stop()


class LinkerThread(WorkerThread):
    def process(self, item, num):
        src, dst = item

        if (num % 100 == 0) or (num == self.pool.queue_total):
            self.pool.log_debug("Linked %s out of %s packages" % (num, self.pool.queue_total))

        directory = os.path.dirname(dst)
        makedirs(directory)
        self.pool.linker.link(src, dst, link_type=self.pool.link_type)


class Linker(kobo.log.LoggingBase):
    def __init__(self, always_copy=None, test=False, logger=None):
        kobo.log.LoggingBase.__init__(self, logger=logger)
        self.always_copy = always_copy or []
        self.test = test
        self._inode_map = {}

    def _is_same_type(self, path1, path2):
        if not os.path.islink(path1) == os.path.islink(path2):
            return False
        if not os.path.isdir(path1) == os.path.isdir(path2):
            return False
        if not os.path.isfile(path1) == os.path.isfile(path2):
            return False
        return True

    def _is_same(self, path1, path2):
        if path1 == path2:
            return True
        if os.path.islink(path2) and not os.path.exists(path2):
            # Broken symlink
            return True
        if os.path.getsize(path1) != os.path.getsize(path2):
            return False
        if int(os.path.getmtime(path1)) != int(os.path.getmtime(path2)):
            return False
        return True

    def symlink(self, src, dst, relative=True):
        if src == dst:
            return

        old_src = src
        if relative:
            src = relative_path(src, dst)

        msg = "Symlinking %s -> %s" % (dst, src)
        if self.test:
            self.log_info("TEST: %s" % msg)
            return
        self.log_info(msg)

        try:
            os.symlink(src, dst)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise
            if os.path.islink(dst) and self._is_same(old_src, dst):
                if os.readlink(dst) != src:
                    raise
                self.log_debug("The same file already exists, skipping symlink %s -> %s" % (dst, src))
            else:
                raise

    def hardlink(self, src, dst):
        if src == dst:
            return

        msg = "Hardlinking %s to %s" % (src, dst)
        if self.test:
            self.log_info("TEST: %s" % msg)
            return
        self.log_info(msg)

        try:
            os.link(src, dst)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise
            if self._is_same(src, dst):
                if not self._is_same_type(src, dst):
                    self.log_error("File %s already exists but has different type than %s" % (dst, src))
                    raise
                self.log_debug("The same file already exists, skipping hardlink %s to %s" % (src, dst))
            else:
                raise

    def copy(self, src, dst):
        if src == dst:
            return True

        if os.path.islink(src):
            msg = "Copying symlink %s to %s" % (src, dst)
        else:
            msg = "Copying file %s to %s" % (src, dst)

        if self.test:
            self.log_info("TEST: %s" % msg)
            return
        self.log_info(msg)

        if os.path.exists(dst):
            if self._is_same(src, dst):
                if not self._is_same_type(src, dst):
                    self.log_error("File %s already exists but has different type than %s" % (dst, src))
                    raise OSError(errno.EEXIST, "File exists")
                self.log_debug("The same file already exists, skipping copy %s to %s" % (src, dst))
                return
            else:
                raise OSError(errno.EEXIST, "File exists")

        if os.path.islink(src):
            if not os.path.islink(dst):
                os.symlink(os.readlink(src), dst)
                return
            return

        src_stat = os.stat(src)
        src_key = (src_stat.st_dev, src_stat.st_ino)
        if src_key in self._inode_map:
            # (st_dev, st_ino) found in the mapping
            self.log_debug("Harlink detected, hardlinking in destination %s to %s" % (self._inode_map[src_key], dst))
            os.link(self._inode_map[src_key], dst)
            return

        # BEWARE: shutil.copy2 automatically *rewrites* existing files
        shutil.copy2(src, dst)
        self._inode_map[src_key] = dst

        if not self._is_same(src, dst):
            self.log_error("File %s doesn't match the copied file %s" % (src, dst))
            # XXX:
            raise OSError(errno.EEXIST, "File exists")

    def _link_file(self, src, dst, link_type):
        if link_type == "hardlink":
            self.hardlink(src, dst)
        elif link_type == "copy":
            self.copy(src, dst)
        elif link_type in ("symlink", "abspath-symlink"):
            if os.path.islink(src):
                self.copy(src, dst)
            else:
                relative = link_type != "abspath-symlink"
                self.symlink(src, dst, relative)
        elif link_type == "hardlink-or-copy":
            src_stat = os.stat(src)
            dst_stat = os.stat(os.path.dirname(dst))
            if src_stat.st_dev == dst_stat.st_dev:
                self.hardlink(src, dst)
            else:
                self.copy(src, dst)
        else:
            raise ValueError("Unknown link_type: %s" % link_type)

    def link(self, src, dst, link_type="hardlink-or-copy"):
        """Link directories recursively."""
        if os.path.isfile(src) or os.path.islink(src):
            self._link_file(src, dst, link_type)
            return

        if os.path.isfile(dst):
            raise OSError(errno.EEXIST, "File exists")

        if not self.test:
            if not os.path.exists(dst):
                makedirs(dst)
            shutil.copystat(src, dst)

        for i in os.listdir(src):
            src_path = os.path.join(src, i)
            dst_path = os.path.join(dst, i)
            self.link(src_path, dst_path, link_type)
