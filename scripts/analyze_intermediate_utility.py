import json
import glob
import os
import pandas as pd
import numpy as np
from scipy import stats

def analyze_study(study_path):
    outcomes_csv = os.path.join(study_path, 'report', 'outcomes.csv')
    if not os.path.exists(outcomes_csv):
        return None
    df = pd.read_csv(outcomes_csv)
    
    trial_details = []
    for _, row in df.iterrows():
        trial_id = row['trial_id']
        attempt_dir = os.path.join(study_path, 'trials', trial_id, 'attempt-001')
        
        draft_session_file = os.path.join(attempt_dir, 'draft-session.json')
        final_session_file = os.path.join(attempt_dir, 'final-session.json')
        outcome_file = os.path.join(attempt_dir, 'outcome.json')
        
        draft_tools = {}
        draft_steps = 0
        final_answer_step = None
        
        if os.path.exists(draft_session_file):
            try:
                with open(draft_session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history = data.get('history', [])
                    draft_steps = len(history)
                    for i, step in enumerate(history):
                        tool = step.get('action', {}).get('tool', 'unknown')
                        draft_tools[tool] = draft_tools.get(tool, 0) + 1
                        if tool == 'final_answer' and final_answer_step is None:
                            final_answer_step = i + 1
            except Exception as e:
                pass
                
        revision_steps = 0
        revision_tools = {}
        if os.path.exists(final_session_file):
            try:
                with open(final_session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history = data.get('history', [])
                    revision_steps = len(history)
                    for step in history:
                        tool = step.get('action', {}).get('tool', 'unknown')
                        revision_tools[tool] = revision_tools.get(tool, 0) + 1
            except Exception as e:
                pass
                
        trial_details.append({
            'trial_id': trial_id,
            'task_id': row['task_id'],
            'repository_id': row['repository_id'],
            'actor_id': row['actor_id'],
            'arm': str(row['arm']).zfill(2),
            'awareness_D': 1 if str(row['arm']).zfill(2)[0] == '1' else 0,
            'feedback_A': 1 if str(row['arm']).zfill(2)[1] == '1' else 0,
            'deployed_tokens': row['deployed_tokens'],
            'deployed_calls': row['deployed_model_calls'],
            'online_seconds': row['online_seconds'],
            'draft_steps': draft_steps,
            'revision_steps': revision_steps,
            'total_steps': draft_steps + revision_steps,
            'surrender_step': final_answer_step,
            'grade_status': row['grade_status'],
            'python_calls': draft_tools.get('python', 0),
            'read_file_calls': draft_tools.get('read_file', 0),
            'edit_file_calls': draft_tools.get('edit_file', 0),
            'write_file_calls': draft_tools.get('write_file', 0),
            'final_answer_calls': draft_tools.get('final_answer', 0),
        })
        
    return pd.DataFrame(trial_details)

def run_comparative_analysis():
    studies = [
        'artifacts/study_llama_multitask',
        'artifacts/study_deepdive',
        'artifacts/trial_qwen14b_verbose',
        'artifacts/trial_actor-llama',
        'artifacts/trial_actor-qwen-general',
        'artifacts/trial_qwen14b'
    ]
    # Dynamically include any sharded studies
    for shard in sorted(glob.glob('artifacts/shard_*')):
        if shard not in studies:
            studies.append(shard)

    
    all_trials = []
    for s in studies:
        if os.path.exists(s):
            df = analyze_study(s)
            if df is not None and not df.empty:
                df['study'] = os.path.basename(s)
                all_trials.append(df)
                
    combined = pd.concat(all_trials, ignore_index=True)
    combined.to_csv('artifacts/intermediate_utility_trials.csv', index=False)
    
    print('=== OVERALL FACTORIAL SUMMARY (AWARENESS D=0 vs D=1) ===')
    grouped = combined.groupby('awareness_D').agg({
        'deployed_tokens': ['mean', 'std', 'median'],
        'deployed_calls': ['mean', 'std', 'median'],
        'online_seconds': ['mean', 'std', 'median'],
        'draft_steps': ['mean', 'median'],
        'surrender_step': ['mean', 'median', 'count'],
        'total_steps': ['mean', 'median']
    })
    print(grouped)
    
    # Statistical tests
    d0_tokens = combined[combined['awareness_D'] == 0]['deployed_tokens']
    d1_tokens = combined[combined['awareness_D'] == 1]['deployed_tokens']
    
    d0_calls = combined[combined['awareness_D'] == 0]['deployed_calls']
    d1_calls = combined[combined['awareness_D'] == 1]['deployed_calls']
    
    t_stat, p_val = stats.ttest_ind(d1_tokens, d0_tokens, equal_var=False)
    u_stat, u_pval = stats.mannwhitneyu(d1_tokens, d0_tokens, alternative='greater')
    
    print(f'\nTokens t-test: t={t_stat:.4f}, p={p_val:.4e}')
    print(f'Tokens Mann-Whitney U: U={u_stat:.1f}, p={u_pval:.4e}')
    
    t_stat_c, p_val_c = stats.ttest_ind(d1_calls, d0_calls, equal_var=False)
    u_stat_c, u_pval_c = stats.mannwhitneyu(d1_calls, d0_calls, alternative='greater')
    print(f'Calls t-test: t={t_stat_c:.4f}, p={p_val_c:.4e}')
    print(f'Calls Mann-Whitney U: U={u_stat_c:.1f}, p={u_pval_c:.4e}')
    
    # Focus on python-cmd2
    cmd2_df = combined[combined['repository_id'] == 'python-cmd2/cmd2']
    print('\n=== PYTHON-CMD2 SUB-COHORT (D=0 vs D=1) ===')
    cmd2_grouped = cmd2_df.groupby('awareness_D').agg({
        'deployed_tokens': ['mean', 'std'],
        'deployed_calls': ['mean', 'std'],
        'online_seconds': ['mean', 'std'],
        'total_steps': ['mean', 'min', 'max']
    })
    print(cmd2_grouped)
    
    c_d0_calls = cmd2_df[cmd2_df['awareness_D'] == 0]['deployed_calls']
    c_d1_calls = cmd2_df[cmd2_df['awareness_D'] == 1]['deployed_calls']
    if len(c_d0_calls) > 1 and len(c_d1_calls) > 1:
        c_t, c_p = stats.ttest_ind(c_d1_calls, c_d0_calls, equal_var=False)
        print(f'CMD2 Calls t-test: t={c_t:.4f}, p={c_p:.4e}')

if __name__ == '__main__':
    run_comparative_analysis()
