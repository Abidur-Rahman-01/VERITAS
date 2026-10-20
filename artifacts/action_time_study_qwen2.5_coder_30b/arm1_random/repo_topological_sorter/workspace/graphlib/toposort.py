"""Topological Dependency Sorter."""

class CycleError(Exception):
    pass

def topological_sort(graph: dict) -> list:
    """Perform topological sort on DAG {node: [dependencies]}.
    Dependencies must appear before dependents in the returned order.
    """
    visited = set()
    visiting = set()
    order = []

    def dfs(node):
        if node in visiting:
            raise CycleError(f"Cycle detected involving {node}")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        visiting.remove(node)
        visited.add(node)
        order.append(node)

    for n in sorted(graph.keys()):
        if n not in visited:
            dfs(n)
    return order
