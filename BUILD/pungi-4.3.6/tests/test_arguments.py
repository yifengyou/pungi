import mock

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import six

from pungi.scripts.pungi_koji import cli_main


class PungiKojiTestCase(unittest.TestCase):
    @mock.patch("sys.argv", new=["prog", "--version"])
    @mock.patch("sys.stderr", new_callable=six.StringIO)
    @mock.patch("sys.stdout", new_callable=six.StringIO)
    @mock.patch("pungi.scripts.pungi_koji.get_full_version", return_value="a-b-c.111")
    def test_version(self, get_full_version, stdout, stderr):
        with self.assertRaises(SystemExit) as cm:
            cli_main()
        self.assertEqual(cm.exception.code, 0)
        # Python 2.7 prints the version to stderr, 3.4+ to stdout.
        if six.PY3:
            self.assertMultiLineEqual(stdout.getvalue(), "a-b-c.111\n")
        else:
            self.assertMultiLineEqual(stderr.getvalue(), "a-b-c.111\n")
