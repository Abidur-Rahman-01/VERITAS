import sqlite3
from sqltools.builder import build_select_query

def test_parameterized_where():
    query, params = build_select_query("users", columns=["id", "name"], filters={"status": "active", "role": "admin"})
    assert "WHERE status = ? AND role = ?" in query
    assert params == ("active", "admin")

def test_limit_and_offset_order():
    query, params = build_select_query("products", limit=10, offset=20)
    assert query.endswith("LIMIT 10 OFFSET 20")

def test_sqlite_execution():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE users (id INT, name TEXT, status TEXT, role TEXT)")
    con.execute("INSERT INTO users VALUES (1, 'Alice', 'active', 'admin')")
    con.execute("INSERT INTO users VALUES (2, 'Bob', 'inactive', 'user')")
    query, params = build_select_query("users", filters={"status": "active", "role": "admin"})
    rows = con.execute(query, params).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Alice"
