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


import collections
import fnmatch
import re
import sys
import xml.dom.minidom
from operator import attrgetter

import libcomps
import lxml.etree


if sys.version_info[:2] < (2, 7):
    # HACK: remove spaces from text elements on py < 2.7
    OldElement = xml.dom.minidom.Element

    class Element(OldElement):
        def writexml(self, writer, indent="", addindent="", newl=""):
            if len(self.childNodes) == 1 and self.firstChild.nodeType == 3:
                writer.write(indent)
                OldElement.writexml(self, writer)
                writer.write(newl)
            else:
                OldElement.writexml(self, writer, indent, addindent, newl)

    xml.dom.minidom.Element = Element


TYPE_MAPPING = collections.OrderedDict([
    (libcomps.PACKAGE_TYPE_MANDATORY, 'mandatory'),
    (libcomps.PACKAGE_TYPE_DEFAULT, 'default'),
    (libcomps.PACKAGE_TYPE_OPTIONAL, 'optional'),
    (libcomps.PACKAGE_TYPE_CONDITIONAL, 'conditional'),
])


class CompsValidationError(ValueError):
    pass


class CompsFilter(object):
    """
    Processor for extended comps file. This class treats the input as just an
    XML file with no extra logic and can remove or modify some elements.
    """

    def __init__(self, file_obj, reindent=False):
        self.reindent = reindent
        parser = None
        if self.reindent:
            parser = lxml.etree.XMLParser(remove_blank_text=True)
        self.tree = lxml.etree.parse(file_obj, parser=parser)
        self.encoding = "utf-8"

    def _filter_elements_by_attr(self, xpath, attr_name, attr_val, only_attr=False):
        if only_attr:
            # Remove all elements without the attribute
            for elem in self.tree.xpath("%s[not(@%s)]" % (xpath, attr_name)):
                elem.getparent().remove(elem)

        for elem in self.tree.xpath("%s[@%s]" % (xpath, attr_name)):
            value = elem.attrib.get(attr_name)
            values = [v for v in re.split(r"[, ]+", value) if v]
            if attr_val not in values:
                # remove elements not matching the given value
                elem.getparent().remove(elem)
            else:
                # remove the attribute
                del elem.attrib[attr_name]

    def filter_packages(self, arch, variant, only_arch=False):
        """
        Filter packages according to arch.
        If only_arch is set, then only packages for the specified arch are preserved.
        Multiple arches separated by comma can be specified in the XML.
        """
        self._filter_elements_by_attr("/comps/group/packagelist/packagereq", 'arch', arch, only_arch)
        if variant:
            self._filter_elements_by_attr("/comps/group/packagelist/packagereq",
                                          'variant', variant, only_arch)

    def filter_groups(self, arch, variant, only_arch=False):
        """
        Filter groups according to arch.
        If only_arch is set, then only groups for the specified arch are preserved.
        Multiple arches separated by comma can be specified in the XML.
        """
        self._filter_elements_by_attr("/comps/group", 'arch', arch, only_arch)
        if variant:
            self._filter_elements_by_attr("/comps/group", 'variant', variant, only_arch)

    def filter_environments(self, arch, variant, only_arch=False):
        """
        Filter environments according to arch.
        If only_arch is set, then only environments for the specified arch are preserved.
        Multiple arches separated by comma can be specified in the XML.
        """
        self._filter_elements_by_attr("/comps/environment", 'arch', arch, only_arch)
        if variant:
            self._filter_elements_by_attr("/comps/environment", 'variant', variant, only_arch)

    def filter_category_groups(self):
        """
        Remove undefined groups from categories.
        """
        all_groups = self.tree.xpath("/comps/group/id/text()")
        for category in self.tree.xpath("/comps/category"):
            for group in category.xpath("grouplist/groupid"):
                if group.text not in all_groups:
                    group.getparent().remove(group)

    def remove_empty_groups(self, keep_empty=None):
        """
        Remove all groups without packages.
        """
        keep_empty = keep_empty or []
        for group in self.tree.xpath("/comps/group"):
            if not group.xpath("packagelist/packagereq"):
                group_id = group.xpath("id/text()")[0]
                for pattern in keep_empty:
                    if fnmatch.fnmatch(group_id, pattern):
                        break
                else:
                    group.getparent().remove(group)

    def remove_empty_categories(self):
        """
        Remove all categories without groups.
        """
        for category in self.tree.xpath("/comps/category"):
            if not category.xpath("grouplist/groupid"):
                category.getparent().remove(category)

    def remove_categories(self):
        """
        Remove all categories.
        """
        categories = self.tree.xpath("/comps/category")
        for i in categories:
            i.getparent().remove(i)

    def remove_langpacks(self):
        """
        Remove all langpacks.
        """
        langpacks = self.tree.xpath("/comps/langpacks")
        for i in langpacks:
            i.getparent().remove(i)

    def remove_translations(self):
        """
        Remove all translations.
        """
        for i in self.tree.xpath("//*[@xml:lang]"):
            i.getparent().remove(i)

    def filter_environment_groups(self, lookaside_groups=[]):
        """
        Remove undefined groups from environments.
        """
        all_groups = self.tree.xpath("/comps/group/id/text()") + lookaside_groups
        for environment in self.tree.xpath("/comps/environment"):
            for group in environment.xpath("grouplist/groupid"):
                if group.text not in all_groups:
                    group.getparent().remove(group)

    def remove_empty_environments(self):
        """
        Remove all environments without groups.
        """
        for environment in self.tree.xpath("/comps/environment"):
            if not environment.xpath("grouplist/groupid"):
                environment.getparent().remove(environment)

    def remove_environments(self):
        """
        Remove all langpacks.
        """
        environments = self.tree.xpath("/comps/environment")
        for i in environments:
            i.getparent().remove(i)

    def write(self, file_obj):
        self.tree.write(file_obj, pretty_print=self.reindent, xml_declaration=True, encoding=self.encoding)
        file_obj.write(b"\n")

    def cleanup(self, keep_groups=[], lookaside_groups=[]):
        """
        Remove empty groups, categories and environment from the comps file.
        Groups given in ``keep_groups`` will be preserved even if empty.
        Lookaside groups are groups that are available in parent variant and
        can be referenced in environments even if they are not directly defined
        in the same comps file.
        """
        self.remove_empty_groups(keep_groups)
        self.filter_category_groups()
        self.remove_empty_categories()
        self.filter_environment_groups(lookaside_groups)
        self.remove_empty_environments()


class CompsWrapper(object):
    """
    Class for reading and retrieving information from comps XML files. This
    class is based on libcomps, and therefore only valid comps file with no
    additional extensions are supported by it.
    """

    def __init__(self, comps_file):
        self.comps = libcomps.Comps()
        self.comps.fromxml_f(comps_file)
        self.comps_file = comps_file

    def get_comps_groups(self):
        """Return a list of group IDs."""
        return [group.id for group in self.comps.groups]

    def get_packages(self, group):
        """Return list of package names in given group."""
        for grp in self.comps.groups:
            if grp.id == group:
                return [pkg.name for pkg in grp.packages]
        raise KeyError('No such group %r' % group)

    def get_langpacks(self):
        langpacks = {}
        for pack in self.comps.langpacks:
            langpacks[pack] = self.comps.langpacks[pack]
        return langpacks

    def validate(self):
        """Check that no package name contains whitespace, and raise a
        RuntimeError if there is a problem.
        """
        errors = []
        for group in self.get_comps_groups():
            for pkg in self.get_packages(group):
                stripped_pkg = pkg.strip()
                if pkg != stripped_pkg:
                    errors.append(
                        "Package name %s in group '%s' contains leading or trailing whitespace"
                        % (stripped_pkg, group)
                    )

        if errors:
            raise CompsValidationError(
                "Comps file contains errors:\n%s" % "\n".join(errors)
            )

    def write_comps(self, comps_obj=None, target_file=None):
        if not comps_obj:
            comps_obj = self.generate_comps()
        if not target_file:
            target_file = self.comps_file

        with open(target_file, "wb") as stream:
            stream.write(comps_obj.toprettyxml(indent="  ", encoding="UTF-8"))

    def generate_comps(self):
        impl = xml.dom.minidom.getDOMImplementation()
        doctype = impl.createDocumentType("comps", "-//Red Hat, Inc.//DTD Comps info//EN", "comps.dtd")
        doc = impl.createDocument(None, "comps", doctype)
        msg_elem = doc.documentElement

        for group in sorted(self.comps.groups, key=attrgetter('id')):
            group_node = doc.createElement("group")
            msg_elem.appendChild(group_node)

            append_common_info(doc, group_node, group, force_description=True)
            append_bool(doc, group_node, "default", group.default)
            append_bool(doc, group_node, "uservisible", group.uservisible)

            if group.lang_only:
                append(doc, group_node, "langonly", group.lang_only)

            packagelist = doc.createElement("packagelist")

            packages_by_type = collections.defaultdict(list)
            for pkg in group.packages:
                if pkg.type == libcomps.PACKAGE_TYPE_UNKNOWN:
                    raise RuntimeError(
                        'Failed to process comps file. Package %s in group %s has unknown type'
                        % (pkg.name, group.id))

                packages_by_type[TYPE_MAPPING[pkg.type]].append(pkg)

            for type_name in TYPE_MAPPING.values():
                for pkg in sorted(packages_by_type[type_name], key=attrgetter('name')):
                    kwargs = {"type": type_name}
                    if type_name == "conditional":
                        kwargs["requires"] = pkg.requires
                    append(doc, packagelist, "packagereq", pkg.name, **kwargs)

            group_node.appendChild(packagelist)

        for category in self.comps.categories:
            groups = set(x.name for x in category.group_ids) & set(self.get_comps_groups())
            if not groups:
                continue
            cat_node = doc.createElement("category")
            msg_elem.appendChild(cat_node)

            append_common_info(doc, cat_node, category)

            if category.display_order is not None:
                append(doc, cat_node, "display_order", str(category.display_order))

            append_grouplist(doc, cat_node, groups)

        for environment in sorted(self.comps.environments, key=attrgetter('id')):
            groups = set(x.name for x in environment.group_ids)
            if not groups:
                continue
            env_node = doc.createElement("environment")
            msg_elem.appendChild(env_node)

            append_common_info(doc, env_node, environment)

            if environment.display_order is not None:
                append(doc, env_node, "display_order", str(environment.display_order))

            append_grouplist(doc, env_node, groups)

            if environment.option_ids:
                append_grouplist(doc, env_node, (x.name for x in environment.option_ids), "optionlist")

        if self.comps.langpacks:
            lang_node = doc.createElement("langpacks")
            msg_elem.appendChild(lang_node)

            for name in sorted(self.comps.langpacks):
                append(doc, lang_node, "match", name=name, install=self.comps.langpacks[name])

        return doc

    def _tweak_group(self, group_obj, group_dict):
        if group_dict["default"] is not None:
            group_obj.default = group_dict["default"]
        if group_dict["uservisible"] is not None:
            group_obj.uservisible = group_dict["uservisible"]

    def _tweak_env(self, env_obj, env_dict):
        if env_dict["display_order"] is not None:
            env_obj.display_order = env_dict["display_order"]
        else:
            # write actual display order back to env_dict
            env_dict["display_order"] = env_obj.display_order
        # write group list back to env_dict
        env_dict["groups"] = [g.name for g in env_obj.group_ids]

    def filter_groups(self, group_dicts):
        """Filter groups according to group definitions in group_dicts.
        group_dicts = [{
            "name": group ID,
            "glob": True/False -- is "name" a glob?
            "default: True/False/None -- if not None, set "default" accordingly
            "uservisible": True/False/None -- if not None, set "uservisible" accordingly
        }]
        """
        to_remove = []
        for group_obj in self.comps.groups:
            for group_dict in group_dicts:
                matcher = fnmatch.fnmatch if group_dict["glob"] else lambda x, y: x == y
                if matcher(group_obj.id, group_dict["name"]):
                    self._tweak_group(group_obj, group_dict)
                    break
            else:
                to_remove.append(group_obj)

        for group in to_remove:
            self.comps.groups.remove(group)

        # Sanity check to report warnings on unused group_dicts
        unmatched = set()
        for group_dict in group_dicts:
            matcher = fnmatch.fnmatch if group_dict["glob"] else lambda x, y: x == y
            for group_obj in self.comps.groups:
                if matcher(group_obj.id, group_dict["name"]):
                    break
            else:
                unmatched.add(group_dict["name"])
        return unmatched

    def filter_environments(self, env_dicts):
        """Filter environments according to group definitions in group_dicts.
        env_dicts = [{
            "name": environment ID,
            "display_order: <int>/None -- if not None, set "display_order" accordingly
        }]
        """
        to_remove = []
        for env_obj in self.comps.environments:
            for env_dict in env_dicts:
                if env_obj.id == env_dict["name"]:
                    self._tweak_env(env_obj, env_dict)
                    break
            else:
                to_remove.append(env_obj)

        for env in to_remove:
            self.comps.environments.remove(env)


def append(doc, parent, elem, content=None, lang=None, **kwargs):
    """Create a new DOM element and append it to parent."""
    node = doc.createElement(elem)
    if content:
        node.appendChild(doc.createTextNode(content))
    if lang:
        node.setAttribute("xml:lang", lang)
    for attr, value in sorted(kwargs.items()):
        node.setAttribute(attr, value)
    parent.appendChild(node)
    return node


def append_grouplist(doc, parent, groups, elem="grouplist"):
    grouplist_node = doc.createElement(elem)
    for groupid in sorted(groups):
        append(doc, grouplist_node, "groupid", groupid)
    parent.appendChild(grouplist_node)


def append_common_info(doc, parent, obj, force_description=False):
    """Add id, name and description (with translations)."""
    append(doc, parent, "id", obj.id)
    append(doc, parent, "name", obj.name)

    for lang in sorted(obj.name_by_lang):
        text = obj.name_by_lang[lang]
        append(doc, parent, "name", text, lang=lang)

    if obj.desc or force_description:
        append(doc, parent, "description", obj.desc or '')

        for lang in sorted(obj.desc_by_lang):
            text = obj.desc_by_lang[lang]
            append(doc, parent, "description", text, lang=lang)


def append_bool(doc, parent, elem, value):
    node = doc.createElement(elem)
    node.appendChild(doc.createTextNode("true" if value else "false"))
    parent.appendChild(node)
