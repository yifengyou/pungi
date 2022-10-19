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


import re
import fnmatch

import pungi.pathmatch
import pungi.gather
import pungi.util


LINE_PATTERN_RE = re.compile(r"^\s*(?P<line>[^#]+)(:?\s+(?P<comment>#.*))?$")
RUNTIME_PATTERN_SPLIT_RE = re.compile(r"^\s*(?P<path>[^\s]+)\s+(?P<pattern>[^\s]+)(:?\s+(?P<comment>#.*))?$")
SONAME_PATTERN_RE = re.compile(r"^(.+\.so\.[a-zA-Z0-9_\.]+).*$")


def read_lines(lines):
    result = []
    for i in lines:
        i = i.strip()

        if not i:
            continue

        # skip comments
        if i.startswith("#"):
            continue

        match = LINE_PATTERN_RE.match(i)
        if match is None:
            raise ValueError("Couldn't parse line: %s" % i)
        gd = match.groupdict()
        result.append(gd["line"])
    return result


def read_lines_from_file(path):
    lines = open(path, "r").readlines()
    lines = read_lines(lines)
    return lines


def read_runtime_patterns(lines):
    result = []
    for i in read_lines(lines):
        match = RUNTIME_PATTERN_SPLIT_RE.match(i)
        if match is None:
            raise ValueError("Couldn't parse pattern: %s" % i)
        gd = match.groupdict()
        result.append((gd["path"], gd["pattern"]))
    return result


def read_runtime_patterns_from_file(path):
    lines = open(path, "r").readlines()
    return read_runtime_patterns(lines)


def expand_runtime_patterns(patterns):
    pm = pungi.pathmatch.PathMatch()
    for path, pattern in patterns:
        for root in ("", "/opt/*/*/root"):
            # include Software Collections: /opt/<vendor>/<scl_name>/root/...
            if "$LIBDIR" in path:
                for lib_dir in ("/lib", "/lib64", "/usr/lib", "/usr/lib64"):
                    path_pattern = path.replace("$LIBDIR", lib_dir)
                    path_pattern = "%s/%s" % (root, path_pattern.lstrip("/"))
                    pm[path_pattern] = (path_pattern, pattern)
            else:
                path_pattern = "%s/%s" % (root, path.lstrip("/"))
                pm[path_pattern] = (path_pattern, pattern)
    return pm


class MultilibMethodBase(object):
    """a base class for multilib methods"""
    name = "base"

    def __init__(self, config_path):
        self.config_path = config_path

    def select(self, po):
        raise NotImplementedError

    def skip(self, po):
        if pungi.gather.is_noarch(po) or pungi.gather.is_source(po) or pungi.util.pkg_is_debug(po):
            return True
        return False

    def is_kernel(self, po):
        for p_name, p_flag, (p_e, p_v, p_r) in po.provides:
            if p_name == "kernel":
                return True
        return False

    def is_kernel_devel(self, po):
        for p_name, p_flag, (p_e, p_v, p_r) in po.provides:
            if p_name == "kernel-devel":
                return True
        return False

    def is_kernel_or_kernel_devel(self, po):
        for p_name, p_flag, (p_e, p_v, p_r) in po.provides:
            if p_name in ("kernel", "kernel-devel"):
                return True
        return False


class NoneMultilibMethod(MultilibMethodBase):
    """multilib disabled"""
    name = "none"

    def select(self, po):
        return False


class AllMultilibMethod(MultilibMethodBase):
    """all packages are multilib"""
    name = "all"

    def select(self, po):
        if self.skip(po):
            return False
        return True


class RuntimeMultilibMethod(MultilibMethodBase):
    """pre-defined paths to libs"""
    name = "runtime"

    def __init__(self, *args, **kwargs):
        super(RuntimeMultilibMethod, self).__init__(*args, **kwargs)
        self.blacklist = read_lines_from_file(self.config_path+"runtime-blacklist.conf")
        self.whitelist = read_lines_from_file(self.config_path+"runtime-whitelist.conf")
        self.patterns = expand_runtime_patterns(read_runtime_patterns_from_file(self.config_path+"runtime-patterns.conf"))

    def select(self, po):
        if self.skip(po):
            return False
        if po.name in self.blacklist:
            return False
        if po.name in self.whitelist:
            return True
        if self.is_kernel(po):
            return False

        # gather all *.so.* provides from the RPM header
        provides = set()
        for i in po.provides:
            match = SONAME_PATTERN_RE.match(i[0])
            if match is not None:
                provides.add(match.group(1))

        for path in po.returnFileEntries() + po.returnFileEntries("ghost"):
            dirname, filename = path.rsplit("/", 1)
            dirname = dirname.rstrip("/")

            patterns = self.patterns[dirname]
            if not patterns:
                continue
            for dir_pattern, file_pattern in patterns:
                if file_pattern == "-":
                    return True
                if fnmatch.fnmatch(filename, file_pattern):
                    if ".so.*" in file_pattern:
                        if filename in provides:
                            # return only if the lib is provided in RPM header
                            # (some libs may be private, hence not exposed in Provides)
                            return True
                    else:
                        return True
        return False


class KernelMultilibMethod(MultilibMethodBase):
    """kernel and kernel-devel"""
    name = "kernel"

    def __init__(self, *args, **kwargs):
        super(KernelMultilibMethod, self).__init__(*args, **kwargs)

    def select(self, po):
        if self.is_kernel_or_kernel_devel(po):
            return True
        return False


class YabootMultilibMethod(MultilibMethodBase):
    """yaboot on ppc"""
    name = "yaboot"

    def __init__(self, *args, **kwargs):
        super(YabootMultilibMethod, self).__init__(*args, **kwargs)

    def select(self, po):
        if po.arch in ["ppc"]:
            if po.name.startswith("yaboot"):
                return True
        return False


class DevelMultilibMethod(MultilibMethodBase):
    """all -devel and -static packages"""
    name = "devel"

    def __init__(self, *args, **kwargs):
        super(DevelMultilibMethod, self).__init__(*args, **kwargs)
        self.blacklist = read_lines_from_file(self.config_path+"devel-blacklist.conf")
        self.whitelist = read_lines_from_file(self.config_path+"devel-whitelist.conf")

    def select(self, po):
        if self.skip(po):
            return False
        if po.name in self.blacklist:
            return False
        if po.name in self.whitelist:
            return True
        if self.is_kernel_devel(po):
            return False
        # HACK: exclude ghc*
        if po.name.startswith("ghc-"):
            return False
        if po.name.endswith("-devel"):
            return True
        if po.name.endswith("-static"):
            return True
        for p_name, p_flag, (p_e, p_v, p_r) in po.provides:
            if p_name.endswith("-devel"):
                return True
            if p_name.endswith("-static"):
                return True
        return False


DEFAULT_METHODS = ["devel", "runtime"]
METHOD_MAP = {}


def init(config_path="/usr/share/pungi/multilib/"):
    global METHOD_MAP

    if not config_path.endswith("/"):
        config_path += "/"

    for cls in (AllMultilibMethod, DevelMultilibMethod, KernelMultilibMethod,
                NoneMultilibMethod, RuntimeMultilibMethod, YabootMultilibMethod):
        method = cls(config_path)
        METHOD_MAP[method.name] = method


def po_is_multilib(po, methods):
    for method_name in methods:
        if not method_name:
            continue
        method = METHOD_MAP[method_name]
        if method.select(po):
            return method_name
    return None
