# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest
import mock

from pungi import media_split


class ConvertMediaSizeTestCase(unittest.TestCase):
    def test_size_parser_correct_number_as_int(self):
        self.assertEqual(media_split.convert_media_size(123), 123)

    def test_size_parser_correct_number_as_str(self):
        self.assertEqual(media_split.convert_media_size("123"), 123)

    def test_size_parser_with_unit_b(self):
        self.assertEqual(media_split.convert_media_size("123b"), 123)

    def test_size_parser_with_unit_k(self):
        self.assertEqual(media_split.convert_media_size("123k"), 123 * 1024)

    def test_size_parser_with_unit_M(self):
        self.assertEqual(media_split.convert_media_size("123M"), 123 * 1024 * 1024)

    def test_size_parser_with_unit_G(self):
        self.assertEqual(
            media_split.convert_media_size("123G"), 123 * 1024 * 1024 * 1024
        )

    def test_size_parser_with_negative_number(self):
        with self.assertRaises(ValueError):
            media_split.convert_media_size(-15)

    def test_size_parser_with_unknown_unit(self):
        with self.assertRaises(ValueError):
            media_split.convert_media_size("123X")


class ConvertFileSizeTestCase(unittest.TestCase):
    def test_round_up(self):
        self.assertEqual(media_split.convert_file_size(123, 2048), 2048)

    def test_exactly_block_size(self):
        self.assertEqual(media_split.convert_file_size(100, 100), 100)


def bl(s):
    return s * 2048


class MediaSplitterTestCase(unittest.TestCase):
    def setUp(self):
        self.compose = mock.Mock()

    def test_sum_size(self):
        ms = media_split.MediaSplitter(bl(100))
        ms.add_file("first", bl(20))
        ms.add_file("second", bl(30))
        ms.add_file("third", 10)

        self.assertEqual(ms.total_size, bl(50) + 10)
        self.assertEqual(ms.total_size_in_blocks, bl(51))

    def test_add_same_file_twice(self):
        ms = media_split.MediaSplitter(bl(100))
        ms.add_file("first", bl(20))
        ms.add_file("first", bl(20))

        self.assertEqual(ms.total_size, bl(20))

    def test_add_same_file_twice_with_different_size(self):
        ms = media_split.MediaSplitter(bl(100))
        ms.add_file("first", bl(20))
        with self.assertRaises(ValueError):
            ms.add_file("first", bl(30))

    def test_add_too_big_file(self):
        ms = media_split.MediaSplitter(bl(100))
        with self.assertRaises(ValueError):
            ms.add_file("too-big", bl(300))

    def test_fit_on_one(self):
        ms = media_split.MediaSplitter(bl(100), compose=self.compose)
        ms.add_file("first", bl(20))
        ms.add_file("second", bl(30))

        self.assertEqual(ms.split(), [{"files": ["first", "second"], "size": bl(50)}])

    def test_split_on_two_discs(self):
        ms = media_split.MediaSplitter(bl(100), compose=self.compose)
        ms.add_file("first", bl(25))
        ms.add_file("second", bl(40))
        ms.add_file("third", bl(80))

        self.assertEqual(
            ms.split(),
            [
                {"files": ["first", "second"], "size": bl(65)},
                {"files": ["third"], "size": bl(80)},
            ],
        )

    def test_split_with_sticky_file(self):
        ms = media_split.MediaSplitter(bl(100))
        ms.add_file("sticky", bl(15), sticky=True)
        ms.add_file("first", bl(25))
        ms.add_file("second", bl(40))
        ms.add_file("third", bl(80))

        self.assertEqual(
            ms.split(),
            [
                {"files": ["sticky", "first", "second"], "size": bl(80)},
                {"files": ["sticky", "third"], "size": bl(95)},
            ],
        )

    def test_split_unlimited_media(self):
        ms = media_split.MediaSplitter(None, compose=self.compose)
        ms.add_file("first", bl(25))
        ms.add_file("second", bl(40))
        ms.add_file("third", bl(80))

        self.assertEqual(
            ms.split(), [{"files": ["first", "second", "third"], "size": bl(145)}]
        )
