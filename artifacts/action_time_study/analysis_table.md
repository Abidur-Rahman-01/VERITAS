# Action-Time Runtime Verification: Statistical Analysis Report

| Experimental Arm | Trials | Resolved | Success Rate (%) | 95% CI | Verified Actions | Blocked Actions | Mean Seconds | Verifier Spent |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm0_unverified** | 2 | 2 | **100.0%** | [15.81%, 100.0%] | 0 | 0 | 7.29s | 0.0 |
| **arm1_random** | 2 | 2 | **100.0%** | [15.81%, 100.0%] | 2 | 0 | 6.4s | 0.04 |
| **arm2_selective** | 2 | 2 | **100.0%** | [15.81%, 100.0%] | 3 | 0 | 5.64s | 0.06 |

### Causal Contrasts

- **selective_vs_random:** +0.00%
- **selective_vs_unverified:** +0.00%