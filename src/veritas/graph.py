"""Small, deterministic DAG engine: backward reachability + Kahn scheduling.

No graph/model dependency is needed. Edges are prerequisite -> consumer. Scheduling
is cost-first among ready nodes; this is a heuristic, not an optimality theorem.
"""

import heapq
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    name: str
    dependencies: tuple[str, ...] = ()
    cost: int = 0


class DAG:
    def __init__(self, nodes):
        nodes = list(nodes)
        self.nodes = {n.name: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("Duplicate graph node")
        for node in nodes:
            if set(node.dependencies) - self.nodes.keys():
                raise ValueError(f"Missing dependency for {node.name}")
        self.order(self.nodes)  # Validate the WHOLE graph, including unrequested branches.

    def slice(self, targets):
        pending, needed = list(targets), set()
        while pending:
            name = pending.pop()
            if name not in self.nodes:
                raise ValueError(f"Unknown target: {name}")
            if name not in needed:
                needed.add(name)
                pending.extend(self.nodes[name].dependencies)
        return needed

    def order(self, targets):
        needed = self.slice(targets)
        degree = {name: len(self.nodes[name].dependencies) for name in needed}
        children = {name: [] for name in needed}
        for name in needed:
            for parent in self.nodes[name].dependencies:
                children[parent].append(name)
        ready = [(self.nodes[n].cost, n) for n, d in degree.items() if d == 0]
        heapq.heapify(ready)
        ordered = []
        while ready:
            _, name = heapq.heappop(ready)
            ordered.append(name)
            for child in children[name]:
                degree[child] -= 1
                if degree[child] == 0:
                    heapq.heappush(ready, (self.nodes[child].cost, child))
        if len(ordered) != len(needed):
            raise ValueError("Verifier dependencies contain a cycle")
        return ordered

    def describe(self, targets):
        targets = list(targets)
        return {
            "algorithm": "backward_slice_then_cost_ordered_kahn",
            "targets": targets,
            "nodes": list(self.nodes),
            "edges": [[p, n.name] for n in self.nodes.values() for p in n.dependencies],
            "schedule": self.order(targets),
        }
