import sys
import tempfile
import subprocess
from pathlib import Path
from datasets import load_dataset

ds = load_dataset('openai/openai_humaneval', split='test')
row = ds[0]

with tempfile.TemporaryDirectory() as tmp_str:
    ws = Path(tmp_str)
    # Stub
    (ws / 'solution.py').write_text(row['prompt'] + '    pass\n', encoding='utf-8')
    # Test
    test_code = (
        'import solution\n'
        f'{row["test"]}\n'
        'def test_solution():\n'
        f'    candidate = getattr(solution, "{row["entry_point"]}")\n'
        '    check(candidate)\n'
    )
    (ws / 'test_solution.py').write_text(test_code, encoding='utf-8')

    # Initially fail
    res = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=str(ws), capture_output=True, text=True)
    print('Initial stub test passed (should be False):', res.returncode == 0)
    assert res.returncode != 0

    # Put canonical solution
    (ws / 'solution.py').write_text(row['prompt'] + row['canonical_solution'], encoding='utf-8')
    res = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=str(ws), capture_output=True, text=True)
    print('Canonical solution test passed (should be True):', res.returncode == 0)
    assert res.returncode == 0

print('HumanEval harness verified successfully!')
