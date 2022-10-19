# -*- coding: utf-8 -*-

import mock
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import os
import sys
from six import StringIO

import kobo.conf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pungi import checks


class CheckDependenciesTestCase(unittest.TestCase):

    def dont_find(self, paths):
        return lambda path: path not in paths

    def test_all_deps_missing(self):
        def custom_exists(path):
            return False

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = custom_exists
                result = checks.check({})

        self.assertGreater(len(out.getvalue().strip().split('\n')), 1)
        self.assertFalse(result)

    def test_all_deps_ok(self):
        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('platform.machine') as machine:
                machine.return_value = 'x86_64'
                with mock.patch('os.path.exists') as exists:
                    exists.side_effect = self.dont_find([])
                    result = checks.check({})

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_does_not_require_jigdo_if_not_configured(self):
        conf = {
            'create_jigdo': False
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('platform.machine') as machine:
                machine.return_value = 'x86_64'
                with mock.patch('os.path.exists') as exists:
                    exists.side_effect = self.dont_find(['/usr/bin/jigdo-lite'])
                    result = checks.check(conf)

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_isohybrid_not_required_without_productimg_phase(self):
        conf = {
            'bootable': True,
            'productimg': False,
            'runroot_tag': 'dummy_tag',
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/isohybrid'])
                result = checks.check(conf)

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_isohybrid_not_required_on_not_bootable(self):
        conf = {
            'bootable': False,
            'runroot_tag': 'dummy_tag',
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/isohybrid'])
                result = checks.check(conf)

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_isohybrid_not_required_on_arm(self):
        conf = {
            'bootable': True,
            'productimg': True,
            'runroot_tag': 'dummy_tag',
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('platform.machine') as machine:
                machine.return_value = 'armhfp'
                with mock.patch('os.path.exists') as exists:
                    exists.side_effect = self.dont_find(['/usr/bin/isohybrid'])
                    result = checks.check(conf)

        self.assertRegexpMatches(out.getvalue(), r'^Not checking.*Expect failures.*$')
        self.assertTrue(result)

    def test_isohybrid_not_needed_in_runroot(self):
        conf = {
            'runroot_tag': 'dummy_tag',
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/isohybrid'])
                result = checks.check(conf)

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_genisoimg_not_needed_in_runroot(self):
        conf = {
            'runroot_tag': 'dummy_tag',
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/genisoimage'])
                result = checks.check(conf)

        self.assertEqual('', out.getvalue())
        self.assertTrue(result)

    def test_genisoimg_needed_for_productimg(self):
        conf = {
            'runroot_tag': 'dummy_tag',
            'productimg': True,
            'bootable': True,
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/genisoimage'])
                result = checks.check(conf)

        self.assertIn('genisoimage', out.getvalue())
        self.assertFalse(result)

    def test_requires_modifyrepo(self):
        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/modifyrepo'])
                result = checks.check({'createrepo_c': False})

        self.assertIn('createrepo', out.getvalue())
        self.assertFalse(result)

    def test_requires_modifyrepo_c(self):
        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/modifyrepo_c'])
                result = checks.check({'createrepo_c': True})

        self.assertIn('createrepo_c', out.getvalue())
        self.assertFalse(result)

    def test_requires_createrepo_c(self):
        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/createrepo_c'])
                result = checks.check({})

        self.assertIn('createrepo_c', out.getvalue())
        self.assertFalse(result)

    def test_doesnt_require_createrepo_c_if_configured(self):
        conf = {
            'createrepo_c': False,
        }

        with mock.patch('sys.stdout', new_callable=StringIO) as out:
            with mock.patch('os.path.exists') as exists:
                exists.side_effect = self.dont_find(['/usr/bin/createrepo_c'])
                result = checks.check(conf)

        self.assertNotIn('createrepo_c', out.getvalue())
        self.assertTrue(result)


class TestSchemaValidator(unittest.TestCase):
    def _load_conf_from_string(self, string):
        conf = kobo.conf.PyConfigParser()
        conf.load_from_string(string)
        return conf

    @mock.patch('pungi.checks.make_schema')
    def test_property(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
            },
            "additionalProperties": False,
            "required": ["release_name"],
        }
        make_schema.return_value = schema

        string = """
        release_name = "dummy product"
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(config.get("release_name", None), "dummy product")

    @mock.patch('pungi.checks.make_schema')
    def test_alias_property(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
            },
            "additionalProperties": False,
        }
        make_schema.return_value = schema

        string = """
        product_name = "dummy product"
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 1)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'product_name' is deprecated and now an alias to 'release_name'.*")
        self.assertEqual(config.get("release_name", None), "dummy product")

    @mock.patch('pungi.checks.make_schema')
    def test_required_is_missing(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
            },
            "additionalProperties": False,
            "required": ["release_name"],
        }
        make_schema.return_value = schema

        string = """
        name = "dummy product"
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 1)
        self.assertIn("Failed validation in : 'release_name' is a required property", errors)
        self.assertEqual(len(warnings), 1)
        self.assertIn("WARNING: Unrecognized config option: name.", warnings)

    @mock.patch('pungi.checks.make_schema')
    def test_required_is_in_alias(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
            },
            "additionalProperties": False,
            "required": ["release_name"],
        }
        make_schema.return_value = schema

        string = """
        product_name = "dummy product"
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 1)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'product_name' is deprecated and now an alias to 'release_name'.*")
        self.assertEqual(config.get("release_name", None), "dummy product")

    @mock.patch('pungi.checks.make_schema')
    def test_redundant_alias(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
            },
            "additionalProperties": False,
            "required": ["release_name"],
        }
        make_schema.return_value = schema

        string = """
        product_name = "dummy product"
        release_name = "dummy product"
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 1)
        self.assertRegexpMatches(errors[0], r"^ERROR: Config option 'product_name' is an alias of 'release_name', only one can be used.*")
        self.assertEqual(len(warnings), 1)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'product_name' is deprecated and now an alias to 'release_name'.*")
        self.assertEqual(config.get("release_name", None), "dummy product")

    @mock.patch('pungi.checks.make_schema')
    def test_properties_in_deep(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {
                "release_name": {"type": "string", "alias": "product_name"},
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "foophase": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "alias": "tree"},
                    },
                    "additionalProperties": False,
                    "required": ["repo"],
                },
            },
            "additionalProperties": False,
            "required": ["release_name"],
        }
        make_schema.return_value = schema

        string = """
        product_name = "dummy product"
        foophase = {
            "tree": "http://www.exampe.com/os"
        }
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 2)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option '.+' is deprecated and now an alias to '.+'.*")
        self.assertRegexpMatches(warnings[1], r"^WARNING: Config option '.+' is deprecated and now an alias to '.+'.*")
        self.assertEqual(config.get("release_name", None), "dummy product")
        self.assertEqual(config.get("foophase", {}).get("repo", None), "http://www.exampe.com/os")

    @mock.patch('pungi.checks.make_schema')
    def test_append_option(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "definitions": {
                "list_of_strings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "strings": {
                    "anyOf": [
                        {"type": "string"},
                        {"$ref": "#/definitions/list_of_strings"},
                    ]
                },
            },
            "properties": {
                "release_name": {"type": "string"},
                "repo": {"$ref": "#/definitions/strings", "append": "repo_from"}
            },
            "additionalProperties": False,
        }
        make_schema.return_value = schema

        string = """
        release_name = "dummy product"
        repo = "http://url/to/repo"
        repo_from = 'Server'
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 2)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'repo_from' is deprecated, its value will be appended to option 'repo'.*")
        self.assertRegexpMatches(warnings[1], r"^WARNING: Value from config option 'repo_from' is now appended to option 'repo'")
        self.assertEqual(config.get("release_name", None), "dummy product")
        self.assertEqual(config.get("repo", None), ["http://url/to/repo", "Server"])

    @mock.patch('pungi.checks.make_schema')
    def test_append_to_nonexist_option(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "definitions": {
                "list_of_strings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "strings": {
                    "anyOf": [
                        {"type": "string"},
                        {"$ref": "#/definitions/list_of_strings"},
                    ]
                },
            },
            "properties": {
                "release_name": {"type": "string"},
                "repo": {"$ref": "#/definitions/strings", "append": "repo_from"}
            },
            "additionalProperties": False,
        }
        make_schema.return_value = schema

        string = """
        release_name = "dummy product"
        repo_from = ['http://url/to/repo', 'Server']
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 2)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'repo_from' is deprecated, its value will be appended to option 'repo'.*")
        self.assertRegexpMatches(warnings[1], r"^WARNING: Config option 'repo' is not found, but 'repo_from' is specified,")
        self.assertEqual(config.get("release_name", None), "dummy product")
        self.assertEqual(config.get("repo", None), ["http://url/to/repo", "Server"])

    @mock.patch('pungi.checks.make_schema')
    def test_multiple_appends(self, make_schema):
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "definitions": {
                "list_of_strings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "strings": {
                    "anyOf": [
                        {"type": "string"},
                        {"$ref": "#/definitions/list_of_strings"},
                    ]
                },
            },
            "properties": {
                "release_name": {"type": "string"},
                "repo": {
                    "$ref": "#/definitions/strings",
                    "append": ["repo_from", "source_repo_from"]
                }
            },
            "additionalProperties": False,
        }
        make_schema.return_value = schema

        string = """
        release_name = "dummy product"
        repo_from = ['http://url/to/repo', 'Server']
        source_repo_from = 'Client'
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 4)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'repo_from' is deprecated, its value will be appended to option 'repo'.*")
        self.assertRegexpMatches(warnings[1], r"^WARNING: Config option 'repo' is not found, but 'repo_from' is specified,")
        self.assertRegexpMatches(warnings[2], r"^WARNING: Config option 'source_repo_from' is deprecated, its value will be appended to option 'repo'")
        self.assertRegexpMatches(warnings[3], r"^WARNING: Value from config option 'source_repo_from' is now appended to option 'repo'.")
        self.assertEqual(config.get("release_name", None), "dummy product")
        self.assertEqual(config.get("repo", None), ["http://url/to/repo", "Server", "Client"])

    @mock.patch('pungi.checks.make_schema')
    def test_anyof_validator_not_raise_our_warnings_as_error(self, make_schema):
        # https://pagure.io/pungi/issue/598
        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "definitions": {
                "live_image_config": {
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "append": "repo_from",
                        },
                    },
                },
            },
            "properties": {
                "live_images": checks._variant_arch_mapping({
                    "anyOf": [
                        {"$ref": "#/definitions/live_image_config"},
                        {
                            "type": "array",
                            "items": {
                                "$ref": "#/definitions/live_image_config"
                            }
                        }
                    ]
                }),
            },
        }
        make_schema.return_value = schema

        string = """
        live_images = [
            ('^Spins$', {
                'armhfp': {
                    'repo_from': 'Everything',
            }}),
        ]
        """
        config = self._load_conf_from_string(string)
        errors, warnings = checks.validate(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 2)
        self.assertRegexpMatches(warnings[0], r"^WARNING: Config option 'repo_from' is deprecated, its value will be appended to option 'repo'.*")
        self.assertRegexpMatches(warnings[1], r"^WARNING: Config option 'repo' is not found, but 'repo_from' is specified, value from 'repo_from' is now added as 'repo'.*")
        self.assertEqual(config.get("live_images")[0][1]['armhfp']['repo'], 'Everything')

    @mock.patch("pungi.util.resolve_git_url")
    @mock.patch('pungi.checks.make_schema')
    def test_resolve_url(self, make_schema, resolve_git_url):
        resolve_git_url.return_value = "git://example.com/repo.git#CAFE"
        make_schema.return_value = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {"foo": {"type": "url"}},
        }
        config = self._load_conf_from_string("foo = 'git://example.com/repo.git#HEAD'")
        errors, warnings = checks.validate(config)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(config["foo"], resolve_git_url.return_value)

    @mock.patch("pungi.util.resolve_git_url")
    @mock.patch('pungi.checks.make_schema')
    def test_resolve_url_when_offline(self, make_schema, resolve_git_url):
        make_schema.return_value = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Pungi Configuration",
            "type": "object",
            "properties": {"foo": {"type": "url"}},
        }
        config = self._load_conf_from_string("foo = 'git://example.com/repo.git#HEAD'")
        errors, warnings = checks.validate(config, offline=True)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(config["foo"], "git://example.com/repo.git#HEAD")
        self.assertEqual(resolve_git_url.call_args_list, [])


class TestUmask(unittest.TestCase):
    def setUp(self):
        self.orig_umask = os.umask(0)
        os.umask(self.orig_umask)

    def tearDown(self):
        os.umask(self.orig_umask)

    def test_no_warning_with_0022(self):
        os.umask(0o022)
        logger = mock.Mock()
        checks.check_umask(logger)
        self.assertItemsEqual(logger.mock_calls, [])

    def test_no_warning_with_0000(self):
        os.umask(0o000)
        logger = mock.Mock()
        checks.check_umask(logger)
        self.assertItemsEqual(logger.mock_calls, [])

    def test_warning_with_0044(self):
        os.umask(0o044)
        logger = mock.Mock()
        checks.check_umask(logger)
        self.assertItemsEqual(
            logger.mock_calls,
            [mock.call.warning('Unusually strict umask detected (0%03o), '
                               'expect files with broken permissions.', 0o044)]
        )
