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
from fnmatch import fnmatch
import contextlib
from six.moves import shlex_quote

from kobo.shortcuts import force_list, relative_path, run
from pungi import util


def get_boot_options(arch, createfrom, efi=True, hfs_compat=True):
    """Checks to see what we need as the -b option for mkisofs"""

    if arch in ("arm", "armhfp"):
        result = []
        return result

    if arch in ("aarch64", ):
        result = [
            '-eltorito-alt-boot',
            '-e', 'images/efiboot.img',
            '-no-emul-boot',
        ]
        return result

    if arch in ("i386", "i686", "x86_64"):
        result = [
            '-b', 'isolinux/isolinux.bin',
            '-c', 'isolinux/boot.cat',
            '-no-emul-boot',
            '-boot-load-size', '4',
            '-boot-info-table',
        ]

        # EFI args
        if arch == "x86_64":
            result.extend([
                '-eltorito-alt-boot',
                '-e', 'images/efiboot.img',
                '-no-emul-boot',
            ])
        return result

    if arch == "ia64":
        result = [
            '-b', 'images/boot.img',
            '-no-emul-boot',
        ]
        return result

    if arch in ("ppc", "ppc64") or (arch == "ppc64le" and hfs_compat):
        result = [
            '-part',
            '-hfs',
            '-r',
            '-l',
            '-sysid', 'PPC',
            '-no-desktop',
            '-allow-multidot',
            '-chrp-boot',
            "-map", os.path.join(createfrom, 'mapping'),  # -map %s/ppc/mapping
            '-hfs-bless', "/ppc/mac",  # must be the last
        ]
        return result

    if arch == "ppc64le" and not hfs_compat:
        result = [
            '-r',
            '-l',
            '-sysid', 'PPC',
            '-chrp-boot',
        ]
        return result

    if arch == "sparc":
        result = [
            '-G', '/boot/isofs.b',
            '-B', '...',
            '-s', '/boot/silo.conf',
            '-sparc-label', '"sparc"',
        ]
        return result

    if arch in ("s390", "s390x"):
        result = [
            '-eltorito-boot', 'images/cdboot.img',
            '-no-emul-boot',
        ]
        return result

    raise ValueError("Unknown arch: %s" % arch)


def _truncate_volid(volid):
    if len(volid) > 32:
        volid = volid.replace("-", "")

    if len(volid) > 32:
        volid = volid.replace(" ", "")

    if len(volid) > 32:
        volid = volid.replace("Supplementary", "Supp")

    if len(volid) > 32:
        raise ValueError("Volume ID must be less than 32 character: %s" % volid)

    return volid


def get_mkisofs_cmd(iso, paths, appid=None, volid=None, volset=None, exclude=None, verbose=False, boot_args=None, input_charset="utf-8", graft_points=None):
    # following options are always enabled
    untranslated_filenames = True
    translation_table = True
    joliet = True
    joliet_long = True
    rock = True

    cmd = ["/usr/bin/genisoimage"]
    if appid:
        cmd.extend(["-appid", appid])

    if untranslated_filenames:
        cmd.append("-untranslated-filenames")

    if volid:
        cmd.extend(["-volid", _truncate_volid(volid)])

    if joliet:
        cmd.append("-J")

    if joliet_long:
        cmd.append("-joliet-long")

    if volset:
        cmd.extend(["-volset", volset])

    if rock:
        cmd.append("-rational-rock")

    if verbose:
        cmd.append("-verbose")

    if translation_table:
        cmd.append("-translation-table")

    if input_charset:
        cmd.extend(["-input-charset", input_charset])

    if exclude:
        for i in force_list(exclude):
            cmd.extend(["-x", i])

    if boot_args:
        cmd.extend(boot_args)

    cmd.extend(["-o", iso])

    if graft_points:
        cmd.append("-graft-points")
        cmd.extend(["-path-list", graft_points])
    else:
        # we're either using graft points or file lists, not both
        cmd.extend(force_list(paths))

    return cmd


def get_implantisomd5_cmd(iso_path, supported=False):
    cmd = ["/usr/bin/implantisomd5"]
    if supported:
        cmd.append("--supported-iso")
    cmd.append(iso_path)
    return cmd


def get_checkisomd5_cmd(iso_path, just_print=False):
    cmd = ["/usr/bin/checkisomd5"]
    if just_print:
        cmd.append("--md5sumonly")
    cmd.append(iso_path)
    return cmd


def get_checkisomd5_data(iso_path, logger=None):
    cmd = get_checkisomd5_cmd(iso_path, just_print=True)
    retcode, output = run(cmd, universal_newlines=True)
    items = [line.strip().rsplit(":", 1) for line in output.splitlines()]
    items = dict([(k, v.strip()) for k, v in items])
    md5 = items.get(iso_path, '')
    if len(md5) != 32:
        # We have seen cases where the command finished successfully, but
        # returned garbage value. We need to handle it, otherwise there would
        # be a crash once we try to write image metadata.
        # This only logs information about the problem and leaves the hash
        # empty, which is valid from productmd point of view.
        if logger:
            logger.critical('Implanted MD5 in %s is not valid: %r', iso_path, md5)
            logger.critical('Ran command %r; exit code %r; output %r', cmd, retcode, output)
        return None
    return items


def get_implanted_md5(iso_path, logger=None):
    return (get_checkisomd5_data(iso_path, logger=logger) or {}).get(iso_path)


def get_isohybrid_cmd(iso_path, arch):
    # isohybrid is in syslinux which is x86 only
    cmd = ["/usr/bin/isohybrid"]
    # uefi is only supported on x86_64
    if arch == "x86_64":
        cmd.append("--uefi")
    cmd.append(iso_path)
    return cmd


def get_manifest_cmd(iso_name):
    return "isoinfo -R -f -i %s | grep -v '/TRANS.TBL$' | sort >> %s.manifest" % (
        shlex_quote(iso_name), shlex_quote(iso_name))


def get_volume_id(path):
    cmd = ["isoinfo", "-d", "-i", path]
    retcode, output = run(cmd, universal_newlines=True)

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Volume id:"):
            return line[11:].strip()

    raise RuntimeError("Could not read Volume ID")


def get_graft_points(paths, exclusive_paths=None, exclude=None):
    # path priority in ascending order (1st = lowest prio)
    # paths merge according to priority
    # exclusive paths override whole dirs

    result = {}
    exclude = exclude or []
    exclusive_paths = exclusive_paths or []

    for i in paths:
        if isinstance(i, dict):
            tree = i
        else:
            tree = _scan_tree(i)
        result = _merge_trees(result, tree)

    for i in exclusive_paths:
        tree = _scan_tree(i)
        result = _merge_trees(result, tree, exclusive=True)

    # TODO: exclude
    return result


def _paths_from_list(root, paths):
    root = os.path.abspath(root).rstrip("/") + "/"
    result = {}
    for i in paths:
        i = os.path.normpath(os.path.join(root, i))
        key = i[len(root):]
        result[key] = i
    return result


def _scan_tree(path):
    path = os.path.abspath(path)
    result = {}
    for root, dirs, files in os.walk(path):
        for f in files:
            abspath = os.path.join(root, f)
            relpath = relative_path(abspath, path.rstrip("/") + "/")
            result[relpath] = abspath

        # include empty dirs
        if root != path:
            abspath = os.path.join(root, "")
            relpath = relative_path(abspath, path.rstrip("/") + "/")
            result[relpath] = abspath

    return result


def _merge_trees(tree1, tree2, exclusive=False):
    # tree2 has higher priority
    result = tree2.copy()
    all_dirs = set([os.path.dirname(i).rstrip("/") for i in result if os.path.dirname(i) != ""])

    for i in tree1:
        dn = os.path.dirname(i)
        if exclusive:
            match = False
            for a in all_dirs:
                if dn == a or dn.startswith("%s/" % a):
                    match = True
                    break
            if match:
                continue

        if i in result:
            continue

        result[i] = tree1[i]
    return result


def write_graft_points(file_name, h, exclude=None):
    exclude = exclude or []
    result = {}
    seen_dirs = set()
    for i in sorted(h, reverse=True):
        dn = os.path.dirname(i)

        if not i.endswith("/"):
            result[i] = h[i]
            seen_dirs.add(dn)
            continue

        found = False
        for j in seen_dirs:
            if j.startswith(dn):
                found = True
                break
        if not found:
            result[i] = h[i]
        seen_dirs.add(dn)

    f = open(file_name, "w")
    for i in sorted(result, key=graft_point_sort_key):
        # make sure all files required for boot come first,
        # otherwise there may be problems with booting (large LBA address, etc.)
        found = False
        for excl in exclude:
            if fnmatch(i, excl):
                found = True
                break
        if found:
            continue
        f.write("%s=%s\n" % (i, h[i]))
    f.close()


def _is_rpm(path):
    return path.endswith(".rpm")


def _is_image(path):
    if path.startswith("images/"):
        return True
    if path.startswith("isolinux/"):
        return True
    if path.startswith("EFI/"):
        return True
    if path.startswith("etc/"):
        return True
    if path.startswith("ppc/"):
        return True
    if path.endswith(".img"):
        return True
    if path.endswith(".ins"):
        return True
    return False


def graft_point_sort_key(x):
    """
    Images are sorted first, followed by other files. RPMs always come last.
    In the same group paths are sorted alphabetically.
    """
    return (0 if _is_image(x) else 2 if _is_rpm(x) else 1, x)


@contextlib.contextmanager
def mount(image, logger=None, use_guestmount=True):
    """Mount an image and make sure it's unmounted.

    The yielded path will only be valid in the with block and is removed once
    the image is unmounted.
    """
    with util.temp_dir(prefix='iso-mount-') as mount_dir:
        ret, __ = run(["which", "guestmount"], can_fail=True)
        # return code 0 means that guestmount is available
        guestmount_available = use_guestmount and not bool(ret)
        if guestmount_available:
            # use guestmount to mount the image, which doesn't require root privileges
            # LIBGUESTFS_BACKEND=direct: running qemu directly without libvirt
            env = {'LIBGUESTFS_BACKEND': 'direct', 'LIBGUESTFS_DEBUG': '1', 'LIBGUESTFS_TRACE': '1'}
            cmd = ["guestmount", "-a", image, "-m", "/dev/sda", mount_dir]
        else:
            env = {}
            cmd = ["mount", "-o", "loop", image, mount_dir]
        ret, out = run(cmd, env=env, can_fail=True, universal_newlines=True)
        if ret != 0:
            # The mount command failed, something is wrong. Log the output and raise an exception.
            if logger:
                logger.error('Command %s exited with %s and output:\n%s'
                             % (cmd, ret, out))
            raise RuntimeError('Failed to mount %s' % image)
        try:
            yield mount_dir
        finally:
            if guestmount_available:
                util.run_unmount_cmd(['fusermount', '-u', mount_dir], path=mount_dir)
            else:
                util.run_unmount_cmd(['umount', mount_dir], path=mount_dir)
