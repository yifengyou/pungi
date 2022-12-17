# -*- coding: utf-8 -*-


class SimpleAcyclicOrientedGraph(object):
    """
    Stores a graph data structure and allows operation with it.
    Example data: {'P1': ['P2'], 'P3': ['P4', 'P5'], 'P2': 'P3'}
    Graph is constructed by adding oriented edges one by one. It can not contain cycles.
    Main result is spanning line, it determines ordering of the nodes.
    """

    def __init__(self):
        self._graph = {}
        self._all_nodes = set()

    def add_edge(self, start, end):
        """
        Add one edge from node 'start' to node 'end'.
        This operation must not create a cycle in the graph.
        """
        if start == end:
            raise ValueError(
                "Can not add this kind of edge into graph: %s-%s" % (start, end)
            )
        self._graph.setdefault(start, [])
        if end not in self._graph[start]:
            self._graph[start].append(end)
        self._all_nodes.add(start)
        self._all_nodes.add(end)
        # try to find opposite direction path (from end to start)
        # to detect newly created cycle
        path = SimpleAcyclicOrientedGraph.find_path(self._graph, end, start)
        if path:
            raise ValueError("There is a cycle in the graph: %s" % path)

    def get_active_nodes(self):
        """
        nodes connected to any edge
        """
        active_nodes = set()
        for start, ends in self._graph.items():
            active_nodes.add(start)
            active_nodes.update(ends)
        return active_nodes

    def is_final_endpoint(self, node):
        """
        edge(s) ends in this node; no other edge starts in this node
        """
        if node not in self._all_nodes:
            return ValueError("This node is not found in the graph: %s" % node)
        if node not in self.get_active_nodes():
            return False
        return False if node in self._graph else True

    def remove_final_endpoint(self, node):
        """"""
        remove_start_points = []
        for start, ends in self._graph.items():
            if node in ends:
                ends.remove(node)
                if not ends:
                    remove_start_points.append(start)
        for start in remove_start_points:
            del self._graph[start]

    @staticmethod
    def find_path(graph, start, end, path=[]):
        """
        find path among nodes 'start' and 'end' recursively
        """
        path = path + [start]
        if start == end:
            return path
        if start not in graph:
            return None
        for node in graph[start]:
            if node not in path:
                newpath = SimpleAcyclicOrientedGraph.find_path(graph, node, end, path)
                if newpath:
                    return newpath
        return None

    def prune_graph(self):
        """
        Construct spanning_line by pruning the graph.
        Looking for endpoints and remove them one by one until graph is empty.
        """
        spanning_line = []
        while self._graph:
            for node in sorted(self._all_nodes):
                if self.is_final_endpoint(node):
                    self.remove_final_endpoint(node)
                    spanning_line.insert(0, node)
                    # orphan node = no edge is connected with this node
                    orphans = self._all_nodes - self.get_active_nodes()
                    if orphans:
                        # restart iteration not to set size self._all_nodes
                        # during iteration
                        break
            for orphan in orphans:
                if orphan not in spanning_line:
                    spanning_line.insert(0, orphan)
                self._all_nodes.remove(orphan)
        return spanning_line
