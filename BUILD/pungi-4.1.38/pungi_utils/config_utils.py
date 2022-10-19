# -*- coding: utf-8 -*-

import argparse
import re

from pungi.checks import make_schema


def validate_definition(value):
    """Check that the variable name is a valid Python variable name, and that
    there is an equals sign. The value can by anything non-empty.
    """
    if not re.match(r"^[a-z_]\w*=.*$", value):
        raise argparse.ArgumentTypeError(
            "definition should be in var=value format: %r" % value
        )
    return value


def extract_defines(args):
    """Given an iterable of "key=value" strings, parse them into a dict."""
    return dict(var.split("=", 1) for var in args)


def remove_unknown(conf, keys):
    """Remove given keys from the config unless they are known Pungi options."""
    schema = make_schema()
    for key in keys:
        if key not in schema["properties"]:
            del conf[key]
