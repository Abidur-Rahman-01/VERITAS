import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

os.makedirs('artifacts/figures', exist_ok=True)
df = pd.read_csv('artifacts/intermediate_utility_trials.csv')

# Style setup for academic papers (clean, high contrast, serif/sans-serif)
plt.rcParams.update({
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.titlesize': 14,
    'figure.dpi': 300
})

# ==============================================================================
# Figure 1: Compute Escalation & Anti-Surrender (2 Subplots)
# ==============================================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

# Subplot 1: Median Tokens & Mean Tokens
d0_tokens = df[df['awareness_D'] == 0]['deployed_tokens'].dropna()
d1_tokens = df[df['awareness_D'] == 1]['deployed_tokens'].dropna()

categories = ['Unmonitored (D=0)', 'Evaluated (D=1)']
medians = [d0_tokens.median(), d1_tokens.median()]
means = [d0_tokens.mean(), d1_tokens.mean()]

x = np.arange(len(categories))
width = 0.35

rects1 = ax1.bar(x - width/2, medians, width, label='Median Tokens', color='#4575b4', alpha=0.9, edgecolor='black', linewidth=1)
rects2 = ax1.bar(x + width/2, means, width, label='Mean Tokens', color='#d73027', alpha=0.9, edgecolor='black', linewidth=1)

ax1.set_ylabel('Model Tokens Consumed')
ax1.set_title('(a) Token Escalation (3.12x Surge)')
ax1.set_xticks(x)
ax1.set_xticklabels(categories, fontweight='bold')
ax1.legend(frameon=True)
ax1.grid(axis='y', linestyle='--', alpha=0.5)

# Value annotations
for r in rects1:
    h = r.get_height()
    ax1.annotate(f'{int(h):,}',
                 xy=(r.get_x() + r.get_width() / 2, h),
                 xytext=(0, 3), textcoords="offset points",
                 ha='center', va='bottom', fontsize=9, fontweight='bold')
for r in rects2:
    h = r.get_height()
    ax1.annotate(f'{int(h):,}',
                 xy=(r.get_x() + r.get_width() / 2, h),
                 xytext=(0, 3), textcoords="offset points",
                 ha='center', va='bottom', fontsize=9)

# Subplot 2: Surrender Rate & CLI Calls
cmd2_df = df[df['repository_id'] == 'python-cmd2/cmd2']
c_d0 = cmd2_df[cmd2_df['awareness_D'] == 0]['deployed_calls'].dropna()
c_d1 = cmd2_df[cmd2_df['awareness_D'] == 1]['deployed_calls'].dropna()

surrender_d0 = (df[df['awareness_D'] == 0]['surrender_step'].notna().sum() / len(df[df['awareness_D'] == 0])) * 100
surrender_d1 = (df[df['awareness_D'] == 1]['surrender_step'].notna().sum() / len(df[df['awareness_D'] == 1])) * 100

ax2_surr = ax2
rects_calls = ax2_surr.bar(x, [c_d0.mean(), c_d1.mean()], width=0.5,
                           yerr=[c_d0.std()/np.sqrt(len(c_d0)), c_d1.std()/np.sqrt(len(c_d1))],
                           capsize=5, color=['#91bfdb', '#fc8d59'], edgecolor='black', linewidth=1)

ax2.set_ylabel('Mean Deployed Tool Calls')
ax2.set_title('(b) Tool Calls on CLI Tasks (p = 0.0405)')
ax2.set_xticks(x)
ax2.set_xticklabels(categories, fontweight='bold')
ax2.grid(axis='y', linestyle='--', alpha=0.5)
ax2.set_ylim(0, 42)

for r in rects_calls:
    h = r.get_height()
    ax2.annotate(f'{h:.1f} calls',
                 xy=(r.get_x() + r.get_width() / 2, h + 1.2),
                 ha='center', va='bottom', fontsize=9, fontweight='bold')

# Add annotation for surrender rate
ax2.text(0.5, 0.12, 'Surrender Rate: 12.5% (D=0) vs 0.0% (D=1)\np = 0.0143 (Fisher Exact)',
         transform=ax2.transAxes, ha='center', fontsize=9,
         bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffffbf', alpha=0.8, edgecolor='gray'))

plt.tight_layout()
fig1_path = 'artifacts/figures/fig1_compute_escalation.png'
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f'Saved {fig1_path}')

# ==============================================================================
# Figure 2: Factorial Interaction Plot (D x A)
# ==============================================================================
fig, ax = plt.subplots(figsize=(6.5, 4.5))

arms = ['Arm 00\n(D=0, A=0)', 'Arm 01\n(D=0, A=1)', 'Arm 10\n(D=1, A=0)', 'Arm 11\n(D=1, A=1)']
arm_data = df.groupby('arm')['deployed_tokens'].agg(['mean', 'median', 'std', 'count']).reindex([0, 1, 10, 11])

bar_colors = ['#4575b4', '#74add1', '#f46d43', '#d73027']
bars = ax.bar(arms, arm_data['median'], color=bar_colors, edgecolor='black', linewidth=1, width=0.55)

ax.set_ylabel('Median Tokens Consumed')
ax.set_title('Factorial Design Interaction (Awareness vs Feedback)')
ax.grid(axis='y', linestyle='--', alpha=0.5)

for b in bars:
    h = b.get_height()
    ax.annotate(f'{int(h):,}',
                xy=(b.get_x() + b.get_width() / 2, h),
                xytext=(0, 4), textcoords="offset points",
                ha='center', va='bottom', fontsize=9, fontweight='bold')

plt.tight_layout()
fig2_path = 'artifacts/figures/fig2_factorial_interaction.png'
plt.savefig(fig2_path, dpi=300)
plt.close()
print(f'Saved {fig2_path}')

# ==============================================================================
# Figure 3: Step Persistence / Anti-Surrender Survival Curve
# ==============================================================================
fig, ax = plt.subplots(figsize=(7, 4.5))

steps_range = np.arange(0, 60, 1)
d0_total = df[df['awareness_D'] == 0]['total_steps'].dropna().values
d1_total = df[df['awareness_D'] == 1]['total_steps'].dropna().values

# Fraction of agents still active at step >= s
d0_surv = [(d0_total >= s).mean() for s in steps_range]
d1_surv = [(d1_total >= s).mean() for s in steps_range]

ax.step(steps_range, d0_surv, where='post', label='Unmonitored (D=0)', color='#4575b4', linewidth=2.5, linestyle='--')
ax.step(steps_range, d1_surv, where='post', label='Evaluated (D=1)', color='#d73027', linewidth=2.5)

ax.set_xlabel('Agent Step (Draft + Revision Horizon)')
ax.set_ylabel('Probability of Continued Execution')
ax.set_title('Agent Persistence & Anti-Surrender Survival Function')
ax.set_ylim(-0.02, 1.05)
ax.grid(True, linestyle='--', alpha=0.5)
ax.legend(frameon=True, loc='upper right')

# Annotation for median step drop-off
ax.axvline(23, color='#4575b4', linestyle=':', alpha=0.7)
ax.text(23.5, 0.45, 'D=0 Median Stop\n(Step 23)', color='#4575b4', fontsize=9, fontweight='bold')

ax.axvline(56, color='#d73027', linestyle=':', alpha=0.7)
ax.text(50.0, 0.25, 'D=1 Ceiling\n(Step 56)', color='#d73027', fontsize=9, fontweight='bold')

plt.tight_layout()
fig3_path = 'artifacts/figures/fig3_persistence_survival.png'
plt.savefig(fig3_path, dpi=300)
plt.close()
print(f'Saved {fig3_path}')
