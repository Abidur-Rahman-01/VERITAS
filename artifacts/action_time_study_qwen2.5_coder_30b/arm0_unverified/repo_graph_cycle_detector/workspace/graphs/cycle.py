"""Directed graph cycle detection."""

def has_cycle(adj: dict[str, list[str]]) -> bool:
    visited = set()
    visiting = set()
    
    def dfs(node):
        if node in visiting:
            return True  # Cycle detected
        if node in visited:
            return False  # Already processed
        
        visiting.add(node)
        for neighbor in adj.get(node, []):
            if dfs(neighbor):
                return True
        
        visiting.remove(node)
        visited.add(node)
        return False
    
    for node in adj:
        if node not in visited:
            if dfs(node):
                return True
    return False
