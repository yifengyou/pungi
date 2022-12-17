# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function

import argparse
import json
import os
import sys

import six

import pungi.checks
import pungi.compose
import pungi.paths
import pungi.phases
import pungi.wrappers.scm
import pungi.util
from pungi.wrappers.variants import VariantsXmlParser, VariantsValidationError
from pungi_utils import config_utils


class ValidationCompose(pungi.compose.Compose):
    def __init__(self, conf, has_old, topdir):
        self.topdir = topdir
        self.conf = conf
        self._logger = None
        self.just_phases = []
        self.skip_phases = []
        self.has_old_composes = has_old
        self.paths = pungi.paths.Paths(self)
        self.variants = {}
        self.all_variants = {}

    @property
    def old_composes(self):
        return "/dummy" if self.has_old_composes else None

    @property
    def compose_id(self):
        return "Dummy-1.0-20160811.t.0"

    @property
    def compose_type(self):
        return "test"

    @property
    def compose_date(self):
        return "20160811"

    @property
    def compose_respin(self):
        return "0"


def read_variants(compose, config):
    with pungi.util.temp_dir() as tmp_dir:
        scm_dict = compose.conf["variants_file"]
        if isinstance(scm_dict, six.string_types) and scm_dict[0] != "/":
            config_dir = os.path.dirname(config)
            scm_dict = os.path.join(config_dir, scm_dict)
        files = pungi.wrappers.scm.get_file_from_scm(scm_dict, tmp_dir)
        tree_arches = compose.conf.get("tree_arches")
        tree_variants = compose.conf.get("tree_variants")
        with open(os.path.join(tmp_dir, files[0]), "r") as file_obj:
            parser = VariantsXmlParser(file_obj, tree_arches, tree_variants)
            compose.variants = parser.parse()

    for variant in compose.variants.values():
        compose.all_variants[variant.uid] = variant
        for child in variant.get_variants():
            compose.all_variants[child.uid] = child


def make_final_schema(schema_overrides):
    # Load schema including extra schemas JSON files.
    schema = pungi.checks.make_schema()
    for schema_override in schema_overrides:
        with open(schema_override) as f:
            schema = pungi.checks.update_schema(schema, json.load(f))
    return schema


def run(config, topdir, has_old, offline, defined_variables, schema_overrides):
    # Load default values for undefined variables. This is useful for
    # validating templates that are supposed to be filled in later with
    # pungi-config-dump.
    try:
        defaults_file = os.path.join(
            os.path.dirname(config), ".pungi-config-validate.json"
        )
        with open(defaults_file) as f:
            defined_variables.update(json.load(f))
    except IOError:
        pass
    # Load actual configuration
    conf = pungi.util.load_config(config, defined_variables)
    # Remove the dummy variables used for defaults.
    config_utils.remove_unknown(conf, defined_variables)
    # Load extra schemas JSON files.
    schema = make_final_schema(schema_overrides)

    errors, warnings = pungi.checks.validate(conf, offline=offline, schema=schema)
    if errors or warnings:
        for error in errors + warnings:
            print(error)
        sys.exit(1)

    errors = []
    compose = ValidationCompose(conf, has_old, topdir)
    try:
        read_variants(compose, config)
    except VariantsValidationError as exc:
        errors.extend(str(exc).splitlines())
    except RuntimeError as exc:
        print("WARNING: Failed to load variants: %s" % exc)

    pkgset_phase = pungi.phases.PkgsetPhase(compose)
    buildinstall_phase = pungi.phases.BuildinstallPhase(compose)
    phases = [
        pungi.phases.InitPhase(compose),
        buildinstall_phase,
        pkgset_phase,
        pungi.phases.GatherPhase(compose, pkgset_phase),
        pungi.phases.ExtraFilesPhase(compose, pkgset_phase),
        pungi.phases.CreaterepoPhase(compose),
        pungi.phases.OstreeInstallerPhase(compose, buildinstall_phase),
        pungi.phases.OSTreePhase(compose),
        pungi.phases.CreateisoPhase(compose, buildinstall_phase),
        pungi.phases.ExtraIsosPhase(compose, buildinstall_phase),
        pungi.phases.LiveImagesPhase(compose),
        pungi.phases.LiveMediaPhase(compose),
        pungi.phases.ImageBuildPhase(compose),
        pungi.phases.ImageChecksumPhase(compose),
        pungi.phases.TestPhase(compose),
    ]

    for phase in phases:
        if phase.skip():
            continue
        try:
            phase.validate()
        except ValueError as ex:
            for i in str(ex).splitlines():
                errors.append("%s: %s" % (phase.name.upper(), i))

    return errors


def dump_schema(schema_overrides):
    # Load extra schemas JSON files.
    schema = make_final_schema(schema_overrides)
    json.dump(schema, sys.stdout, sort_keys=True, indent=4)
    print("")


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="print JSON Schema of configuration and exit",
    )
    parser.add_argument(
        "config", metavar="CONFIG", help="configuration file to validate"
    )
    parser.add_argument(
        "--old-composes",
        action="store_true",
        help="indicate if pungi-koji will be run with --old-composes option",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Do not validate git references in URLs"
    )
    parser.add_argument(
        "-e",
        "--define",
        action="append",
        default=[],
        metavar="VAR=VALUE",
        type=config_utils.validate_definition,
        help=(
            "Define a variable on command line and inject it into the config file. "
            "Can be used multiple times."
        ),
    )
    parser.add_argument(
        "--schema-override",
        action="append",
        default=[],
        help=(
            "Path to extra JSON schema defining the values which will override "
            "the original Pungi JSON schema values."
        ),
    )
    opts = parser.parse_args(args)
    defines = config_utils.extract_defines(opts.define)

    if opts.dump_schema:
        dump_schema(opts.schema_override)
        sys.exit(0)

    with pungi.util.temp_dir() as topdir:
        errors = run(
            opts.config,
            topdir,
            opts.old_composes,
            opts.offline,
            defines,
            opts.schema_override,
        )

    for msg in errors:
        print(msg)

    return bool(errors)


def cli_main():
    if main():
        sys.exit(1)
