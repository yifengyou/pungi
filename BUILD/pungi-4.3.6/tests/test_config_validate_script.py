# -*- coding: utf-8 -*-


import mock
import os
import six

from pungi.scripts.config_validate import cli_main
from tests import helpers


HERE = os.path.abspath(os.path.dirname(__file__))
DUMMY_CONFIG = os.path.join(HERE, "data/dummy-pungi.conf")
SCHEMA_OVERRIDE = os.path.join(HERE, "data/dummy-override.json")


class ConfigValidateScriptTest(helpers.PungiTestCase):
    @mock.patch("sys.argv", new=["pungi-config-validate", DUMMY_CONFIG])
    @mock.patch("sys.stderr", new_callable=six.StringIO)
    @mock.patch("sys.stdout", new_callable=six.StringIO)
    def test_validate_dummy_config(self, stdout, stderr):
        cli_main()
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    @mock.patch(
        "sys.argv",
        new=[
            "pungi-config-validate",
            DUMMY_CONFIG,
            "--schema-override",
            SCHEMA_OVERRIDE,
        ],
    )
    @mock.patch("sys.stderr", new_callable=six.StringIO)
    @mock.patch("sys.stdout", new_callable=six.StringIO)
    @mock.patch("sys.exit")
    def test_schema_override(self, exit, stdout, stderr):
        cli_main()
        self.assertTrue(
            stdout.getvalue().startswith(
                "Failed validation in pkgset_source: 'repos' is not one of"
            )
        )
        self.assertEqual("", stderr.getvalue())
        exit.assert_called_once_with(1)
