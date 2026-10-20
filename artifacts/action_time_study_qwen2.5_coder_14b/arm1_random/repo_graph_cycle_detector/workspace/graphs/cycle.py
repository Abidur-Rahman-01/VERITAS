"""Directed graph cycle detection."""

def has_cycle(adj: dict[str, list[str]]) -> bool:
    # BUG: Returns False unconditionally
    visited = set()
    rec_stack = set()

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in adj[node]:
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    for node in adj:
        if node not in visited:
            if dfs(node):
                return True

    return False
