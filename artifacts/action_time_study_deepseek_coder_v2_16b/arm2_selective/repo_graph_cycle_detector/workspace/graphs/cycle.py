"""Directed graph cycle detection."""

def has_cycle(adj: dict[str, list[str]]) -> bool:
    visited = set()
    rec_stack = set()

    def dfs(node):
        if node in rec_stack:
            return True
        if node in visited:
            return False

        visited.add(node)
        rec_stack.add(node)

        for neighbor in adj[node]:
            if dfs(neighbor):
                return True

        rec_stack.remove(node)
        return False

    for node in adj:
        if node not in visited:
            if dfs(node):
                return True
    return False
