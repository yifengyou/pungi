# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from pungi.graph import SimpleAcyclicOrientedGraph


class SimpleAcyclicOrientedGraphTestCase(unittest.TestCase):
    def setUp(self):
        self.g = SimpleAcyclicOrientedGraph()

    def test_simple_graph(self):
        graph_data = (
            ("Client", "Base"),
            ("Server", "Base"),
            ("Workstation", "Base"),
        )

        for start, end in graph_data:
            self.g.add_edge(start, end)
        spanning_line = self.g.prune_graph()

        self.assertEqual(4, len(spanning_line))
        # 'Base' as a lookaside should be at the end of the spanning line,
        # order of others is not crucial
        self.assertEqual("Base", spanning_line[-1])

    def test_complex_graph(self):
        graph_data = (
            ("1", "3"),  # 1 --> 3 --> 4 --> 5 ...
            ("3", "4"),
            ("4", "5"),
            ("4", "6"),
            ("2", "4"),
            ("7", "6"),
            ("6", "5"),
        )

        for start, end in graph_data:
            self.g.add_edge(start, end)
        spanning_line = self.g.prune_graph()

        # spanning line have to match completely to given graph
        self.assertEqual(["1", "3", "2", "4", "7", "6", "5"], spanning_line)

    def test_cyclic_graph(self):
        graph_data = (
            ("1", "2"),
            ("2", "3"),
            ("3", "1"),
        )

        with self.assertRaises(ValueError):
            for start, end in graph_data:
                self.g.add_edge(start, end)

    def test_two_separate_graph_lines(self):
        graph_data = (
            ("1", "3"),  # 1st graph
            ("3", "2"),  # 1st graph
            ("6", "5"),  # 2nd graph
        )

        for start, end in graph_data:
            self.g.add_edge(start, end)
        spanning_line = self.g.prune_graph()
        spanning_line_str = "".join(spanning_line)

        self.assertEqual(5, len(spanning_line))
        # Particular parts should match. Order of these parts is not crucial.
        self.assertTrue(
            "132" in spanning_line_str and "65" in spanning_line_str,
            "Spanning line '%s' does not match to graphs" % spanning_line_str,
        )

    def alternative_route_in_graph(self):
        graph_data = (
            ("1", "3"),
            ("3", "2"),
            ("1", "2"),
        )

        for start, end in graph_data:
            self.g.add_edge(start, end)
        spanning_line = self.g.prune_graph()

        # spanning line have to match completely to given graph
        self.assertEqual(["1", "3", "2"], spanning_line)
