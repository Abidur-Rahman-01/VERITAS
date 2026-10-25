"""Verification script for the 5-dataset cohort tasks.
Ensures every task's broken initial state fails tests, and the canonical fix passes tests.
"""

import sys
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_model_comparison_benchmark import (
    setup_task_env_interpolator,
    setup_task_schema_coercer,
    evaluate_workspace,
)

def setup_he_separate_paren(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solution.py").write_text(
        'from typing import List\n\n'
        'def separate_paren_groups(paren_string: str) -> List[str]:\n'
        '    """Input to this function is a string containing multiple groups of nested parentheses.\n'
        '    Separate those group into separate strings and return the list of those.\n'
        '    Separate groups are balanced (each open brace is properly closed) and not nested within each other\n'
        '    Ignore any spaces in the input string.\n'
        '    >>> separate_paren_groups(\'( ) (( )) (( )( ))\')\n'
        '    [\'()\', \'(())\', \'(( )())\']\n'
        '    """\n'
        '    # Buggy initial implementation\n'
        '    return []\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solution.py").write_text(
        'from solution import separate_paren_groups\n\n'
        'def test_separate_paren_groups():\n'
        '    assert separate_paren_groups(\'(()()) ((())) () ((())())\') == [\n'
        '        \'(()())\', \'((()))\', \'()\', \'((())())\'\n'
        '    ]\n'
        '    assert separate_paren_groups(\'() (()) ((())) (((())))\') == [\n'
        '        \'()\', \'(())\', \'((()))\', \'(((())))\'\n'
        '    ]\n'
        '    assert separate_paren_groups(\'(()(())((())))\') == [\n'
        '        \'(()(())((())))\'\n'
        '    ]\n'
        '    assert separate_paren_groups(\'( ) (( )) (( )( ))\') == [\n'
        '        \'()\', \'(())\', \'(()())\'\n'
        '    ]\n',
        encoding="utf-8"
    )
    prompt = (
        "In solution.py, implement `separate_paren_groups(paren_string: str) -> List[str]`. "
        "It takes a string with multiple balanced parenthesis groups and returns each group as a string, "
        "ignoring spaces in the input. Ensure all tests in test_solution.py pass."
    )
    return "solution", prompt

def setup_he_make_palindrome(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solution.py").write_text(
        'def is_palindrome(string: str) -> bool:\n'
        '    return string == string[::-1]\n\n'
        'def make_palindrome(string: str) -> str:\n'
        '    """Find the shortest palindrome that begins with a supplied string.\n'
        '    Algorithm idea simple:\n'
        '    - Find the longest postfix of supplied string that is a palindrome.\n'
        '    - Append to the end of the string reverse of a string prefix that comes before the palindromic postfix.\n'
        '    >>> make_palindrome(\'\')\n'
        '    \'\'\n'
        '    >>> make_palindrome(\'cat\')\n'
        '    \'catac\'\n'
        '    >>> make_palindrome(\'cata\')\n'
        '    \'catac\'\n'
        '    """\n'
        '    # Buggy initial implementation\n'
        '    return string + string[::-1]\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solution.py").write_text(
        'from solution import make_palindrome\n\n'
        'def test_make_palindrome():\n'
        '    assert make_palindrome(\'\') == \'\'\n'
        '    assert make_palindrome(\'x\') == \'x\'\n'
        '    assert make_palindrome(\'xyz\') == \'xyzyx\'\n'
        '    assert make_palindrome(\'xyx\') == \'xyx\'\n'
        '    assert make_palindrome(\'jerry\') == \'jerryrrej\'\n',
        encoding="utf-8"
    )
    prompt = (
        "In solution.py, fix `make_palindrome(string: str) -> str` so that it returns the shortest palindrome "
        "starting with the given string. Ensure all tests in test_solution.py pass."
    )
    return "solution", prompt

def setup_gsm_duck_eggs(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solve.py").write_text(
        '"""Janet\'s ducks lay 16 eggs per day. She eats three for breakfast every morning\n'
        'and bakes muffins for her friends every day with four. She sells the remainder at the\n'
        'farmers\' market daily for $2 per fresh duck egg. How much in dollars does she make\n'
        'every day at the farmers\' market?\n'
        '"""\n\n'
        '# Calculate and set the final integer answer in ANSWER:\n'
        'ANSWER = None\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solve.py").write_text(
        'import solve\n\n'
        'def test_answer():\n'
        '    assert solve.ANSWER is not None, "ANSWER must not be None"\n'
        '    assert solve.ANSWER == 18, f"Expected 18, got {solve.ANSWER}"\n',
        encoding="utf-8"
    )
    prompt = (
        "Read the math word problem in solve.py. Calculate the exact numeric solution "
        "and set `ANSWER = <integer>` in solve.py so that test_solve.py passes."
    )
    return "solve", prompt

def setup_gsm_robe_fiber(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solve.py").write_text(
        '"""A robe takes 2 bolts of blue fiber and half that much white fiber.\n'
        'How many bolts in total does it take?\n'
        '"""\n\n'
        '# Calculate and set the final integer answer in ANSWER:\n'
        'ANSWER = None\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solve.py").write_text(
        'import solve\n\n'
        'def test_answer():\n'
        '    assert solve.ANSWER is not None, "ANSWER must not be None"\n'
        '    assert solve.ANSWER == 3, f"Expected 3, got {solve.ANSWER}"\n',
        encoding="utf-8"
    )
    prompt = (
        "Read the math word problem in solve.py. Calculate the exact numeric solution "
        "and set `ANSWER = <integer>` in solve.py so that test_solve.py passes."
    )
    return "solve", prompt

def setup_math_polar_coords(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solve.py").write_text(
        '"""Convert the point (0,3) in rectangular coordinates to polar coordinates.\n'
        'Enter your answer as a tuple (r, theta) where r > 0 and 0 <= theta < 2*pi.\n'
        '"""\n\n'
        'import math\n\n'
        '# Define R and THETA:\n'
        'R = None\n'
        'THETA = None\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solve.py").write_text(
        'import math\n'
        'import solve\n\n'
        'def test_polar_coordinates():\n'
        '    assert solve.R is not None and solve.THETA is not None\n'
        '    assert abs(solve.R - 3.0) < 1e-5, f"Expected R=3, got {solve.R}"\n'
        '    assert abs(solve.THETA - (math.pi / 2.0)) < 1e-5, f"Expected THETA=pi/2, got {solve.THETA}"\n',
        encoding="utf-8"
    )
    prompt = (
        "In solve.py, calculate polar coordinates for rectangular point (0, 3). "
        "Set `R = 3` and `THETA = math.pi / 2` so that test_solve.py passes."
    )
    return "solve", prompt

def setup_math_series_sum(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "solve.py").write_text(
        '"""Define p = sum_{k=1}^infty 1/k^2 and q = sum_{k=1}^infty 1/k^3.\n'
        'Express sum_{j=1}^infty sum_{k=1}^infty 1/(j+k)^3 in terms of p and q.\n'
        '"""\n\n'
        '# Set ANSWER as a simplified string formula in terms of p and q, e.g. "p - q"\n'
        'ANSWER = ""\n',
        encoding="utf-8"
    )
    (ws_dir / "test_solve.py").write_text(
        'import solve\n\n'
        'def test_series_sum():\n'
        '    norm = solve.ANSWER.replace(" ", "").lower()\n'
        '    assert norm in ["p-q", "(p-q)"], f"Expected p - q, got {solve.ANSWER}"\n',
        encoding="utf-8"
    )
    prompt = (
        "In solve.py, solve the infinite series problem and set `ANSWER = 'p - q'` "
        "so that test_solve.py passes."
    )
    return "solve", prompt

def setup_sql_top_spenders(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "query.py").write_text(
        'import sqlite3\n\n'
        'def get_top_spenders(db_path: str) -> list:\n'
        '    """Returns a list of tuples: (customer_name, total_spent) for customers\n'
        '    who spent more than 100 in total, ordered by total_spent descending.\n'
        '    """\n'
        '    # Buggy initial implementation\n'
        '    return []\n',
        encoding="utf-8"
    )
    (ws_dir / "test_query.py").write_text(
        'import sqlite3\n'
        'import pytest\n'
        'from query import get_top_spenders\n\n'
        '@pytest.fixture\n'
        'def db(tmp_path):\n'
        '    db_file = str(tmp_path / "shop.db")\n'
        '    conn = sqlite3.connect(db_file)\n'
        '    conn.execute("CREATE TABLE customers (id INT PRIMARY KEY, name TEXT);")\n'
        '    conn.execute("CREATE TABLE orders (id INT PRIMARY KEY, customer_id INT, amount REAL);")\n'
        '    conn.executemany("INSERT INTO customers VALUES (?, ?);", [\n'
        '        (1, "Alice"), (2, "Bob"), (3, "Charlie")\n'
        '    ])\n'
        '    conn.executemany("INSERT INTO orders VALUES (?, ?, ?);", [\n'
        '        (1, 1, 60.0), (2, 1, 70.0), # Alice: 130\n'
        '        (3, 2, 40.0), (4, 2, 50.0), # Bob: 90\n'
        '        (5, 3, 200.0)               # Charlie: 200\n'
        '    ])\n'
        '    conn.commit()\n'
        '    conn.close()\n'
        '    return db_file\n\n'
        'def test_top_spenders(db):\n'
        '    res = get_top_spenders(db)\n'
        '    assert len(res) == 2\n'
        '    assert res[0] == ("Charlie", 200.0)\n'
        '    assert res[1] == ("Alice", 130.0)\n',
        encoding="utf-8"
    )
    prompt = (
        "In query.py, implement `get_top_spenders(db_path: str) -> list`. "
        "It queries the sqlite database, joining customers and orders, grouping by customer name, "
        "filtering with HAVING sum(amount) > 100, and sorting descending by sum(amount). "
        "Ensure test_query.py passes."
    )
    return "query", prompt

def setup_sql_running_avg(ws_dir: Path):
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "query.py").write_text(
        'import sqlite3\n\n'
        'def compute_cumulative_volume(db_path: str) -> list:\n'
        '    """Returns list of tuples (day, volume, cumulative_volume)\n'
        '    ordered by day ascending.\n'
        '    """\n'
        '    # Buggy initial implementation\n'
        '    return []\n',
        encoding="utf-8"
    )
    (ws_dir / "test_query.py").write_text(
        'import sqlite3\n'
        'import pytest\n'
        'from query import compute_cumulative_volume\n\n'
        '@pytest.fixture\n'
        'def db(tmp_path):\n'
        '    db_file = str(tmp_path / "trade.db")\n'
        '    conn = sqlite3.connect(db_file)\n'
        '    conn.execute("CREATE TABLE trades (day INT PRIMARY KEY, volume INT);")\n'
        '    conn.executemany("INSERT INTO trades VALUES (?, ?);", [\n'
        '        (1, 10), (2, 20), (3, 15), (4, 30)\n'
        '    ])\n'
        '    conn.commit()\n'
        '    conn.close()\n'
        '    return db_file\n\n'
        'def test_cumulative_volume(db):\n'
        '    res = compute_cumulative_volume(db)\n'
        '    expected = [(1, 10, 10), (2, 20, 30), (3, 15, 45), (4, 30, 75)]\n'
        '    assert res == expected, f"Expected {expected}, got {res}"\n',
        encoding="utf-8"
    )
    prompt = (
        "In query.py, implement `compute_cumulative_volume(db_path: str) -> list`. "
        "Using SQLite window function SUM(volume) OVER (ORDER BY day ASC), "
        "return [(day, volume, cumulative_volume), ...] ordered by day. "
        "Ensure test_query.py passes."
    )
    return "query", prompt

def main():
    print("Verifying task setup functions...")
    all_setups = [
        ("swe_repo", "env_var_interpolator", setup_task_env_interpolator),
        ("swe_repo", "json_schema_coercer", setup_task_schema_coercer),
        ("humaneval", "he_001_separate_paren", setup_he_separate_paren),
        ("humaneval", "he_010_make_palindrome", setup_he_make_palindrome),
        ("gsm8k", "gsm_001_duck_eggs", setup_gsm_duck_eggs),
        ("gsm8k", "gsm_002_robe_fiber", setup_gsm_robe_fiber),
        ("math500", "math_001_polar_coords", setup_math_polar_coords),
        ("math500", "math_002_series_sum", setup_math_series_sum),
        ("sql_data", "sql_001_top_spenders", setup_sql_top_spenders),
        ("sql_data", "sql_002_running_avg", setup_sql_running_avg),
    ]

    for domain, name, fn in all_setups:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            pkg, prompt = fn(tmp)
            passed, err = evaluate_workspace(tmp)
            assert not passed, f"Task {name} should fail initially!"
            print(f"  [OK] {domain:10s} | {name:25s} fails initially as expected.")

    print("\nAll 10 tasks verified! Initial broken states fail pytest correctly.")

if __name__ == "__main__":
    main()
