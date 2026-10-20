# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 60 | 3 | **5.0%** | [1.04%, 13.92%] | 0 | 15 | 107.07s | 0.0 |
| **arm1_random** | 60 | 3 | **5.0%** | [1.04%, 13.92%] | 238 | 236 | 27.23s | 4.76 |
| **arm2_selective** | 60 | 3 | **5.0%** | [1.04%, 13.92%] | 65 | 92 | 86.18s | 1.3 |

### Causal Contrasts

- **selective_vs_random:** +0.00%
- **selective_vs_unverified:** +0.00%