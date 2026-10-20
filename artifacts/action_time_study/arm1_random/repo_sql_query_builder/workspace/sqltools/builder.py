"""SQL Query Builder."""

def build_select_query(table: str, columns: list = None, filters: dict = None, order_by: str = None, limit: int = None, offset: int = None):
    """Build parameterized SELECT query string and parameter tuple."""
    cols = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols} FROM {table}"
    params = []

    if filters:
        # BUG: String concatenates filter values into SQL instead of using '?' placeholders
        where_clauses = []
        for k, v in filters.items():
            where_clauses.append(f"{k} = ?")
            params.append(v)
        sql += " WHERE " + " AND ".join(where_clauses)

    if order_by:
        sql += f" ORDER BY {order_by}"

    if offset is not None:
        # BUG: Emits OFFSET before LIMIT (invalid syntax in SQLite)
        sql += f" LIMIT {limit} OFFSET {offset}"

    if limit is not None:
        sql += f" LIMIT {limit}"

    return sql.strip(), tuple(params)
