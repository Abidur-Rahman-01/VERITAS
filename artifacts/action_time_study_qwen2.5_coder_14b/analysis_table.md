# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 60 | 48 | **80.0%** | [67.67%, 89.22%] | 0 | 1 | 19.71s | 0.0 |
| **arm1_random** | 60 | 48 | **80.0%** | [67.67%, 89.22%] | 136 | 47 | 32.47s | 2.72 |
| **arm2_selective** | 60 | 48 | **80.0%** | [67.67%, 89.22%] | 79 | 46 | 22.49s | 1.58 |

### Causal Contrasts

- **selective_vs_random:** +0.00%
- **selective_vs_unverified:** +0.00%