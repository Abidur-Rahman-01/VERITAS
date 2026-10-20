"""Levenshtein distance."""

def levenshtein(s1: str, s2: str) -> int:
    # BUG: Returns difference in string lengths instead of edit distance
    # Initialize matrix
    dp = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]

    # Fill matrix
    for i in range(len(s1) + 1):
        dp[i][0] = i
    for j in range(len(s2) + 1):
        dp[0][j] = j

    for i in range(1, len(s1) + 1):
        for j in range(1, len(s2) + 1):
            if s1[i - 1] == s2[j - 1]:
                cost = 0
            else:
                cost = 1
            dp[i][j] = min(dp[i - 1][j] + 1,    # Deletion
                           dp[i][j - 1] + 1,    # Insertion
                           dp[i - 1][j - 1] + cost)  # Substitution

    return dp[len(s1)][len(s2)]
