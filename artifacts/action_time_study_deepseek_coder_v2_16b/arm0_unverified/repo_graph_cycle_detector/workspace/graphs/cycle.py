"""Directed graph cycle detection."""

def has_cycle(adj: dict[str, list[str]]) -> bool:
    visited = set()
    stack = set()

    def dfs(node):
        if node in stack:
            return True
        if node in visited:
            return False

        stack.add(node)
        for neighbor in adj[node]:
            if dfs(neighbor):
                return True
        stack.remove(node)
        visited.add(node)
        return False

    for node in adj:
        if node not in visited:
            if dfs(node):
                return True
    return False
