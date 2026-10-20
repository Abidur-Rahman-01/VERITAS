# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 60 | 55 | **91.67%** | [81.61%, 97.24%] | 0 | 0 | 13.26s | 0.0 |
| **arm1_random** | 60 | 57 | **95.0%** | [86.08%, 98.96%] | 125 | 8 | 33.43s | 2.5 |
| **arm2_selective** | 60 | 55 | **91.67%** | [81.61%, 97.24%] | 50 | 16 | 24.31s | 1.0 |

### Causal Contrasts

- **selective_vs_random:** -3.33%
- **selective_vs_unverified:** +0.00%