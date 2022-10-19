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

from kobo import shortcuts
import os
import productmd
import tempfile
from six.moves import shlex_quote

from pungi import util
from pungi.phases.buildinstall import tweak_configs
from pungi.wrappers import iso


def sh(log, cmd, *args, **kwargs):
    log.info('Running: %s', ' '.join(shlex_quote(x) for x in cmd))
    ret, out = shortcuts.run(cmd, *args, universal_newlines=True, **kwargs)
    if out:
        log.debug('%s', out)
    return ret, out


def get_lorax_dir(default='/usr/share/lorax'):
    try:
        _, out = shortcuts.run(['python3', '-c' 'import pylorax; print(pylorax.find_templates())'],
                               universal_newlines=True)
        return out.strip()
    except Exception:
        return default


def as_bool(arg):
    if arg == 'true':
        return True
    elif arg == 'false':
        return False
    else:
        return arg


def get_arch(log, iso_dir):
    di_path = os.path.join(iso_dir, '.discinfo')
    if os.path.exists(di_path):
        di = productmd.discinfo.DiscInfo()
        di.load(di_path)
        log.info('Detected bootable ISO for %s (based on .discinfo)', di.arch)
        return di.arch

    ti_path = os.path.join(iso_dir, '.treeinfo')
    if os.path.exists(ti_path):
        ti = productmd.treeinfo.TreeInfo()
        ti.load(ti_path)
        log.info('Detected bootable ISO for %s (based on .treeinfo)', ti.tree.arch)
        return ti.tree.arch

    # There is no way to tell the architecture of an ISO file without guessing.
    # Let's print a warning and continue with assuming unbootable ISO.

    log.warning('Failed to detect arch for ISO, assuming unbootable one.')
    log.warning('If this is incorrect, use the --force-arch option.')
    return None


def run(log, opts):
    # mount source iso
    log.info('Mounting %s', opts.source)
    target = os.path.abspath(opts.target)

    with util.temp_dir(prefix='patch-iso-') as work_dir:
        with iso.mount(opts.source) as source_iso_dir:
            util.copy_all(source_iso_dir, work_dir)

        # Make everything writable
        for root, dirs, files in os.walk(work_dir):
            for name in files:
                os.chmod(os.path.join(root, name), 0o640)
            for name in dirs:
                os.chmod(os.path.join(root, name), 0o755)

        # volume id is copied from source iso unless --label is specified
        volume_id = opts.volume_id or iso.get_volume_id(opts.source)

        # create graft points from mounted source iso + overlay dir
        graft_points = iso.get_graft_points([work_dir] + opts.dirs)
        # if ks.cfg is detected, patch syslinux + grub to use it
        if 'ks.cfg' in graft_points:
            log.info('Adding ks.cfg to boot configs')
            tweak_configs(work_dir, volume_id, graft_points['ks.cfg'])

        arch = opts.force_arch or get_arch(log, work_dir)

        with tempfile.NamedTemporaryFile(prefix='graft-points-') as graft_file:
            iso.write_graft_points(graft_file.name, graft_points,
                                   exclude=["*/TRANS.TBL", "*/boot.cat"])

            # make the target iso bootable if source iso is bootable
            boot_args = input_charset = None
            if arch:
                boot_args = iso.get_boot_options(
                    arch, os.path.join(get_lorax_dir(), 'config_files/ppc'))
                input_charset = 'utf-8' if 'ppc' not in arch else None
            # Create the target ISO
            mkisofs_cmd = iso.get_mkisofs_cmd(target, None,
                                              volid=volume_id,
                                              exclude=["./lost+found"],
                                              graft_points=graft_file.name,
                                              input_charset=input_charset,
                                              boot_args=boot_args)
            sh(log, mkisofs_cmd, workdir=work_dir)

    # isohybrid support
    if arch in ["x86_64", "i386"]:
        isohybrid_cmd = iso.get_isohybrid_cmd(target, arch)
        sh(log, isohybrid_cmd)

    supported = as_bool(opts.supported or iso.get_checkisomd5_data(opts.source)['Supported ISO'])
    # implantmd5 + supported bit (use the same as on source iso, unless
    # overriden by --supported option)
    isomd5sum_cmd = iso.get_implantisomd5_cmd(target, supported)
    sh(log, isomd5sum_cmd)
