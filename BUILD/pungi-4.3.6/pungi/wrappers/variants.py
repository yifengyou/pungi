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


from __future__ import print_function
import os
import copy
import lxml.etree


def get_variants_dtd(logger=None):
    """
    Find the DTD for variants file. First look into the system directory, and
    fall back to local directory.
    """
    variants_dtd = "/usr/share/pungi/variants.dtd"
    if not os.path.isfile(variants_dtd):
        devel_variants_dtd = os.path.normpath(
            os.path.realpath(
                os.path.join(
                    os.path.dirname(__file__), "..", "..", "share", "variants.dtd"
                )
            )
        )
        msg = "Variants DTD not found: %s" % variants_dtd
        if os.path.isfile(devel_variants_dtd):
            if logger:
                logger.warning("%s", msg)
                logger.warning("Using alternative DTD: %s", devel_variants_dtd)
            variants_dtd = devel_variants_dtd
        else:
            raise RuntimeError(msg)
    return variants_dtd


class VariantsValidationError(ValueError):
    pass


NO_WHITESPACE_ELEMENTS = [
    "arch",
    "environment",
    "group",
    "kojitag",
    "module",
    "name",
    "package",
]


class VariantsXmlParser(object):
    def __init__(self, file_obj, tree_arches=None, tree_variants=None, logger=None):
        self.tree = lxml.etree.parse(file_obj)
        with open(get_variants_dtd(logger), "r") as f:
            self.dtd = lxml.etree.DTD(f)
        self.addons = {}
        self.variants = {}
        self.layered_products = {}
        self.tree_arches = tree_arches
        self.tree_variants = tree_variants
        self.logger = logger
        self.validate()

    def _is_true(self, value):
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("Invalid boolean value in variants XML: %s" % value)

    def validate(self):
        if not self.dtd.validate(self.tree):
            errors = [str(i) for i in self.dtd.error_log.filter_from_errors()]
            raise VariantsValidationError(
                "Variants XML doesn't validate:\n%s" % "\n".join(errors)
            )

        errors = []
        for text in self.tree.xpath("//text()"):
            if text != text.strip() and not text.is_tail:
                e = text.getparent()
                if e.tag in NO_WHITESPACE_ELEMENTS:
                    errors.append(
                        "Tag %s on line %s contains leading or trailing whitespace"
                        % (e.tag, e.sourceline)
                    )

        if errors:
            raise VariantsValidationError(
                "Variants XML doesn't validate:\n%s" % "\n".join(errors)
            )

    def parse_variant_node(self, variant_node, parent=None):
        variant_dict = {
            "id": str(variant_node.attrib["id"]),
            "name": str(variant_node.attrib["name"]),
            "type": str(variant_node.attrib["type"]),
            "arches": [str(i) for i in variant_node.xpath("arches/arch/text()")],
            "groups": [],
            "modules": None,
            "modular_koji_tags": None,
            "environments": [],
            "buildinstallpackages": [],
            "is_empty": bool(variant_node.attrib.get("is_empty", False)),
            "parent": parent,
        }
        if self.tree_arches:
            variant_dict["arches"] = [
                i for i in variant_dict["arches"] if i in self.tree_arches
            ]
        if not variant_dict["arches"]:
            if self.logger:
                self.logger.info(
                    "Excluding variant %s: all its arches are filtered."
                    % variant_dict["id"]
                )
            return None

        for grouplist_node in variant_node.xpath("groups"):
            for group_node in grouplist_node.xpath("group"):
                group = {
                    "name": str(group_node.text),
                    "glob": self._is_true(group_node.attrib.get("glob", "false")),
                    "default": None,
                    "uservisible": None,
                }

                default = group_node.attrib.get("default")
                if default is not None:
                    group["default"] = self._is_true(default)

                uservisible = group_node.attrib.get("uservisible")
                if uservisible is not None:
                    group["uservisible"] = self._is_true(uservisible)

                variant_dict["groups"].append(group)

        for modulelist_node in variant_node.xpath("modules"):
            variant_dict["modules"] = variant_dict["modules"] or []
            for module_node in modulelist_node.xpath("module"):
                module = {
                    "name": str(module_node.text),
                    "glob": self._is_true(module_node.attrib.get("glob", "false")),
                }

                variant_dict["modules"].append(module)

            for kojitag_node in modulelist_node.xpath("kojitag"):
                kojitag = {
                    "name": str(kojitag_node.text),
                }

                variant_dict["modular_koji_tags"] = (
                    variant_dict["modular_koji_tags"] or []
                )
                variant_dict["modular_koji_tags"].append(kojitag)

        for environments_node in variant_node.xpath("environments"):
            for environment_node in environments_node.xpath("environment"):
                environment = {
                    "name": str(environment_node.text),
                    "display_order": None,
                }

                display_order = environment_node.attrib.get("display_order")
                if display_order is not None:
                    environment["display_order"] = int(display_order)

                variant_dict["environments"].append(environment)

        for buildinstallpackages_node in variant_node.xpath("buildinstallpackages"):
            for package_node in buildinstallpackages_node.xpath("package"):
                variant_dict["buildinstallpackages"].append(package_node.text)

        variant = Variant(**variant_dict)
        if variant.type == "layered-product":
            release_node = variant_node.xpath("release")[0]
            variant.release_name = str(release_node.attrib["name"])
            variant.release_version = str(release_node.attrib["version"])
            variant.release_short = str(release_node.attrib["short"])

        contains_optional = False
        for child_node in variant_node.xpath("variants/variant"):
            child_variant = self.parse_variant_node(child_node, variant)
            if not self.add_child(child_variant, variant):
                continue
            if child_variant.type == "optional":
                contains_optional = True

        has_optional = self._is_true(variant_node.attrib.get("has_optional", "false"))
        if has_optional and not contains_optional:
            optional = Variant(
                id="optional",
                name="optional",
                type="optional",
                arches=variant.arches,
                groups=[],
                parent=variant,
            )
            self.add_child(optional, variant)

        for ref in variant_node.xpath("variants/ref/@id"):
            try:
                child_variant = self.parse_variant_node(self.addons[ref], variant)
            except KeyError:
                raise RuntimeError(
                    "Variant %s references non-existing variant %s" % (variant.uid, ref)
                )
            self.add_child(child_variant, variant)

        # XXX: top-level optional
        #    for ref in variant_node.xpath("variants/ref/@id"):
        #        variant["variants"].append(copy.deepcopy(addons[ref]))

        return variant

    def _is_excluded(self, variant):
        if self.tree_variants and variant.uid not in self.tree_variants:
            if self.logger:
                self.logger.info(
                    "Excluding variant %s: filtered by configuration." % variant
                )
            return True
        return False

    def add_child(self, child, parent):
        if not child or self._is_excluded(child):
            return None
        parent.add_variant(child)
        return child

    def parse(self):
        # we allow top-level addon definitions which can be referenced in variants
        for variant_node in self.tree.xpath("/variants/variant[@type='addon']"):
            variant_id = str(variant_node.attrib["id"])
            self.addons[variant_id] = variant_node

        for variant_node in self.tree.xpath(
            "/variants/variant[@type='layered-product']"
        ):
            variant_id = str(variant_node.attrib["id"])
            self.addons[variant_id] = variant_node

        for variant_node in self.tree.xpath("/variants/variant[@type='variant']"):
            variant = self.parse_variant_node(variant_node)
            if not variant or self._is_excluded(variant):
                continue
            self.variants[variant.id] = variant

        return self.variants


class Variant(object):
    def __init__(
        self,
        id,
        name,
        type,
        arches,
        groups,
        environments=None,
        buildinstallpackages=None,
        is_empty=False,
        parent=None,
        modules=None,
        modular_koji_tags=None,
    ):

        environments = environments or []
        buildinstallpackages = buildinstallpackages or []

        self.id = id
        self.name = name
        self.type = type
        self.arches = sorted(copy.deepcopy(arches))
        self.groups = sorted(copy.deepcopy(groups), key=lambda x: x["name"])
        self.environments = sorted(copy.deepcopy(environments), key=lambda x: x["name"])
        self.modules = copy.deepcopy(modules)
        if self.modules:
            self.modules = sorted(self.modules, key=lambda x: x["name"])
        self.modular_koji_tags = copy.deepcopy(modular_koji_tags)
        if self.modular_koji_tags:
            self.modular_koji_tags = sorted(
                self.modular_koji_tags, key=lambda x: x["name"]
            )
        self.buildinstallpackages = sorted(buildinstallpackages)
        self.variants = {}
        self.parent = parent
        self.is_empty = is_empty

        self.pkgsets = set()
        self.arch_mmds = {}
        self.module_uid_to_koji_tag = {}
        self.nsvc_to_pkgset = {}

    def __getitem__(self, name):
        return self.variants[name]

    def __str__(self):
        return self.uid

    def __repr__(self):
        return 'Variant(id="{0.id}", name="{0.name}", type="{0.type}", parent={0.parent})'.format(  # noqa: E501
            self
        )

    def __eq__(self, other):
        return self.type == other.type and self.uid == other.uid

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        ORDERING = {"variant": 0, "addon": 1, "layered-product": 1, "optional": 2}
        return (ORDERING[self.type], self.uid) < (ORDERING[other.type], other.uid)

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return not (self <= other)

    def __ge__(self, other):
        return not (self < other)

    def __hash__(self):
        return hash((self.type, self.uid))

    @property
    def uid(self):
        if self.parent:
            return "%s-%s" % (self.parent, self.id)
        return self.id

    def add_variant(self, variant):
        """Add a variant object to the child variant list."""
        if variant.id in self.variants:
            return
        if self.type != "variant":
            raise RuntimeError("Only 'variant' can contain another variants.")
        if variant.id == self.id:
            # due to os/<variant.id> path -- addon id would conflict with
            # parent variant id
            raise RuntimeError(
                "Child variant id must be different than parent variant id: %s"
                % variant.id
            )
        # sometimes an addon or layered product can be part of multiple
        # variants with different set of arches
        arches = sorted(set(self.arches).intersection(set(variant.arches)))
        if self.arches and not arches:
            raise RuntimeError(
                "%s: arch list %s does not intersect with parent arch list: %s"
                % (variant, variant.arches, self.arches)
            )
        variant.arches = arches
        self.variants[variant.id] = variant
        variant.parent = self

    def get_groups(self, arch=None, types=None, recursive=False):
        """Return list of groups, default types is ["self"]"""

        types = types or ["self"]
        result = copy.deepcopy(self.groups)
        for variant in self.get_variants(arch=arch, types=types, recursive=recursive):
            if variant == self:
                continue
            for group in variant.get_groups(
                arch=arch, types=types, recursive=recursive
            ):
                if group not in result:
                    result.append(group)
        return result

    def get_modules(self, arch=None, types=None, recursive=False):
        """Return list of modules, default types is ["self"]"""

        if self.modules is None:
            return []

        types = types or ["self"]
        result = copy.deepcopy(self.modules)
        for variant in self.get_variants(arch=arch, types=types, recursive=recursive):
            if variant == self:
                continue
            for module in variant.get_modules(
                arch=arch, types=types, recursive=recursive
            ):
                if module not in result:
                    result.append(module)
        return result

    def get_modular_koji_tags(self, arch=None, types=None, recursive=False):
        """Return list of modular koji tags, default types is ["self"]"""

        if self.modular_koji_tags is None:
            return []

        types = types or ["self"]
        result = copy.deepcopy(self.modular_koji_tags)
        for variant in self.get_variants(arch=arch, types=types, recursive=recursive):
            if variant == self:
                continue
            for koji_tag in variant.get_modular_koji_tags(
                arch=arch, types=types, recursive=recursive
            ):
                if koji_tag not in result:
                    result.append(koji_tag)
        return result

    def get_variants(self, arch=None, types=None, recursive=False):
        """
        Return all variants of given arch and types.

        Supported variant types:
            self     - include the top-level ("self") variant as well
            addon
            variant
            optional
        """
        types = types or []
        result = []

        if arch and arch not in self.arches + ["src"]:
            return result

        if "self" in types:
            result.append(self)

        for variant in self.variants.values():
            if types and variant.type not in types:
                continue
            if arch and arch not in variant.arches + ["src"]:
                continue
            result.append(variant)
            if recursive:
                result.extend(
                    variant.get_variants(
                        types=[i for i in types if i != "self"], recursive=True
                    )
                )

        return result

    def get_addons(self, arch=None):
        """Return all 'addon' child variants. No recursion."""
        return self.get_variants(arch=arch, types=["addon"], recursive=False)

    def get_layered_products(self, arch=None):
        """Return all 'layered-product' child variants. No recursion."""
        return self.get_variants(arch=arch, types=["layered-product"], recursive=False)

    def get_optional(self, arch=None):
        """Return all 'optional' child variants. No recursion."""
        return self.get_variants(arch=arch, types=["optional"], recursive=False)
