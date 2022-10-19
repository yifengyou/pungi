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
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""
This module exports a couple functions for checking configuration and
environment.

Validation of the configuration is the most complicated part here: here is the
outline of the process:

1. The configuration is checked against JSON schema. The errors encountered are
   reported as string. The validator also populates default values.

2. The requirements/conflicts among options are resolved separately. This is
   because expressing those relationships in JSON Schema is very verbose and
   the error message is not very descriptive.

3. Extra validation can happen in ``validate()`` method of any phase.

When a new config option is added, the schema must be updated (see the
``make_schema`` function). The dependencies should be encoded into
``CONFIG_DEPS`` mapping.
"""

from __future__ import print_function

import multiprocessing
import os.path
import platform
import re

import jsonschema
import six
from kobo.shortcuts import force_list
from pungi.phases import PHASES_NAMES
from productmd.common import RELEASE_TYPES
from productmd.composeinfo import COMPOSE_TYPES

from . import util


def _will_productimg_run(conf):
    return conf.get('productimg', False) and conf.get('bootable', False)


def is_jigdo_needed(conf):
    return conf.get('create_jigdo', True)


def is_isohybrid_needed(conf):
    """The isohybrid command is needed locally only for productimg phase and
    createiso phase without runroot. If that is not going to run, we don't need
    to check for it. Additionally, the syslinux package is only available on
    x86_64 and i386.
    """
    runroot_tag = conf.get('runroot_tag', '')
    if runroot_tag and not _will_productimg_run(conf):
        return False
    if platform.machine() not in ('x86_64', 'i686', 'i386'):
        print('Not checking for /usr/bin/isohybrid due to current architecture. '
              'Expect failures in productimg phase.')
        return False
    return True


def is_genisoimage_needed(conf):
    """This is only needed locally for productimg and createiso without runroot.
    """
    runroot_tag = conf.get('runroot_tag', '')
    if runroot_tag and not _will_productimg_run(conf):
        return False
    return True


def is_createrepo_c_needed(conf):
    return conf.get('createrepo_c', True)


# The first element in the tuple is package name expected to have the
# executable (2nd element of the tuple). The last element is an optional
# function that should determine if the tool is required based on
# configuration.
tools = [
    ("isomd5sum", "/usr/bin/implantisomd5", None),
    ("isomd5sum", "/usr/bin/checkisomd5", None),
    ("jigdo", "/usr/bin/jigdo-lite", is_jigdo_needed),
    ("genisoimage", "/usr/bin/genisoimage", is_genisoimage_needed),
    ("gettext", "/usr/bin/msgfmt", _will_productimg_run),
    ("syslinux", "/usr/bin/isohybrid", is_isohybrid_needed),
    # createrepo, modifyrepo and mergerepo are not needed by default, only when
    # createrepo_c is not configured
    ("createrepo", "/usr/bin/createrepo", lambda conf: not is_createrepo_c_needed(conf)),
    ("createrepo", "/usr/bin/modifyrepo", lambda conf: not is_createrepo_c_needed(conf)),
    ("createrepo", "/usr/bin/mergerepo", lambda conf: not is_createrepo_c_needed(conf)),
    ("createrepo_c", "/usr/bin/createrepo_c", is_createrepo_c_needed),
    ("createrepo_c", "/usr/bin/modifyrepo_c", is_createrepo_c_needed),
    ("createrepo_c", "/usr/bin/mergerepo_c", is_createrepo_c_needed),
]


def check(conf):
    """Check runtime environment and report errors about missing dependencies."""
    fail = False

    for package, path, test_if_required in tools:
        if test_if_required and not test_if_required(conf):
            # The config says this file is not required, so we won't even check it.
            continue
        if not os.path.exists(path):
            print("Program '%s' doesn't exist. Install package '%s'." % (path, package))
            fail = True

    return not fail


def check_umask(logger):
    """Make sure umask is set to something reasonable. If not, log a warning."""
    mask = os.umask(0)
    os.umask(mask)

    if mask > 0o022:
        logger.warning('Unusually strict umask detected (0%03o), '
                       'expect files with broken permissions.', mask)


def _validate_requires(schema, conf, valid_options):
    """
    Check if all requires and conflicts are ok in configuration.

    :param conf: Python dict with configuration to check
    :param valid_options: mapping with option dependencies
    :param with_default: a set of options that have default value
    :returns: list of errors
    """
    errors = []

    def has_default(x):
        return schema['properties'].get(x, {}).get('default') == conf[x]

    for name, opt in valid_options.items():
        value = conf.get(name)

        errors.extend(_check_dep(name, value, opt.get('conflicts', []),
                                 lambda x: x in conf and not has_default(x), CONFLICTS))
        errors.extend(_check_dep(name, value, opt.get('requires', []),
                                 lambda x: x not in conf, REQUIRES))

    return errors


def _check_dep(name, value, lst, matcher, fmt):
    for deps in [deps for (func, deps) in lst if func(value)]:
        for dep in [d for d in deps if matcher(d)]:
            yield fmt.format(name, value, dep)


def validate(config, offline=False):
    """Test the configuration against schema.

    Undefined values for which a default value exists will be filled in.
    """
    schema = make_schema()
    DefaultValidator = _extend_with_default_and_alias(
        jsonschema.Draft4Validator, offline=offline
    )
    validator = DefaultValidator(
        schema,
        {"array": (tuple, list), "regex": six.string_types, "url": six.string_types}
    )
    errors = []
    warnings = []
    for error in validator.iter_errors(config):
        if isinstance(error, ConfigDeprecation):
            warnings.append(REMOVED.format('.'.join(error.path), error.message))
        elif isinstance(error, ConfigOptionWarning):
            warnings.append(error.message)
        elif isinstance(error, ConfigOptionError):
            errors.append(error.message)
        elif not error.path and error.validator == 'additionalProperties':
            allowed_keys = set(error.schema['properties'].keys())
            used_keys = set(error.instance.keys())
            for key in used_keys - allowed_keys:
                suggestion = _get_suggestion(key, allowed_keys)
                if suggestion:
                    warnings.append(UNKNOWN_SUGGEST.format(key, suggestion))
                else:
                    warnings.append(UNKNOWN.format(key))
        else:
            errors.append('Failed validation in %s: %s' % (
                '.'.join([str(x) for x in error.path]), error.message))
            if error.validator in ("anyOf", "oneOf"):
                for suberror in error.context:
                    errors.append("    Possible reason: %s" % suberror.message)
    return (errors + _validate_requires(schema, config, CONFIG_DEPS),
            warnings)


def _get_suggestion(desired, names):
    """Find a value in ``names`` that is the closest match for ``desired``.

    The edit distance must be at most half the length of target string.
    """
    closest = None
    closest_match = len(desired) + 1
    for name in names:
        match = util.levenshtein(desired, name)
        if match < closest_match and match < len(desired) // 2:
            closest = name
            closest_match = match

    return closest


CONFLICTS = 'ERROR: Config option {0}={1} conflicts with option {2}.'
REQUIRES = 'ERROR: Config option {0}={1} requires {2} which is not set.'
REMOVED = 'WARNING: Config option {0} was removed and has no effect; {1}.'
UNKNOWN = 'WARNING: Unrecognized config option: {0}.'
UNKNOWN_SUGGEST = 'WARNING: Unrecognized config option: {0}. Did you mean {1}?'


def _extend_with_default_and_alias(validator_class, offline=False):
    validate_properties = validator_class.VALIDATORS["properties"]
    validate_type = validator_class.VALIDATORS['type']
    validate_required = validator_class.VALIDATORS['required']
    validate_additional_properties = validator_class.VALIDATORS['additionalProperties']
    resolver = util.GitUrlResolver(offline=offline)

    def _hook_errors(properties, instance, schema):
        """
        Hook the instance and yield errors and warnings.
        """
        for property, subschema in properties.items():
            # update instance for alias option
            # If alias option for the property is present and property is not specified,
            # update the property in instance with value from alias option.
            if "alias" in subschema:
                if subschema['alias'] in instance:
                    msg = "WARNING: Config option '%s' is deprecated and now an alias to '%s', " \
                          "please use '%s' instead. " \
                          "In:\n%s" % (subschema['alias'], property, property, instance)
                    yield ConfigOptionWarning(msg)
                    if property in instance:
                        msg = "ERROR: Config option '%s' is an alias of '%s', only one can be used." \
                              % (subschema['alias'], property)
                        yield ConfigOptionError(msg)
                        instance.pop(subschema['alias'])
                    else:
                        instance.setdefault(property, instance.pop(subschema['alias']))
            # update instance for append option
            # If append is defined in schema, append values from append options to property. If property
            # is not present in instance, set it to empty list, and append the values from append options.
            # Note: property's schema must support a list of values.
            if "append" in subschema:
                appends = force_list(subschema['append'])
                for append in appends:
                    if append in instance:
                        msg = "WARNING: Config option '%s' is deprecated, its value will be appended to option '%s'. " \
                              "In:\n%s" % (append, property, instance)
                        yield ConfigOptionWarning(msg)
                        if property in instance:
                            msg = "WARNING: Value from config option '%s' is now appended to option '%s'." \
                                  % (append, property)
                            yield ConfigOptionWarning(msg)
                            instance[property] = force_list(instance[property])
                            instance[property].extend(force_list(instance.pop(append)))
                        else:
                            msg = "WARNING: Config option '%s' is not found, but '%s' is specified, value from '%s' " \
                                  "is now added as '%s'." % (property, append, append, property)
                            yield ConfigOptionWarning(msg)
                            instance[property] = instance.pop(append)

    def properties_validator(validator, properties, instance, schema):
        """
        Assign default values to options that have them defined and are not
        specified. Resolve URLs to Git repos
        """
        for property, subschema in properties.items():
            if "default" in subschema and property not in instance:
                instance.setdefault(property, subschema["default"])

            # Resolve git URL references to actual commit hashes
            if subschema.get("type") == "url" and property in instance:
                try:
                    instance[property] = resolver(instance[property])
                except util.GitUrlResolveError as exc:
                    yield ConfigOptionError(exc)

            # Resolve branch in scm dicts.
            if (
                # Schema says it can be an scm dict
                subschema.get("$ref") == "#/definitions/str_or_scm_dict"
                # and the data is actually a dict
                and isinstance(instance.get(property), dict)
                # and it's git
                and instance[property]["scm"] == "git"
                # and there's a repo URL specified
                and "repo" in instance[property]
            ):
                instance[property]["branch"] = resolver(
                    instance[property]["repo"],
                    instance[property].get("branch") or "HEAD",
                )

        for error in _hook_errors(properties, instance, schema):
            yield error

        for error in validate_properties(validator, properties, instance, schema):
            yield error

    def _validate_additional_properties(validator, aP, instance, schema):
        properties = schema.get("properties", {})
        for error in _hook_errors(properties, instance, schema):
            yield error

        for error in validate_additional_properties(validator, aP, instance, schema):
            yield error

    def _validate_required(validator, required, instance, schema):
        properties = schema.get("properties", {})
        for error in _hook_errors(properties, instance, schema):
            yield error

        for error in validate_required(validator, required, instance, schema):
            yield error

    def error_on_deprecated(validator, properties, instance, schema):
        """Unconditionally raise deprecation error if encountered."""
        yield ConfigDeprecation(properties)

    def validate_regex_type(validator, properties, instance, schema):
        """
        Extend standard type validation to check correctness in regular
        expressions.
        """
        if properties == 'regex':
            try:
                re.compile(instance)
            except re.error as exc:
                yield jsonschema.ValidationError(
                    'incorrect regular expression: %s' % str(exc),
                )
        else:
            # Not a regular expression, delegate to original validator.
            for error in validate_type(validator, properties, instance, schema):
                yield error

    def _validate_any_of(validator, anyOf, instance, schema):
        """
        Overwrite jsonschema's anyOf validator to not yield ValidationError when
        ConfigOptionWarning is found.
        """
        all_errors = []

        for index, subschema in enumerate(anyOf):
            errs = list(validator.descend(instance, subschema, schema_path=index))
            warnings = [err for err in errs if isinstance(err, ConfigOptionWarning)]
            errors = [err for err in errs if err not in warnings]
            if not errors:
                for warning in warnings:
                    yield warning
                break
            all_errors.extend(errors)
        else:
            yield jsonschema.ValidationError(
                "%r is not valid under any of the given schemas" % (instance,),
                context=all_errors,
            )

    return jsonschema.validators.extend(
        validator_class,
        {
            "properties": properties_validator,
            "deprecated": error_on_deprecated,
            "type": validate_regex_type,
            "required": _validate_required,
            "additionalProperties": _validate_additional_properties,
            "anyOf": _validate_any_of,
        },
    )


class ConfigDeprecation(jsonschema.exceptions.ValidationError):
    pass


class ConfigOptionWarning(jsonschema.exceptions.ValidationError):
    pass


class ConfigOptionError(jsonschema.exceptions.ValidationError):
    pass


def make_schema():
    return {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Pungi Configuration",

        "definitions": {
            "multilib_list": {
                "type": "object",
                "patternProperties": {
                    "^.+$": {"$ref": "#/definitions/list_of_strings"},
                },
                "additionalProperties": False,
            },

            "package_mapping": _variant_arch_mapping(
                {"$ref": "#/definitions/list_of_strings"}
            ),

            "scm_dict": {
                "type": "object",
                "properties": {
                    "scm": {
                        "type": "string",
                        "enum": ["file", "cvs", "git", "rpm"],
                    },
                    "repo": {"type": "string"},
                    "branch": {"$ref": "#/definitions/optional_string"},
                    "file": {"type": "string"},
                    "dir": {"type": "string"},
                    "command": {"type": "string"},
                },
                "additionalProperties": False,
            },

            "str_or_scm_dict": {
                "anyOf": [
                    {"type": "string"},
                    {"$ref": "#/definitions/scm_dict"},
                ]
            },

            "repo_dict": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "baseurl": {"type": "string"},
                    "exclude": {"type": "string"},
                    "gpgcheck": {"type": "boolean"},
                    "enabled": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["baseurl"],
            },

            "repo": {
                "anyOf": [
                    {"type": "string"},
                    {"$ref": "#/definitions/repo_dict"},
                ]
            },

            "repos": _one_or_list({"$ref": "#/definitions/repo"}),

            "list_of_strings": {
                "type": "array",
                "items": {"type": "string"},
            },

            "strings": _one_or_list({"type": "string"}),

            "optional_string": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"},
                ],
            },

            "live_image_config": {
                "type": "object",
                "properties": {
                    "kickstart": {"type": "string"},
                    "ksurl": {"type": "url"},
                    "name": {"type": "string"},
                    "subvariant": {"type": "string"},
                    "target": {"type": "string"},
                    "version": {"type": "string"},
                    "repo": {"$ref": "#/definitions/repos"},
                    "specfile": {"type": "string"},
                    "scratch": {"type": "boolean"},
                    "type": {"type": "string"},
                    "sign": {"type": "boolean"},
                    "failable": {"type": "boolean"},
                    "release": {"$ref": "#/definitions/optional_string"},
                },
                "required": ["kickstart"],
                "additionalProperties": False,
                "type": "object",
            },

            "osbs_config": {
                "type": "object",
                "properties": {
                    "url": {"type": "url"},
                    "target": {"type": "string"},
                    "name": {"type": "string"},
                    "version": {"type": "string"},
                    "scratch": {"type": "boolean"},
                    "priority": {"type": "number"},
                    "repo": {
                        "$ref": "#/definitions/repos",
                        "append": "repo_from",
                    },
                    "gpgkey": {"type": "string"},
                    "git_branch": {"type": "string"},
                },
                "required": ["url", "target", "git_branch"]
            },

            "string_pairs": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": [
                        {"type": "string"},
                        {"type": "string"},
                    ],
                    "additionalItems": False,
                }
            }
        },

        "type": "object",
        "properties": {
            "release_name": {"type": "string"},
            "release_short": {"type": "string"},
            "release_version": {"type": "string"},
            "release_type": {
                "type": "string",
                "enum": RELEASE_TYPES,
                "default": "ga",
            },
            "release_is_layered": {
                "deprecated": "remove it. It's layered if there's configuration for base product"
            },
            "release_internal": {"type": "boolean", "default": False},
            "release_discinfo_description": {"type": "string"},

            "compose_type": {
                "type": "string",
                "enum": COMPOSE_TYPES,
            },

            "base_product_name": {"type": "string"},
            "base_product_short": {"type": "string"},
            "base_product_version": {"type": "string"},
            "base_product_type": {
                "type": "string",
                "default": "ga"
            },

            "runroot": {
                "deprecated": "remove it. Please specify 'runroot_method' if you want to enable runroot, otherwise run things locally",
            },
            "runroot_method": {
                "type": "string",
                "enum": ["local", "koji", "openssh"],
            },
            "runroot_ssh_username": {
                "type": "string",
                "default": "root",
            },
            "runroot_ssh_hostnames": {
                "type": "object",
                "default": {},
            },
            "runroot_ssh_init_template": {
                "type": "string",
            },
            "runroot_ssh_install_packages_template": {
                "type": "string",
            },
            "runroot_ssh_run_template": {
                "type": "string",
            },
            "create_jigdo": {
                "type": "boolean",
                "default": True,
            },
            "check_deps": {
                "type": "boolean",
                "default": True
            },
            "require_all_comps_packages": {
                "type": "boolean",
                "default": False,
            },
            "bootable": {
                "type": "boolean",
                "default": False
            },

            "gather_method": {
                "oneOf": [
                    {
                        "type": "object",
                        "patternProperties": {
                            ".+": {
                                "oneOf": [
                                    {
                                        "type": "string",
                                        "enum": ["hybrid"],
                                    },
                                    {
                                        "type": "object",
                                        "patternProperties": {
                                            "^module|comps|json$": {
                                                "type": "string",
                                                "enum": ["deps", "nodeps"],
                                            }
                                        },
                                    }
                                ]
                            }
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": "string",
                        "enum": ["deps", "nodeps", "hybrid"],
                    }
                ],
            },
            "gather_source": {
                "deprecated": "remove it",
            },
            "gather_fulltree": {
                "type": "boolean",
                "default": False,
            },
            "gather_selfhosting": {
                "type": "boolean",
                "default": False,
            },
            "gather_prepopulate": {"$ref": "#/definitions/str_or_scm_dict"},
            "gather_source_mapping": {"type": "string"},
            "gather_backend": {
                "type": "string",
                "enum": _get_gather_backends(),
                "default": _get_default_gather_backend(),
            },
            "gather_profiler": {
                "type": "boolean",
                "default": False,
            },

            "pkgset_source": {
                "type": "string",
                "enum": ["koji", "repos"],
            },

            "createrepo_c": {
                "type": "boolean",
                "default": True,
            },
            "createrepo_checksum": {
                "type": "string",
                "default": "sha256",
                "enum": ["sha", "sha256", "sha512"],
            },
            "createrepo_use_xz": {
                "type": "boolean",
                "default": False,
            },
            "createrepo_num_threads": {
                "type": "number",
                "default": get_num_cpus(),
            },
            "createrepo_num_workers": {
                "type": "number",
                "default": 3,
            },
            "createrepo_database": {
                "type": "boolean",
            },
            "createrepo_extra_args": {
                "type": "array",
                "default": [],
                "items": {
                    "type": "string",
                },
            },
            "repoclosure_strictness": _variant_arch_mapping({
                "type": "string",
                "default": "lenient",
                "enum": ["off", "lenient", "fatal"],
            }),
            "repoclosure_backend": {
                "type": "string",
                # Gather and repoclosure both have the same backends: yum + dnf
                "default": _get_default_gather_backend(),
                "enum": _get_gather_backends(),
            },

            "old_composes_per_release_type": {
                "deprecated": "remove it. It is the default behavior now"
            },
            "hashed_directories": {
                "type": "boolean",
                "default": False,
            },
            "multilib_whitelist": {
                "$ref": "#/definitions/multilib_list",
                "default": {},
            },
            "multilib_blacklist": {
                "$ref": "#/definitions/multilib_list",
                "default": {},
            },
            "greedy_method": {
                "type": "string",
                "enum": ["none", "all", "build"],
                "default": "none",
            },
            "additional_packages": {
                "$ref": "#/definitions/package_mapping",
                "default": [],
            },
            "filter_packages": {
                "$ref": "#/definitions/package_mapping",
                "default": [],
            },
            "sigkeys": {
                "type": "array",
                "items": {"$ref": "#/definitions/optional_string"},
                "minItems": 1,
                "default": [None],
            },
            "variants_file": {"$ref": "#/definitions/str_or_scm_dict"},
            "comps_file": {"$ref": "#/definitions/str_or_scm_dict"},
            "comps_filter_environments": {
                "type": "boolean",
                "default": True
            },
            "module_defaults_dir": {"$ref": "#/definitions/str_or_scm_dict"},

            "pkgset_repos": {
                "type": "object",
                "patternProperties": {
                    ".+": {"$ref": "#/definitions/strings"},
                },
                "additionalProperties": False,
            },
            "create_optional_isos": {
                "type": "boolean",
                "default": False
            },
            "symlink_isos_to": {"type": "string"},
            "dogpile_cache_backend": {"type": "string"},
            "dogpile_cache_expiration_time": {"type": "number"},
            "dogpile_cache_arguments": {
                "type": "object",
                "default": {},
            },
            "createiso_skip": _variant_arch_mapping({"type": "boolean"}),
            "createiso_max_size": _variant_arch_mapping({"type": "number"}),
            "createiso_break_hardlinks": {
                "type": "boolean",
                "default": False,
            },
            "iso_hfs_ppc64le_compatible": {"type": "boolean", "default": True},
            "multilib": _variant_arch_mapping({
                "$ref": "#/definitions/list_of_strings"
            }),

            "runroot_tag": {"type": "string"},
            "runroot_channel": {
                "$ref": "#/definitions/optional_string",
            },
            "runroot_weights": {
                "type": "object",
                "default": {},
                "properties": {
                    "buildinstall": {"type": "number"},
                    "createiso": {"type": "number"},
                    "ostree": {"type": "number"},
                    "ostree_installer": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "createrepo_deltas": {
                "anyOf": [
                    # Deprecated in favour of more granular settings.
                    {
                        "type": "boolean",
                        "default": False,
                    },
                    _variant_arch_mapping({"type": "boolean"})
                ]
            },

            "buildinstall_method": {
                "type": "string",
                "enum": ["lorax", "buildinstall"],
            },
            "buildinstall_topdir": {"type": "string"},
            "buildinstall_kickstart": {"$ref": "#/definitions/str_or_scm_dict"},
            "buildinstall_use_guestmount": {"type": "boolean", "default": True},
            "buildinstall_skip": _variant_arch_mapping({"type": "boolean"}),

            "global_ksurl": {"type": "url"},
            "global_version": {"type": "string"},
            "global_target": {"type": "string"},
            "global_release": {"$ref": "#/definitions/optional_string"},

            "pdc_url": {"deprecated": "Koji is queried instead"},
            "pdc_develop": {"deprecated": "Koji is queried instead"},
            "pdc_insecure": {"deprecated": "Koji is queried instead"},

            "koji_profile": {"type": "string"},
            "koji_event": {"type": "number"},

            "pkgset_koji_tag": {"$ref": "#/definitions/strings"},
            "pkgset_koji_builds": {"$ref": "#/definitions/strings"},
            "pkgset_koji_module_tag": {
                "$ref": "#/definitions/strings",
                "default": [],
            },
            "pkgset_koji_inherit": {
                "type": "boolean",
                "default": True
            },
            "pkgset_koji_inherit_modules": {
                "type": "boolean",
                "default": False
            },
            "pkgset_exclusive_arch_considers_noarch": {
                "type": "boolean",
                "default": True,
            },

            "disc_types": {
                "type": "object",
                "default": {},
            },

            "paths_module": {"type": "string"},
            "skip_phases": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": PHASES_NAMES,
                },
                "default": [],
            },

            "image_name_format": {
                "oneOf": [
                    {
                        "type": "string"
                    },
                    {
                        "type": "object",
                        "patternProperties": {
                            # Warning: this pattern is a variant uid regex, but the
                            # format does not let us validate it as there is no regular
                            # expression to describe all regular expressions.
                            ".+": _one_or_list({"type": "string"}),
                        },
                        "additionalProperties": False,
                    },
                ],
            },
            "image_volid_formats": {
                "$ref": "#/definitions/list_of_strings",
                "default": [
                    "{release_short}-{version} {variant}.{arch}",
                    "{release_short}-{version} {arch}",
                ],
            },
            "image_volid_layered_product_formats": {
                "$ref": "#/definitions/list_of_strings",
                "default": [
                    "{release_short}-{version} {base_product_short}-{base_product_version} {variant}.{arch}",
                    "{release_short}-{version} {base_product_short}-{base_product_version} {arch}",
                ],
            },
            "restricted_volid": {
                "type": "boolean",
                "default": False,
            },
            "volume_id_substitutions": {
                "type": "object",
                "default": {},
            },

            "live_images_no_rename": {
                "type": "boolean",
                "default": False,
            },
            "live_images_ksurl": {"type": "url"},
            "live_images_target": {"type": "string"},
            "live_images_release": {"$ref": "#/definitions/optional_string"},
            "live_images_version": {"type": "string"},

            "image_build_ksurl": {"type": "url"},
            "image_build_target": {"type": "string"},
            "image_build_release": {"$ref": "#/definitions/optional_string"},
            "image_build_version": {"type": "string"},

            "live_media_ksurl": {"type": "url"},
            "live_media_target": {"type": "string"},
            "live_media_release": {"$ref": "#/definitions/optional_string"},
            "live_media_version": {"type": "string"},

            "media_checksums": {
                "$ref": "#/definitions/list_of_strings",
                "default": ['md5', 'sha1', 'sha256']
            },
            "media_checksum_one_file": {
                "type": "boolean",
                "default": False
            },
            "media_checksum_base_filename": {
                "type": "string",
                "default": ""
            },

            "filter_system_release_packages": {
                "type": "boolean",
                "default": True,
            },
            "keep_original_comps": {
                "deprecated": "remove <groups> tag from respective variant in variants XML"
            },

            "link_type": {
                "type": "string",
                "enum": ["hardlink", "copy", "hardlink-or-copy", "symlink", "abspath-symlink"],
                "default": "hardlink-or-copy"
            },

            "product_id": {"$ref": "#/definitions/str_or_scm_dict"},
            "product_id_allow_missing": {
                "type": "boolean",
                "default": False
            },

            # Deprecated in favour of regular local/phase/global setting.
            "live_target": {"type": "string"},

            "tree_arches": {
                "$ref": "#/definitions/list_of_strings",
                "default": []
            },
            "tree_variants": {
                "$ref": "#/definitions/list_of_strings",
                "default": []
            },

            "translate_paths": {
                "$ref": "#/definitions/string_pairs",
                "default": [],
            },

            "failable_deliverables": _variant_arch_mapping({
                "$ref": "#/definitions/list_of_strings"
            }),

            "extra_isos": {
                "type": "object",
                "patternProperties": {
                    # Warning: this pattern is a variant uid regex, but the
                    # format does not let us validate it as there is no regular
                    # expression to describe all regular expressions.
                    ".+": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "include_variants": {"$ref": "#/definitions/strings"},
                                "extra_files": _one_or_list({
                                    "type": "object",
                                    "properties": {
                                        "scm": {"type": "string"},
                                        "repo": {"type": "string"},
                                        "branch": {"$ref": "#/definitions/optional_string"},
                                        "file": {"$ref": "#/definitions/strings"},
                                        "dir": {"$ref": "#/definitions/strings"},
                                        "target": {"type": "string"},
                                    },
                                    "additionalProperties": False,
                                }),
                                "filename": {"type": "string"},
                                "volid": {"$ref": "#/definitions/strings"},
                                "arches": {"$ref": "#/definitions/list_of_strings"},
                                "failable_arches": {
                                    "$ref": "#/definitions/list_of_strings"
                                },
                                "skip_src": {
                                    "type": "boolean",
                                    "default": False,
                                },
                                "inherit_extra_files": {
                                    "type": "boolean",
                                    "default": False,
                                },
                                "max_size": {"type": "number"},
                            },
                            "required": ["include_variants"],
                            "additionalProperties": False
                        }
                    }
                }
            },

            "live_media": {
                "type": "object",
                "patternProperties": {
                    # Warning: this pattern is a variant uid regex, but the
                    # format does not let us validate it as there is no regular
                    # expression to describe all regular expressions.
                    ".+": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "install_tree_from": {"type": "string"},
                                "kickstart": {"type": "string"},
                                "ksversion": {"type": "string"},
                                "ksurl": {"type": "url"},
                                "version": {"type": "string"},
                                "scratch": {"type": "boolean"},
                                "skip_tag": {"type": "boolean"},
                                "name": {"type": "string"},
                                "subvariant": {"type": "string"},
                                "title": {"type": "string"},
                                "repo": {"$ref": "#/definitions/repos"},
                                "target": {"type": "string"},
                                "arches": {"$ref": "#/definitions/list_of_strings"},
                                "failable": {"$ref": "#/definitions/list_of_strings"},
                                "release": {"$ref": "#/definitions/optional_string"},
                            },
                            "required": ["name", "kickstart"],
                            "additionalProperties": False,
                        },
                    }
                },
                "additionalProperties": False,
            },

            "ostree": {
                "anyOf": [
                    {
                        "type": "object",
                        "patternProperties": {
                            # Warning: this pattern is a variant uid regex, but the
                            # format does not let us validate it as there is no regular
                            # expression to describe all regular expressions.
                            ".+": _one_or_list({
                                "type": "object",
                                "properties": {
                                    "treefile": {"type": "string"},
                                    "config_url": {"type": "string"},
                                    "repo": {"$ref": "#/definitions/repos"},
                                    "keep_original_sources": {"type": "boolean"},
                                    "ostree_repo": {"type": "string"},
                                    "arches": {"$ref": "#/definitions/list_of_strings"},
                                    "failable": {"$ref": "#/definitions/list_of_strings"},
                                    "update_summary": {"type": "boolean"},
                                    "force_new_commit": {"type": "boolean"},
                                    "version": {"type": "string"},
                                    "config_branch": {"type": "string"},
                                    "tag_ref": {"type": "boolean"},
                                    "ostree_ref": {"type": "string"},
                                },
                                "required": ["treefile", "config_url", "repo", "ostree_repo"],
                                "additionalProperties": False,
                            }),
                        },
                        "additionalProperties": False,
                    },
                    # Deprecated in favour of the dict version above.
                    _variant_arch_mapping({
                        "type": "object",
                        "properties": {
                            "treefile": {"type": "string"},
                            "config_url": {"type": "string"},
                            "repo": {
                                "$ref": "#/definitions/repos",
                                "alias": "extra_source_repos",
                                "append": ["repo_from", "source_repo_from"],
                            },
                            "keep_original_sources": {"type": "boolean"},
                            "ostree_repo": {"type": "string"},
                            "failable": {"$ref": "#/definitions/list_of_strings"},
                            "update_summary": {"type": "boolean"},
                            "force_new_commit": {"type": "boolean"},
                            "version": {"type": "string"},
                            "config_branch": {"type": "string"},
                            "tag_ref": {"type": "boolean"},
                            "ostree_ref": {"type": "string"},
                        },
                        "required": ["treefile", "config_url", "ostree_repo"],
                        "additionalProperties": False,
                    }),
                ]
            },

            "ostree_installer": _variant_arch_mapping({
                "type": "object",
                "properties": {
                    "repo": {"$ref": "#/definitions/repos"},
                    "release": {"$ref": "#/definitions/optional_string"},
                    "failable": {"$ref": "#/definitions/list_of_strings"},
                    "installpkgs": {"$ref": "#/definitions/list_of_strings"},
                    "add_template": {"$ref": "#/definitions/list_of_strings"},
                    "add_arch_template": {"$ref": "#/definitions/list_of_strings"},
                    "add_template_var": {"$ref": "#/definitions/list_of_strings"},
                    "add_arch_template_var": {"$ref": "#/definitions/list_of_strings"},
                    "rootfs_size": {"type": "string"},
                    "template_repo": {"type": "string"},
                    "template_branch": {"type": "string"},
                },
                "additionalProperties": False,
            }),

            "ostree_installer_overwrite": {
                "type": "boolean",
                "default": False,
            },

            "live_images": _variant_arch_mapping(
                _one_or_list({"$ref": "#/definitions/live_image_config"})
            ),

            "image_build": {
                "type": "object",
                "patternProperties": {
                    # Warning: this pattern is a variant uid regex, but the
                    # format does not let us validate it as there is no regular
                    # expression to describe all regular expressions.
                    ".+": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "image-build": {
                                    "type": "object",
                                    "properties": {
                                        "failable": {"$ref": "#/definitions/list_of_strings"},
                                        "disc_size": {"type": "number"},
                                        "distro": {"type": "string"},
                                        "name": {"type": "string"},
                                        "kickstart": {"type": "string"},
                                        "ksurl": {"type": "url"},
                                        "arches": {"$ref": "#/definitions/list_of_strings"},
                                        "repo": {
                                            "$ref": "#/definitions/repos",
                                            "append": "repo_from",
                                        },
                                        "install_tree_from": {"type": "string"},
                                        "subvariant": {"type": "string"},
                                        "format": {
                                            "anyOf": [
                                                # The variant with explicit extension is deprecated.
                                                {"$ref": "#/definitions/string_pairs"},
                                                {"$ref": "#/definitions/strings"}
                                            ]
                                        },
                                    },
                                },
                                "factory-parameters": {
                                    "type": "object",
                                },
                            },
                            "required": ["image-build"],
                            "additionalProperties": False,
                        }
                    }
                },
                "additionalProperties": False,
            },

            "lorax_options": _variant_arch_mapping({
                "type": "object",
                "properties": {
                    "bugurl": {"type": "string"},
                    "nomacboot": {"type": "boolean"},
                    "noupgrade": {"type": "boolean"},
                    'add_template': {"$ref": "#/definitions/list_of_strings"},
                    'add_arch_template': {"$ref": "#/definitions/list_of_strings"},
                    'add_template_var': {"$ref": "#/definitions/list_of_strings"},
                    'add_arch_template_var': {"$ref": "#/definitions/list_of_strings"},
                    "rootfs_size": {"type": "integer"},
                    "version": {"type": "string"},
                },
                "additionalProperties": False,
            }),

            "lorax_extra_sources": _variant_arch_mapping({
                "$ref": "#/definitions/strings",
            }),

            "signing_key_id": {"type": "string"},
            "signing_key_password_file": {"type": "string"},
            "signing_command": {"type": "string"},
            "productimg": {
                "type": "boolean",
                "default": False
            },
            "productimg_install_class": {"$ref": "#/definitions/str_or_scm_dict"},
            "productimg_po_files": {"$ref": "#/definitions/str_or_scm_dict"},
            "iso_size": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                ],
                "default": 4700000000,
            },
            "split_iso_reserve": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                ],
                "default": 10 * 1024 * 1024
            },

            "osbs": {
                "type": "object",
                "patternProperties": {
                    # Warning: this pattern is a variant uid regex, but the
                    # format does not let us validate it as there is no regular
                    # expression to describe all regular expressions.
                    ".+": _one_or_list({"$ref": "#/definitions/osbs_config"}),
                },
                "additionalProperties": False,
            },
            "osbs_registries": {
                "type": "object",
                "patternProperties": {
                    # There are no restrictions on what the value can be.
                    ".+": {}
                },
                "additionalProperties": False,
            },

            "extra_files": _variant_arch_mapping({
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "scm": {"type": "string"},
                        "repo": {"type": "string"},
                        "branch": {"$ref": "#/definitions/optional_string"},
                        "file": {"$ref": "#/definitions/strings"},
                        "dir": {"type": "string"},
                        "target": {"type": "string"},
                    },
                    "additionalProperties": False,
                }
            }),

            "gather_lookaside_repos": _variant_arch_mapping({
                "$ref": "#/definitions/strings",
            }),

            "variant_as_lookaside": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": [
                        {"type": "string"},
                        {"type": "string"},
                    ],
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        },

        "required": ["release_name", "release_short", "release_version",
                     "variants_file",
                     "pkgset_source",
                     "gather_method"],
        "additionalProperties": False,
    }


def _variant_arch_mapping(value):
    return {
        "type": "array",
        "items": {
            "type": "array",
            "items": [
                {"type": "regex"},
                {
                    "type": "object",
                    "patternProperties": {".+": value},
                    "additionalProperties": False
                }
            ],
            "additionalItems": False,
            "minItems": 2,
        },
        "default": []
    }


def _one_or_list(value):
    """Require either `value` or a list of `value`s."""
    return {
        "anyOf": [
            value,
            {
                "type": "array",
                "items": value,
            },
        ],
    }


def get_num_cpus():
    try:
        return multiprocessing.cpu_count()
    except NotImplementedError:
        return 3


# This is a mapping of configuration option dependencies and conflicts.
#
# The key in this mapping is the trigger for the check. When the option is
# encountered and its value satisfies the lambda, an error is reported for each
# missing (for requires) option in the list.
CONFIG_DEPS = {
    "productimg": {
        "requires": (
            (lambda x: bool(x), ["productimg_install_class"]),
            (lambda x: bool(x), ["productimg_po_files"]),
        ),
    },

    "bootable": {
        "requires": (
            (lambda x: x, ["buildinstall_method"]),
        ),
        "conflicts": (
            (lambda x: not x, ["buildinstall_method"]),
        ),
    },
    "buildinstall_method": {
        "conflicts": (
            (lambda val: val == "buildinstall", ["lorax_options"]),
            (lambda val: not val, ["lorax_options", "buildinstall_kickstart"]),
        ),
    },
    "base_product_name": {
        "requires": (
            (lambda x: x, ["base_product_short", "base_product_version"]),
        ),
        "conflicts": (
            (lambda x: not x, ["base_product_short", "base_product_version"]),
        ),
    },
    "base_product_short": {
        "requires": (
            (lambda x: x, ["base_product_name", "base_product_version"]),
        ),
        "conflicts": (
            (lambda x: not x, ["base_product_name", "base_product_version"]),
        ),
    },
    "base_product_version": {
        "requires": (
            (lambda x: x, ["base_product_name", "base_product_short"]),
        ),
        "conflicts": (
            (lambda x: not x, ["base_product_name", "base_product_short"]),
        ),
    },
    "product_id": {
        "conflicts": [
            (lambda x: not x, ['product_id_allow_missing']),
        ],
    },
    "pkgset_source": {
        "requires": [
            (lambda x: x == "repos", ["pkgset_repos"]),
        ],
        "conflicts": [
            (lambda x: x == "koji", ["pkgset_repos"]),
            (lambda x: x == "repos", ["pkgset_koji_tag", "pkgset_koji_inherit"]),
        ],
    },
}


def _get_gather_backends():
    if six.PY2:
        return ['yum', 'dnf']
    return ['dnf']


def _get_default_gather_backend():
    return 'yum' if six.PY2 else 'dnf'
