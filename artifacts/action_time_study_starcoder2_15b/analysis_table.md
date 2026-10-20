# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 60 | 0 | **0.0%** | [0.0%, 5.96%] | 0 | 60 | 1.82s | 0.0 |
| **arm1_random** | 60 | 0 | **0.0%** | [0.0%, 5.96%] | 0 | 240 | 17.35s | 0.0 |
| **arm2_selective** | 60 | 0 | **0.0%** | [0.0%, 5.96%] | 0 | 240 | 18.84s | 0.0 |

### Causal Contrasts

- **selective_vs_random:** +0.00%
- **selective_vs_unverified:** +0.00%