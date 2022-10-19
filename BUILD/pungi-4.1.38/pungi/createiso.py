# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import six
from collections import namedtuple
from six.moves import shlex_quote

from .wrappers import iso
from .wrappers.jigdo import JigdoWrapper


CreateIsoOpts = namedtuple('CreateIsoOpts',
                           ['buildinstall_method', 'arch', 'output_dir', 'jigdo_dir',
                            'iso_name', 'volid', 'graft_points', 'supported', 'os_tree',
                            "hfs_compat"])
CreateIsoOpts.__new__.__defaults__ = (None,) * len(CreateIsoOpts._fields)


def quote(str):
    """Quote an argument for shell, but make sure $TEMPLATE variable will be
    expanded.
    """
    if str.startswith('$TEMPLATE'):
        return '$TEMPLATE%s' % shlex_quote(str.replace('$TEMPLATE', '', 1))
    return shlex_quote(str)


def emit(f, cmd):
    """Print line of shell code into the stream."""
    if isinstance(cmd, six.string_types):
        print(cmd, file=f)
    else:
        print(' '.join([quote(x) for x in cmd]), file=f)


FIND_TEMPLATE_SNIPPET = """
if ! TEMPLATE="$($(head -n1 $(which lorax) | cut -c3-) -c 'import pylorax; print(pylorax.find_templates())')"; then
  TEMPLATE=/usr/share/lorax;
fi
""".replace('\n', '')


def make_image(f, opts):
    mkisofs_kwargs = {}

    if opts.buildinstall_method:
        if opts.buildinstall_method == 'lorax':
            emit(f, FIND_TEMPLATE_SNIPPET)
            mkisofs_kwargs["boot_args"] = iso.get_boot_options(
                opts.arch,
                os.path.join("$TEMPLATE", "config_files/ppc"),
                hfs_compat=opts.hfs_compat,
            )
        elif opts.buildinstall_method == 'buildinstall':
            mkisofs_kwargs["boot_args"] = iso.get_boot_options(
                opts.arch, "/usr/lib/anaconda-runtime/boot")

    # ppc(64) doesn't seem to support utf-8
    if opts.arch in ("ppc", "ppc64", "ppc64le"):
        mkisofs_kwargs["input_charset"] = None

    cmd = iso.get_mkisofs_cmd(opts.iso_name, None, volid=opts.volid,
                              exclude=["./lost+found"],
                              graft_points=opts.graft_points, **mkisofs_kwargs)
    emit(f, cmd)


def implant_md5(f, opts):
    cmd = iso.get_implantisomd5_cmd(opts.iso_name, opts.supported)
    emit(f, cmd)


def run_isohybrid(f, opts):
    """If the image is bootable, it should include an MBR or GPT so that it can
    be booted when written to USB disk. This is done by running isohybrid on
    the image.
    """
    if opts.buildinstall_method and opts.arch in ["x86_64", "i386"]:
        cmd = iso.get_isohybrid_cmd(opts.iso_name, opts.arch)
        emit(f, cmd)


def make_manifest(f, opts):
    emit(f, iso.get_manifest_cmd(opts.iso_name))


def make_jigdo(f, opts):
    jigdo = JigdoWrapper()
    files = [
        {
            "path": opts.os_tree,
            "label": None,
            "uri": None,
        }
    ]
    cmd = jigdo.get_jigdo_cmd(os.path.join(opts.output_dir, opts.iso_name),
                              files, output_dir=opts.jigdo_dir,
                              no_servers=True, report="noprogress")
    emit(f, cmd)


def write_script(opts, f):
    if bool(opts.jigdo_dir) != bool(opts.os_tree):
        raise RuntimeError('jigdo_dir must be used together with os_tree')

    emit(f, "#!/bin/bash")
    emit(f, "set -ex")
    emit(f, "cd %s" % opts.output_dir)
    make_image(f, opts)
    run_isohybrid(f, opts)
    implant_md5(f, opts)
    make_manifest(f, opts)
    if opts.jigdo_dir:
        make_jigdo(f, opts)
