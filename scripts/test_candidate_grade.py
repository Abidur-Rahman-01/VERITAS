import json, shutil
from pathlib import Path
from veritas.awareness_grading import grade_patch
from veritas.schema import StrictModel

with open('artifacts/swe-rebench-images-selected.tasks.jsonl') as f:
    for line in f:
        t = json.loads(line)
        if 'cmd2' in t.get('instance_id', ''):
            cmd2_task = t
            break

class MockTask:
    def __init__(self, private):
        self.private = private

task = MockTask(cmd2_task)

candidate_patch = '''diff --git a/cmd2/cmd2.py b/cmd2/cmd2.py
index adadbdf8..7c529acc 100644
--- a/cmd2/cmd2.py
+++ b/cmd2/cmd2.py
@@ -3610,6 +3610,14 @@ class Cmd(cmd.Cmd):
             self.perror(msg.format(hist_file))
             return
 
+        # Create the directory for the history file if it doesn't already exist
+        hist_file_dir = os.path.dirname(hist_file)
+        try:
+            os.makedirs(hist_file_dir, exist_ok=True)
+        except OSError as ex:
+            msg = "Error creating persistent history file directory '{}': {}".format(hist_file_dir, ex)
+            self.pexcept(msg)
+            return
+
         # first we try and unpickle the history file
         history = History()
'''

with open('artifacts/shard_python_cmd2_cmd2_744/grader.json') as f:
    gj = json.load(f)

class MockSpec(StrictModel):
    identity: str = 'd307ff9f2168a0448843c0d5881d2cd498d9f73f'
    package_sha256: str = gj['sha256']
    platform: str = None
    python: str = '/home/user/.venvs/veritas-rebench/bin/python'
    namespace: str = ''
    timeout_seconds: float = 300

tmp = Path('/mnt/d/2110001/VERITAS/artifacts/debug_candidate_eval')
shutil.rmtree(tmp, ignore_errors=True)

print('Running SWE-bench grading on agent-synthesized patch...')
res = grade_patch(task, candidate_patch, MockSpec(), tmp, 'candidate-eval-run')
print('=== GRADING RESULT ===')
print('status:', res['status'])
print('resolved:', res['resolved'])
