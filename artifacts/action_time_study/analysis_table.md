# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 20 | 10 | **50.0%** | [27.2%, 72.8%] | 0 | 7 | 7.11s | 0.0 |
| **arm1_random** | 20 | 14 | **70.0%** | [45.72%, 88.11%] | 45 | 30 | 8.47s | 0.9 |
| **arm2_selective** | 20 | 14 | **70.0%** | [45.72%, 88.11%] | 65 | 38 | 10.91s | 1.3 |

### Causal Contrasts

- **selective_vs_random:** +0.00%
- **selective_vs_unverified:** +20.00%