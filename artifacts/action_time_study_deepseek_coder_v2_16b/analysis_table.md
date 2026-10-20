# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 60 | 17 | **28.33%** | [17.45%, 41.44%] | 0 | 4 | 65.28s | 0.0 |
| **arm1_random** | 60 | 16 | **26.67%** | [16.07%, 39.66%] | 235 | 175 | 32.28s | 4.7 |
| **arm2_selective** | 60 | 17 | **28.33%** | [17.45%, 41.44%] | 107 | 112 | 43.6s | 2.14 |

### Causal Contrasts

- **selective_vs_random:** +1.66%
- **selective_vs_unverified:** +0.00%