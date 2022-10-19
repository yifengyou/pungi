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


__all__ = (
    "Paths",
)


import errno
import os

from pungi.util import makedirs


class Paths(object):
    def __init__(self, compose):
        paths_module_name = compose.conf.get("paths_module")
        if paths_module_name:
            # custom paths
            paths_module = __import__(paths_module_name, globals(), locals(), ["LogPaths", "WorkPaths", "ComposePaths"])
            self.compose = paths_module.ComposePaths(compose)
            self.log = paths_module.LogPaths(compose)
            self.work = paths_module.WorkPaths(compose)
        else:
            # default paths
            self.compose = ComposePaths(compose)
            self.log = LogPaths(compose)
            self.work = WorkPaths(compose)
        # self.metadata ?


class LogPaths(object):
    def __init__(self, compose):
        self.compose = compose

    def topdir(self, arch=None, create_dir=True):
        """
        Examples:
            log/global
            log/x86_64
        """
        arch = arch or "global"
        path = os.path.join(self.compose.topdir, "logs", arch)
        if create_dir:
            makedirs(path)
        return path

    def log_file(self, arch, log_name, create_dir=True):
        arch = arch or "global"
        if log_name.endswith(".log"):
            log_name = log_name[:-4]
        return os.path.join(self.topdir(arch, create_dir=create_dir), "%s.%s.log" % (log_name, arch))


class WorkPaths(object):
    def __init__(self, compose):
        self.compose = compose

    def topdir(self, arch=None, create_dir=True):
        """
        Examples:
            work/global
            work/x86_64
        """
        arch = arch or "global"
        path = os.path.join(self.compose.topdir, "work", arch)
        if create_dir:
            makedirs(path)
        return path

    def variants_file(self, arch=None, create_dir=True):
        """
        Examples:
            work/global/variants.xml
        """
        arch = "global"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "variants.xml")
        return path

    def comps(self, arch=None, variant=None, create_dir=True):
        """
        Examples:
            work/x86_64/comps/comps-86_64.xml
            work/x86_64/comps/comps-Server.x86_64.xml
        """
        arch = arch or "global"
        if variant is None:
            file_name = "comps-%s.xml" % arch
        else:
            file_name = "comps-%s.%s.xml" % (variant.uid, arch)
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "comps")
        if create_dir:
            makedirs(path)
        path = os.path.join(path, file_name)
        return path

    def pungi_conf(self, arch=None, variant=None, create_dir=True, source_name=None):
        """
        Examples:
            work/x86_64/pungi/x86_64.conf
            work/x86_64/pungi/Server.x86_64.conf
        """
        arch = arch or "global"
        file_name = ''
        if variant:
            file_name += variant.uid + '.'
        file_name += arch + '.'
        if source_name:
            file_name += source_name + '.'
        file_name += 'conf'
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "pungi")
        if create_dir:
            makedirs(path)
        path = os.path.join(path, file_name)
        return path

    def fus_conf(self, arch, variant, iteration, create_dir=True):
        """
        Examples:
            work/x86_64/fus/Server-solvables.x86_64.conf
        """
        file_name = "%s-solvables-%d.%s.conf" % (variant.uid, iteration, arch)
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "fus")
        if create_dir:
            makedirs(path)
        return os.path.join(path, file_name)

    def pungi_log(self, arch=None, variant=None, create_dir=True, source_name=None):
        """
        Examples:
            work/x86_64/pungi/x86_64.log
            work/x86_64/pungi/Server.x86_64.log
        """
        path = self.pungi_conf(arch, variant, create_dir=create_dir)
        path = path[:-5]
        if source_name:
            path += '.' + source_name
        return path + ".log"

    def pungi_cache_dir(self, arch, variant=None, create_dir=True):
        """
        Examples:
            work/global/pungi-cache
        """
        # WARNING: Using the same cache dir with repos of the same names may lead to a race condition
        # We should use per arch variant cache dirs to workaround this.
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "pungi-cache")
        if variant:
            path = os.path.join(path, variant.uid)
        if create_dir:
            makedirs(path)
        return path

    def _repo(self, type, arch=None, variant=None, create_dir=True):
        arch = arch or "global"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "%s_repo" % type)
        if variant:
            path += "_" + variant.uid
        if create_dir:
            makedirs(path)
        return path

    def comps_repo(self, arch=None, variant=None, create_dir=True):
        """
        Examples:
            work/x86_64/comps_repo_Server
            work/global/comps_repo
        """
        return self._repo("comps", arch, variant, create_dir=create_dir)

    def arch_repo(self, arch=None, create_dir=True):
        """
        Examples:
            work/x86_64/repo
            work/global/repo
        """
        arch = arch or "global"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "repo")
        if create_dir:
            makedirs(path)
        return path

    def lookaside_repo(self, arch, variant, create_dir=True):
        """
        Examples:
            work/x86_64/Server/lookaside_repo
        """
        path = os.path.join(self.topdir(arch, create_dir=create_dir),
                            variant.uid, "lookaside_repo")
        if create_dir:
            makedirs(path)
        return path

    def package_list(self, arch=None, variant=None, pkg_type=None, create_dir=True):
        """
        Examples:
            work/x86_64/package_list/x86_64.conf
            work/x86_64/package_list/Server.x86_64.conf
            work/x86_64/package_list/Server.x86_64.rpm.conf
        """
        arch = arch or "global"
        if variant is not None:
            file_name = "%s.%s" % (variant, arch)
        else:
            file_name = "%s" % arch
        if pkg_type is not None:
            file_name += ".%s" % pkg_type
        file_name += ".conf"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "package_list")
        if create_dir:
            makedirs(path)
        path = os.path.join(path, file_name)
        return path

    def lookaside_package_list(self, arch, variant, create_dir=True):
        """
        Examples:
            work/x86_64/package_list/Server.x86_64.lookaside.conf
        """
        return self.package_list(arch, variant, pkg_type='lookaside', create_dir=create_dir)

    def pungi_download_dir(self, arch, create_dir=True):
        """
        Examples:
            work/x86_64/pungi_download
        """
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "pungi_download")
        if create_dir:
            makedirs(path)
        return path

    def buildinstall_dir(self, arch, create_dir=True,
                         allow_topdir_override=False, variant=None):
        """
        :param bool allow_topdir_override: When True, the
            "buildinstall_topdir" will be used (if set) instead of real
            "topdir".
        Examples:
            work/x86_64/buildinstall
        """
        if arch == "global":
            raise RuntimeError("Global buildinstall dir makes no sense.")

        buildinstall_topdir = self.compose.conf.get("buildinstall_topdir", "")
        if allow_topdir_override and buildinstall_topdir:
            topdir_basename = os.path.basename(self.compose.topdir)
            path = os.path.join(
                buildinstall_topdir, "buildinstall-%s" % topdir_basename, arch)
        else:
            path = os.path.join(self.topdir(arch, create_dir=create_dir), "buildinstall")

        if variant:
            path = os.path.join(path, variant.uid)
        return path

    def extra_files_dir(self, arch, variant, create_dir=True):
        """
        Examples:
            work/x86_64/Server/extra-files
        """
        if arch == "global":
            raise RuntimeError("Global extra files dir makes no sense.")
        path = os.path.join(self.topdir(arch, create_dir=create_dir), variant.uid, "extra-files")
        if create_dir:
            makedirs(path)
        return path

    def extra_iso_extra_files_dir(self, arch, variant, create_dir=True):
        """
        Examples:
            work/x86_64/Server/extra-iso-extra-files
        """
        if arch == "global":
            raise RuntimeError("Global extra files dir makes no sense.")
        path = os.path.join(self.topdir(arch, create_dir=create_dir), variant.uid, "extra-iso-extra-files")
        if create_dir:
            makedirs(path)
        return path

    def iso_staging_dir(self, arch, variant, filename, create_dir=True):
        """
        Examples:
            work/x86_64/Server/iso-staging-dir/file.iso/
        """
        path = os.path.join(
            self.topdir(arch, create_dir=create_dir),
            variant.uid,
            "iso-staging-dir",
            filename
        )
        if create_dir:
            makedirs(path)
        return path

    def repo_package_list(self, arch, variant, pkg_type=None, create_dir=True):
        """
        Examples:
            work/x86_64/repo_package_list/Server.x86_64.rpm.conf
        """
        file_name = "%s.%s" % (variant.uid, arch)
        if pkg_type is not None:
            file_name += ".%s" % pkg_type
        file_name += ".conf"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "repo_package_list")
        if create_dir:
            makedirs(path)
        path = os.path.join(path, file_name)
        return path

    def product_img(self, variant, create_dir=True):
        """
        Examples:
            work/global/product-Server.img
        """
        file_name = "product-%s.img" % variant
        path = self.topdir(arch="global", create_dir=create_dir)
        path = os.path.join(path, file_name)
        return path

    def iso_dir(self, arch, filename, create_dir=True):
        """
        Examples:
            work/x86_64/iso/Project-1.0-20151203.0-Client-x86_64-dvd1.iso
        """
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "iso", filename)
        if create_dir:
            makedirs(path)
        return path

    def tmp_dir(self, arch=None, variant=None, create_dir=True):
        """
        Examples:
            work/global/tmp
            work/x86_64/tmp
            work/x86_64/tmp-Server
        """
        dir_name = "tmp"
        if variant:
            dir_name += "-%s" % variant.uid
        path = os.path.join(self.topdir(arch=arch, create_dir=create_dir), dir_name)
        if create_dir:
            makedirs(path)
        return path

    def product_id(self, arch, variant, create_dir=True):
        """
        Examples:
            work/x86_64/product_id/productid-Server.x86_64.pem/productid
        """
        # file_name = "%s.%s.pem" % (variant, arch)
        # HACK: modifyrepo doesn't handle renames -> $dir/productid
        file_name = "productid"
        path = os.path.join(self.topdir(arch, create_dir=create_dir), "product_id", "%s.%s.pem" % (variant, arch))
        if create_dir:
            makedirs(path)
        path = os.path.join(path, file_name)
        return path

    def image_build_dir(self, variant, create_dir=True):
        """
        @param variant
        @param create_dir=True

        Examples:
            work/image-build/Server
        """
        path = os.path.join(self.topdir('image-build', create_dir=create_dir), variant.uid)
        if create_dir:
            makedirs(path)
        return path

    def image_build_conf(self, variant, image_name, image_type, arches=None, create_dir=True):
        """
        @param variant
        @param image-name
        @param image-type (e.g docker)
        @param arches
        @param create_dir=True

        Examples:
            work/image-build/Server/docker_rhel-server-docker.cfg
            work/image-build/Server/docker_rhel-server-docker_x86_64.cfg
            work/image-build/Server/docker_rhel-server-docker_x86_64-ppc64le.cfg
        """
        path = os.path.join(self.image_build_dir(variant), "%s_%s" % (image_type, image_name))
        if arches is not None:
            path = "%s_%s" % (path, '-'.join(list(arches)))
        path = "%s.cfg" % path
        return path

    def module_defaults_dir(self, create_dir=True):
        """
        """
        path = os.path.join(self.topdir(create_dir=create_dir), 'module_defaults')
        if create_dir:
            makedirs(path)
        return path

    def pkgset_file_cache(self):
        """
        Returns the path to file in which the cached version of
        PackageSetBase.file_cache should be stored.
        """
        return os.path.join(
            self.topdir(arch="global"), "pkgset_file_cache.pickle")


class ComposePaths(object):
    def __init__(self, compose):
        self.compose = compose
        # TODO: TREES?

    def topdir(self, arch=None, variant=None, create_dir=True, relative=False):
        """
        Examples:
            compose
            compose/Server/x86_64
        """
        if bool(arch) != bool(variant):
            raise TypeError("topdir(): either none or 2 arguments are expected")

        path = ""
        if not relative:
            path = os.path.join(self.compose.topdir, "compose")

        if arch or variant:
            if variant.type == "addon":
                return self.topdir(arch, variant.parent, create_dir=create_dir, relative=relative)
            path = os.path.join(path, variant.uid, arch)
        if create_dir and not relative:
            makedirs(path)
        return path

    def tree_dir(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/os
            compose/Server-optional/x86_64/os
        """
        if arch == "src":
            arch = "source"

        if arch == "source":
            tree_dir = "tree"
        else:
            # use 'os' dir due to historical reasons
            tree_dir = "os"

        path = os.path.join(self.topdir(arch, variant, create_dir=create_dir, relative=relative), tree_dir)
        if create_dir and not relative:
            makedirs(path)
        return path

    def os_tree(self, arch, variant, create_dir=True, relative=False):
        return self.tree_dir(arch, variant, create_dir=create_dir, relative=relative)

    def repository(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/os
            compose/Server/x86_64/addons/LoadBalancer
        """
        if variant.type == "addon":
            path = self.packages(arch, variant, create_dir=create_dir, relative=relative)
        else:
            path = self.tree_dir(arch, variant, create_dir=create_dir, relative=relative)
        if create_dir and not relative:
            makedirs(path)
        return path

    def packages(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/os/Packages
            compose/Server/x86_64/os/addons/LoadBalancer
            compose/Server-optional/x86_64/os/Packages
        """
        if variant.type == "addon":
            path = os.path.join(self.tree_dir(arch, variant, create_dir=create_dir, relative=relative), "addons", variant.id)
        else:
            path = os.path.join(self.tree_dir(arch, variant, create_dir=create_dir, relative=relative), "Packages")
        if create_dir and not relative:
            makedirs(path)
        return path

    def debug_topdir(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/debug
            compose/Server-optional/x86_64/debug
        """
        path = os.path.join(self.topdir(arch, variant, create_dir=create_dir, relative=relative), "debug")
        if create_dir and not relative:
            makedirs(path)
        return path

    def debug_tree(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/debug/tree
            compose/Server-optional/x86_64/debug/tree
        """
        path = os.path.join(self.debug_topdir(arch, variant, create_dir=create_dir, relative=relative), "tree")
        if create_dir and not relative:
            makedirs(path)
        return path

    def debug_packages(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/debug/tree/Packages
            compose/Server/x86_64/debug/tree/addons/LoadBalancer
            compose/Server-optional/x86_64/debug/tree/Packages
        """
        if arch in ("source", "src"):
            return None
        if variant.type == "addon":
            path = os.path.join(self.debug_tree(arch, variant, create_dir=create_dir, relative=relative), "addons", variant.id)
        else:
            path = os.path.join(self.debug_tree(arch, variant, create_dir=create_dir, relative=relative), "Packages")
        if create_dir and not relative:
            makedirs(path)
        return path

    def debug_repository(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/debug/tree
            compose/Server/x86_64/debug/tree/addons/LoadBalancer
            compose/Server-optional/x86_64/debug/tree
        """
        if arch in ("source", "src"):
            return None
        if variant.type == "addon":
            path = os.path.join(self.debug_tree(arch, variant, create_dir=create_dir, relative=relative), "addons", variant.id)
        else:
            path = self.debug_tree(arch, variant, create_dir=create_dir, relative=relative)
        if create_dir and not relative:
            makedirs(path)
        return path

    def iso_dir(self, arch, variant, symlink_to=None, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/iso
            None
        """
        if variant.type == "addon":
            return None
        if variant.type == "optional":
            if not self.compose.conf.get("create_optional_isos", False):
                return None
        if arch == "src":
            arch = "source"
        path = os.path.join(self.topdir(arch, variant, create_dir=create_dir, relative=relative), "iso")

        if symlink_to:
            # TODO: create_dir
            topdir = self.compose.topdir.rstrip("/") + "/"
            relative_dir = path[len(topdir):]
            target_dir = os.path.join(symlink_to, self.compose.compose_id, relative_dir)
            if create_dir and not relative:
                makedirs(target_dir)
            try:
                os.symlink(target_dir, path)
            except OSError as ex:
                if ex.errno != errno.EEXIST:
                    raise
                msg = "Symlink pointing to '%s' expected: %s" % (target_dir, path)
                if not os.path.islink(path):
                    raise RuntimeError(msg)
                if os.path.abspath(os.readlink(path)) != target_dir:
                    raise RuntimeError(msg)
        else:
            if create_dir and not relative:
                makedirs(path)
        return path

    def iso_path(self, arch, variant, filename, symlink_to=None, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/iso/rhel-7.0-20120127.0-Server-x86_64-dvd1.iso
            None
        """
        path = self.iso_dir(arch, variant, symlink_to=symlink_to, create_dir=create_dir, relative=relative)
        if path is None:
            return None

        return os.path.join(path, filename)

    def image_dir(self, variant, symlink_to=None, relative=False):
        """
        The arch is listed as literal '%(arch)s'
        Examples:
            compose/Server/%(arch)s/images
            None
        @param variant
        @param symlink_to=None
        @param relative=False
        """
        path = os.path.join(self.topdir('%(arch)s', variant, create_dir=False, relative=relative),
                            "images")
        if symlink_to:
            topdir = self.compose.topdir.rstrip("/") + "/"
            relative_dir = path[len(topdir):]
            target_dir = os.path.join(symlink_to, self.compose.compose_id, relative_dir)
            try:
                os.symlink(target_dir, path)
            except OSError as ex:
                if ex.errno != errno.EEXIST:
                    raise
                msg = "Symlink pointing to '%s' expected: %s" % (target_dir, path)
                if not os.path.islink(path):
                    raise RuntimeError(msg)
                if os.path.abspath(os.readlink(path)) != target_dir:
                    raise RuntimeError(msg)
        return path

    def jigdo_dir(self, arch, variant, create_dir=True, relative=False):
        """
        Examples:
            compose/Server/x86_64/jigdo
            None
        """
        if variant.type == "addon":
            return None
        if variant.type == "optional":
            if not self.compose.conf.get("create_optional_isos", False):
                return None
        if arch == "src":
            arch = "source"
        path = os.path.join(self.topdir(arch, variant, create_dir=create_dir, relative=relative), "jigdo")

        if create_dir and not relative:
            makedirs(path)
        return path

    def metadata(self, file_name=None, create_dir=True, relative=False):
        """
        Examples:
            compose/metadata
            compose/metadata/rpms.json
        """
        path = os.path.join(self.topdir(create_dir=create_dir, relative=relative), "metadata")
        if create_dir and not relative:
            makedirs(path)
        if file_name:
            path = os.path.join(path, file_name)
        return path
