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

    # BUG: Fails to distinguish recursion stack nodes from completed nodes,
    # falsely raising CycleError on diamond/convergent dependencies.
    def dfs(node):
        if node in visited and node not in visiting:
            raise CycleError(f"Cycle detected involving {node}")
        visiting.add(node)
        for dep in graph.get(node, []):
            if dep not in visiting:
                visiting.add(dep)
                try:
                    dfs(dep)
                finally:
                    visiting.remove(dep)
                dfs(dep)
        visiting.remove(node)
        order.append(node)

    for n in sorted(graph.keys()):
        if n not in visited:
            dfs(n)
    return order
