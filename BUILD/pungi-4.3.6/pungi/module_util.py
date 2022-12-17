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

import glob
import os

try:
    import gi

    gi.require_version("Modulemd", "2.0")  # noqa
    from gi.repository import Modulemd
except (ImportError, ValueError):
    Modulemd = None


def iter_module_defaults(path):
    """Given a path to a directory with yaml files, yield each module default
    in there as a pair (module_name, ModuleDefaults instance).
    """
    # It is really tempting to merge all the module indexes into a single one
    # and work with it. However that does not allow for detecting conflicting
    # defaults. That should not happen in practice, but better safe than sorry.
    # Once libmodulemd can report the error, this code can be simplifed by a
    # lot. It was implemented in
    # https://github.com/fedora-modularity/libmodulemd/commit/3087e4a5c38a331041fec9b6b8f1a372f9ffe64d
    # and released in 2.6.0, but 2.8.0 added the need to merge overrides and
    # that breaks this use case again.
    for file in glob.glob(os.path.join(path, "*.yaml")):
        index = Modulemd.ModuleIndex()
        index.update_from_file(file, strict=False)
        for module_name in index.get_module_names():
            yield module_name, index.get_module(module_name).get_defaults()


def get_module_obsoletes_idx(path, mod_list):
    """Given a path to a directory with yaml files, return Index with
    merged all obsoletes.
    """

    merger = Modulemd.ModuleIndexMerger.new()
    md_idxs = []

    # associate_index does NOT copy it's argument (nor increases a
    # reference counter on the object). It only stores a pointer.
    for file in glob.glob(os.path.join(path, "*.yaml")):
        index = Modulemd.ModuleIndex()
        index.update_from_file(file, strict=False)
        mod_name = index.get_module_names()[0]

        if mod_name and (mod_name in mod_list or not mod_list):
            md_idxs.append(index)
            merger.associate_index(md_idxs[-1], 0)

    merged_idx = merger.resolve()

    return merged_idx


def collect_module_defaults(
    defaults_dir, modules_to_load=None, mod_index=None, overrides_dir=None
):
    """Load module defaults into index.

    If `modules_to_load` is passed in, it should be a set of module names. Only
    defaults for these modules will be loaded.

    If `mod_index` is passed in, it will be updated and returned. If it was
    not, a new ModuleIndex will be created and returned
    """
    mod_index = mod_index or Modulemd.ModuleIndex()

    temp_index = Modulemd.ModuleIndex.new()
    temp_index.update_from_defaults_directory(
        defaults_dir, overrides_path=overrides_dir, strict=False
    )

    for module_name in temp_index.get_module_names():
        defaults = temp_index.get_module(module_name).get_defaults()

        if not modules_to_load or module_name in modules_to_load:
            mod_index.add_defaults(defaults)

    return mod_index


def collect_module_obsoletes(obsoletes_dir, modules_to_load, mod_index=None):
    """Load module obsoletes into index.

    This works in a similar fashion as collect_module_defaults except it
    merges indexes together instead of adding them during iteration.

    Additionally if modules_to_load is not empty returned Index will include
    only obsoletes for those modules.
    """

    obsoletes_index = get_module_obsoletes_idx(obsoletes_dir, modules_to_load)

    # Merge Obsoletes with Modules Index.
    if mod_index:
        merger = Modulemd.ModuleIndexMerger.new()
        merger.associate_index(mod_index, 0)
        merger.associate_index(obsoletes_index, 0)
        merged_idx = merger.resolve()
        obsoletes_index = merged_idx

    return obsoletes_index
