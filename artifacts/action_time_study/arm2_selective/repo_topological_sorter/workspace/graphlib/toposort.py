"""Topological Dependency Sorter."""

class CycleError(Exception):
    pass

def topological_sort(graph: dict) -> list:
    """Perform topological sort on DAG {node: [dependencies]}.
    Dependencies must appear before dependents in the returned order.
    """
    visited = set()
    order = []

    # BUG: Fails to distinguish recursion stack nodes from completed nodes,
    # falsely raising CycleError on diamond/convergent dependencies.
    def dfs(node):
        if node in visited:
            raise CycleError(f"Cycle detected involving {node}")
        visited.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        order.append(node)

    for n in sorted(graph.keys()):
        if n not in visited:
            dfs(n)
    return order
