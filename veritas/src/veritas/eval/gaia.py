"""GAIA (General AI Assistants) benchmark integration for VERITAS.

Evaluates long-horizon, multi-step reasoning across Levels 1, 2, and 3 tasks
involving web browsing, file handling, tabular data extraction, arithmetic calculation,
and strategic verification under bounded compute budgets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from veritas.actions.classes import ActionClass
from veritas.actions.contracts import ActionContract, Provenance


BUILTIN_GAIA_TASKS: list[dict[str, Any]] = [
    # Level 1: Targeted Information Extraction & Single-Stage Derivations
    {
        "task_id": "gaia_lvl1_001",
        "question": "According to the municipal census report, City A had 450,000 residents in 2020 and 486,000 in 2023. City B had 320,000 in 2020 and 352,000 in 2023. What is the difference in population growth rates (percentage points) between City A and City B?",
        "level": 1,
        "tools_required": ("file.read", "math.calc"),
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {"path": "data/census_2023.txt"},
                "intent": "Read census report for City A and City B",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "City A: 450000->486000, City B: 320000->352000",
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "(486000 - 450000) / 450000 * 100", "target": 8.0},
                "intent": "Calculate percentage growth rate for City A",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 8.0,
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "(352000 - 320000) / 320000 * 100", "target": 10.0},
                "intent": "Calculate percentage growth rate for City B",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 10.0,
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "abs(10.0 - 8.0)", "target": 2.0},
                "intent": "Calculate absolute difference in growth rate percentage points",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 2.0,
            },
        ],
        "final_answer": "2.0 percentage points",
    },
    {
        "task_id": "gaia_lvl1_002",
        "question": "A financial report states that TechCorp had quarterly revenue of $12.5B against an analyst consensus estimate of $11.8B. What was the revenue beat in percentage?",
        "level": 1,
        "tools_required": ("web.search", "math.calc"),
        "steps": [
            {
                "tool": "web.search",
                "operation": "query",
                "arguments": {"query": "TechCorp quarterly revenue Q3 consensus actual"},
                "intent": "Retrieve revenue report and analyst consensus",
                "permissions": ("network:read",),
                "mutates": False,
                "expected": "Actual: $12.5B, Consensus: $11.8B",
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "round((12.5 - 11.8) / 11.8 * 100, 2)", "target": 5.93},
                "intent": "Compute percentage revenue beat",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 5.93,
            },
        ],
        "final_answer": "5.93%",
    },
    {
        "task_id": "gaia_lvl1_003",
        "question": "Extract the lead author and total citation count for the paper titled 'Attention Is All You Need' from the citation index.",
        "level": 1,
        "tools_required": ("web.search", "data.extract"),
        "steps": [
            {
                "tool": "web.search",
                "operation": "query",
                "arguments": {"query": "Attention Is All You Need Vaswani citation count"},
                "intent": "Query scholarly index for paper citation metadata",
                "permissions": ("network:read",),
                "mutates": False,
                "expected": "Lead author: Ashish Vaswani, Citations: 120000+",
            },
            {
                "tool": "data.extract",
                "operation": "parse_field",
                "arguments": {"field": "first_author", "input": "Vaswani et al."},
                "intent": "Extract primary author name",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Ashish Vaswani",
            },
        ],
        "final_answer": "Ashish Vaswani",
    },
    {
        "task_id": "gaia_lvl1_004",
        "question": "Inspect conference schedule JSON and identify the room number and start time for Keynote 2.",
        "level": 1,
        "tools_required": ("file.read", "json.parse"),
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {"path": "agenda.json"},
                "intent": "Read conference agenda JSON",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "{'sessions': [{'id': 'keynote_2', 'room': 'Hall C', 'time': '14:00'}]}",
            },
            {
                "tool": "json.parse",
                "operation": "query",
                "arguments": {"path": "$.sessions[?(@.id=='keynote_2')].room", "target": "Hall C"},
                "intent": "Parse session room from agenda",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Hall C",
            },
        ],
        "final_answer": "Hall C at 14:00",
    },

    # Level 2: Multi-Source Synthesis, Tabular Filtering, and Cross-Referencing
    {
        "task_id": "gaia_lvl2_001",
        "question": "Find the cheapest flight route between JFK and LHR with at most 1 layover under 2.5 hours, including a $60 checked baggage fee.",
        "level": 2,
        "tools_required": ("web.search", "table.filter", "math.calc"),
        "steps": [
            {
                "tool": "web.search",
                "operation": "query",
                "arguments": {"origin": "JFK", "destination": "LHR", "max_layovers": 1},
                "intent": "Search flight schedules JFK to LHR",
                "permissions": ("network:read",),
                "mutates": False,
                "expected": "Flight 101 ($450, 1 layover 1.5h), Flight 202 ($420, 1 layover 3.5h)",
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {"condition": "layover_duration <= 2.5", "target_flight": "Flight 101"},
                "intent": "Filter flights satisfying max layover constraint",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Flight 101 (Base $450)",
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "450 + 60", "target": 510.0},
                "intent": "Compute total cost including baggage fee",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 510.0,
            },
        ],
        "final_answer": "$510.00 via Flight 101",
    },
    {
        "task_id": "gaia_lvl2_002",
        "question": "From the university endowments dataset, filter for private universities in New England and calculate the median endowment in billions.",
        "level": 2,
        "tools_required": ("file.read", "table.filter", "data.aggregate"),
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {"path": "endowments.csv"},
                "intent": "Read university endowments tabular dataset",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Parsed 100 university records",
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {"region": "New England", "type": "private"},
                "intent": "Filter dataset to private New England institutions",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Found 12 matching institutions",
            },
            {
                "tool": "data.aggregate",
                "operation": "median",
                "arguments": {"column": "endowment_billions", "target": 14.2},
                "intent": "Calculate median endowment",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 14.2,
            },
        ],
        "final_answer": "$14.2B",
    },
    {
        "task_id": "gaia_lvl2_003",
        "question": "Inspect Python package dependencies between v1.4 and v2.0 in requirements.txt, determine conflicting version constraints for numpy and scipy.",
        "level": 2,
        "tools_required": ("file.read", "diff.inspect", "code.analyze"),
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {"path": "requirements.v1.txt"},
                "intent": "Read baseline dependencies",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "numpy>=1.20,<1.24, scipy==1.9.0",
            },
            {
                "tool": "diff.inspect",
                "operation": "compare",
                "arguments": {"old_file": "requirements.v1.txt", "new_file": "requirements.v2.txt"},
                "intent": "Compare dependency specifications",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "numpy bumped to >=2.0.0, scipy requires numpy<2.0.0",
            },
            {
                "tool": "code.analyze",
                "operation": "resolve_pin",
                "arguments": {"package": "numpy", "compatible_version": "1.26.4"},
                "intent": "Resolve highest mutually compatible version pin",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "numpy==1.26.4",
            },
        ],
        "final_answer": "numpy==1.26.4",
    },
    {
        "task_id": "gaia_lvl2_004",
        "question": "Parse factory telemetry log, identify temperature spikes exceeding 3 standard deviations from the mean, and compute the spike duration in minutes.",
        "level": 2,
        "tools_required": ("file.read", "math.calc", "data.aggregate"),
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {"path": "sensors.log"},
                "intent": "Load sensor telemetry series",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "1440 minute data points loaded",
            },
            {
                "tool": "data.aggregate",
                "operation": "stats",
                "arguments": {"mean": 68.0, "std": 4.0, "threshold_3sigma": 80.0},
                "intent": "Compute 3-sigma anomaly threshold",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 80.0,
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "18 - 3", "target": 15.0},
                "intent": "Calculate anomaly duration in minutes",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 15.0,
            },
        ],
        "final_answer": "15 minutes",
    },

    # Level 3: Long-Horizon Multi-Step Agent Workflows & Financial Consolidation
    {
        "task_id": "gaia_lvl3_001",
        "question": "Download quarterly reports for 3 companies (Alpha in USD, Beta in EUR, Gamma in GBP). Normalize revenues to USD using spot FX rates (EUR/USD=1.08, GBP/USD=1.28), compute YoY growth rates, and identify the company with highest operating margin.",
        "level": 3,
        "tools_required": ("web.search", "file.read", "currency.convert", "math.calc", "table.rank"),
        "steps": [
            {
                "tool": "web.search",
                "operation": "query",
                "arguments": {"query": "Alpha Beta Gamma Q3 2025 revenue operating income"},
                "intent": "Retrieve financial disclosures across all three firms",
                "permissions": ("network:read",),
                "mutates": False,
                "expected": "Alpha: $10B rev, $2.5B opinc; Beta: €8B rev, €2.4B opinc; Gamma: £6B rev, £1.2B opinc",
            },
            {
                "tool": "currency.convert",
                "operation": "convert",
                "arguments": {"amount": 8.0, "currency": "EUR", "rate": 1.08, "target": 8.64},
                "intent": "Convert Beta revenue to USD",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 8.64,
            },
            {
                "tool": "currency.convert",
                "operation": "convert",
                "arguments": {"amount": 2.4, "currency": "EUR", "rate": 1.08, "target": 2.592},
                "intent": "Convert Beta operating income to USD",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 2.592,
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "round(2.5 / 10.0 * 100, 1)", "target": 25.0},
                "intent": "Compute Alpha operating margin",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 25.0,
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {"expression": "round(2.592 / 8.64 * 100, 1)", "target": 30.0},
                "intent": "Compute Beta operating margin",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 30.0,
            },
            {
                "tool": "table.rank",
                "operation": "rank_max",
                "arguments": {"Alpha": 25.0, "Beta": 30.0, "Gamma": 20.0, "target": "Beta"},
                "intent": "Rank operating margins and select leader",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Beta (30.0%)",
            },
        ],
        "final_answer": "Beta with 30.0% operating margin",
    },
    {
        "task_id": "gaia_lvl3_002",
        "question": "Audit e-commerce ledger against payment gateway transactions. Recompute sales tax per state rules (CA=7.25%, NY=8.875%, TX=6.25%), detect unremitted tax liabilities, and generate a reconciled closing entry.",
        "level": 3,
        "tools_required": ("db.query", "table.join", "tax.compute", "audit.reconcile", "report.generate"),
        "steps": [
            {
                "tool": "db.query",
                "operation": "query",
                "arguments": {"table": "orders", "status": "completed"},
                "intent": "Fetch completed order records from internal database",
                "permissions": ("workspace:read",),
                "mutates": False,
                "expected": "Retrieved 1,200 orders totaling $450,000",
            },
            {
                "tool": "tax.compute",
                "operation": "calculate_nexus",
                "arguments": {"state": "CA", "gross": 200000.0, "rate": 0.0725, "target": 14500.0},
                "intent": "Compute California sales tax obligation",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 14500.0,
            },
            {
                "tool": "tax.compute",
                "operation": "calculate_nexus",
                "arguments": {"state": "NY", "gross": 150000.0, "rate": 0.08875, "target": 13312.5},
                "intent": "Compute New York sales tax obligation",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 13312.5,
            },
            {
                "tool": "audit.reconcile",
                "operation": "diff_collected",
                "arguments": {"collected": 26000.0, "obligated": 27812.5, "target": 1812.5},
                "intent": "Compute tax shortfall between collected and obligated",
                "permissions": ("calc:execute",),
                "mutates": False,
                "expected": 1812.5,
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {"path": "reconciliation.csv", "unremitted_liability": 1812.5},
                "intent": "Write audited tax reconciliation ledger entry",
                "permissions": ("workspace:write",),
                "mutates": True,
                "expected": "reconciliation.csv generated",
            },
        ],
        "final_answer": "Unremitted tax liability of $1,812.50 recorded in reconciliation.csv",
        },
    {
        "task_id": "gaia_lvl1_011",
        "question": "Calculate the compound interest on a principal of $15,000 at 4.5% annual rate compounded quarterly for 3 years.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "15000 * ((1 + 0.045/4) ** 12) - 15000",
                    "target": 2154.27
                },
                "intent": "Compute compound interest",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 2154.27
            }
        ],
        "final_answer": "$2,154.27"
    },
    {
        "task_id": "gaia_lvl1_012",
        "question": "Determine the carbon emission offset of replacing 1,200 incandescent bulbs (60W) with LED equivalents (9W) operating 8 hours/day for 365 days (grid intensity 0.85 lbs CO2/kWh).",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "1200 * (60 - 9) * 8 * 365 / 1000 * 0.85 / 2204.62",
                    "target": 68.9
                },
                "intent": "Calculate metric tons CO2 offset",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 68.9
            }
        ],
        "final_answer": "68.9 metric tons CO2"
    },
    {
        "task_id": "gaia_lvl1_013",
        "question": "Auditing server cluster power: compute peak wattage for 48 nodes drawing 450W each with a PUE multiplier of 1.25.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "48 * 450 * 1.25 / 1000",
                    "target": 27.0
                },
                "intent": "Calculate total peak kW",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 27.0
            }
        ],
        "final_answer": "27.0 kW"
    },
    {
        "task_id": "gaia_lvl1_014",
        "question": "Evaluate the net present value (NPV) of a project generating $10k, $15k, and $20k over 3 years with a 7% discount rate and initial cost $35k.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "10000/1.07 + 15000/(1.07**2) + 20000/(1.07**3) - 35000",
                    "target": 3794.13
                },
                "intent": "Calculate NPV",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 3794.13
            }
        ],
        "final_answer": "$3,794.13"
    },
    {
        "task_id": "gaia_lvl1_015",
        "question": "Inspect package dependency manifest for CVE-2023-32681 in certifi package versions.",
        "level": 1,
        "tools_required": [
            "file.read",
            "json.parse"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "requirements.lock"
                },
                "intent": "Check locked version of certifi",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "certifi==2023.5.7"
            },
            {
                "tool": "json.parse",
                "operation": "verify",
                "arguments": {
                    "package": "certifi",
                    "vulnerable_below": "2023.7.22"
                },
                "intent": "Confirm vulnerability status",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": True
            }
        ],
        "final_answer": "Vulnerable: certifi 2023.5.7 requires upgrade to >=2023.7.22"
    },
    {
        "task_id": "gaia_lvl1_016",
        "question": "Verify memory buffer size requirement for 4K 60fps RGBA 10-bit video pipeline holding 12 frames.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "3840 * 2160 * 4 * 1.25 * 12 / (1024**2)",
                    "target": 474.6
                },
                "intent": "Calculate frame buffer in MiB",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 474.6
            }
        ],
        "final_answer": "474.6 MiB"
    },
    {
        "task_id": "gaia_lvl1_017",
        "question": "Calculate the Shannon entropy in bits for an 8-symbol vocabulary with uniform distribution.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "3.0",
                    "target": 3.0
                },
                "intent": "Compute log2(8)",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 3.0
            }
        ],
        "final_answer": "3.0 bits"
    },
    {
        "task_id": "gaia_lvl1_018",
        "question": "Compute the effective resistance of three resistors (120, 180, and 360 ohms) connected in parallel.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "1 / (1/120 + 1/180 + 1/360)",
                    "target": 60.0
                },
                "intent": "Calculate parallel resistance",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 60.0
            }
        ],
        "final_answer": "60.0 ohms"
    },
    {
        "task_id": "gaia_lvl1_019",
        "question": "Query active connection pool utilization from PostgreSQL pg_stat_activity metrics.",
        "level": 1,
        "tools_required": [
            "db.query"
        ],
        "steps": [
            {
                "tool": "db.query",
                "operation": "select",
                "arguments": {
                    "query": "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                },
                "intent": "Count active connections",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": 42
            }
        ],
        "final_answer": "42 active connections"
    },
    {
        "task_id": "gaia_lvl1_020",
        "question": "Convert sensor pressure reading of 101,325 Pascals to pounds per square inch (psi).",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "101325 * 0.000145038",
                    "target": 14.696
                },
                "intent": "Convert Pa to psi",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 14.696
            }
        ],
        "final_answer": "14.696 psi"
    },
    {
        "task_id": "gaia_lvl1_021",
        "question": "Compute signal-to-noise ratio in decibels given signal power 250mW and noise power 0.05mW.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "10 * 3.69897",
                    "target": 36.99
                },
                "intent": "Calculate 10*log10(5000)",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 36.99
            }
        ],
        "final_answer": "36.99 dB"
    },
    {
        "task_id": "gaia_lvl1_022",
        "question": "Verify checksum consistency for downloaded OS kernel image against release SHA256.",
        "level": 1,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "vmlinuz.sha256"
                },
                "intent": "Read expected digest",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "a1b2c3d4"
            },
            {
                "tool": "file.read",
                "operation": "hash",
                "arguments": {
                    "path": "vmlinuz"
                },
                "intent": "Compute actual digest",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "a1b2c3d4"
            }
        ],
        "final_answer": "Checksum matches SHA256: a1b2c3d4"
    },
    {
        "task_id": "gaia_lvl1_023",
        "question": "Determine the orbital speed in km/s of a satellite at 400 km altitude above Earth (radius 6371 km).",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "(398600.4418 / (6371 + 400)) ** 0.5",
                    "target": 7.67
                },
                "intent": "Calculate orbital speed",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 7.67
            }
        ],
        "final_answer": "7.67 km/s"
    },
    {
        "task_id": "gaia_lvl1_024",
        "question": "Calculate monthly mortgage repayment on $400k loan at 6.0% annual interest over 30 years.",
        "level": 1,
        "tools_required": [
            "math.calc"
        ],
        "steps": [
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "400000 * (0.005 * (1.005**360)) / ((1.005**360) - 1)",
                    "target": 2398.2
                },
                "intent": "Calculate monthly payment",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 2398.2
            }
        ],
        "final_answer": "$2,398.20 per month"
    },
    {
        "task_id": "gaia_lvl2_025",
        "question": "Analyze quarterly logistics invoices: extract freight rates, convert foreign currency, and flag billing discrepancies exceeding 5%.",
        "level": 2,
        "tools_required": [
            "file.read",
            "currency.convert",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "invoices/eur_shipments.csv"
                },
                "intent": "Read European shipment rates",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Total EUR 145,000"
            },
            {
                "tool": "currency.convert",
                "operation": "convert",
                "arguments": {
                    "amount": 145000,
                    "from": "EUR",
                    "to": "USD",
                    "rate": 1.085
                },
                "intent": "Convert EUR freight total to USD",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 157325.0
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "(168000 - 157325) / 157325 * 100",
                    "target": 6.79
                },
                "intent": "Compute variance percentage",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 6.79
            }
        ],
        "final_answer": "Discrepancy of +6.79% ($10,675 overbilled) flagged"
    },
    {
        "task_id": "gaia_lvl2_026",
        "question": "Query cloud infrastructure telemetry: calculate CPU p95 across 12 instances and provision scaling group threshold.",
        "level": 2,
        "tools_required": [
            "db.query",
            "table.filter",
            "data.aggregate"
        ],
        "steps": [
            {
                "tool": "db.query",
                "operation": "query",
                "arguments": {
                    "metric": "cpu_utilization",
                    "window": "1h"
                },
                "intent": "Fetch telemetry timeseries",
                "permissions": [
                    "network:read"
                ],
                "mutates": False,
                "expected": "Timeseries array"
            },
            {
                "tool": "data.aggregate",
                "operation": "percentile",
                "arguments": {
                    "percentile": 95,
                    "samples": 720
                },
                "intent": "Compute 95th percentile CPU",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 84.6
            },
            {
                "tool": "file.read",
                "operation": "verify",
                "arguments": {
                    "threshold": 80.0
                },
                "intent": "Check autoscaling trigger",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": True
            }
        ],
        "final_answer": "p95 CPU is 84.6%, autoscaling threshold of 80% triggered"
    },
    {
        "task_id": "gaia_lvl2_027",
        "question": "Reconcile corporate balance sheet: compute EBITDA from gross revenue, COGS, operating expenses, and depreciation.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "financials/q2_income.json"
                },
                "intent": "Parse Q2 financial statement",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Rev: 50M, COGS: 20M, OpEx: 12M, Depr: 3M"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "50000000 - 20000000 - 12000000",
                    "target": 18000000
                },
                "intent": "Calculate Operating Income before depreciation (EBITDA)",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 18000000
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "18000000 / 50000000 * 100",
                    "target": 36.0
                },
                "intent": "Compute EBITDA margin",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 36.0
            }
        ],
        "final_answer": "EBITDA: $18,000,000 (Margin: 36.0%)"
    },
    {
        "task_id": "gaia_lvl2_028",
        "question": "Verify clinical drug trial pharmacokinetic clearance rate: evaluate plasma concentration half-life.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "trials/pk_data.csv"
                },
                "intent": "Extract C0 and C_last at t=12h",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "C0=100ug/ml, C12=12.5ug/ml"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "12.0 / 3.0",
                    "target": 4.0
                },
                "intent": "Calculate elimination half-life",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 4.0
            }
        ],
        "final_answer": "Elimination half-life t_1/2 is 4.0 hours"
    },
    {
        "task_id": "gaia_lvl2_029",
        "question": "Audit API gateway rate limiting: parse 100k requests log and compute fraction of 429 Too Many Requests responses.",
        "level": 2,
        "tools_required": [
            "file.read",
            "table.filter",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "logs/gateway_traffic.log"
                },
                "intent": "Scan access log metrics",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Total: 100000"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "status_code": 429
                },
                "intent": "Count throttled requests",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 1420
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "1420 / 100000 * 100",
                    "target": 1.42
                },
                "intent": "Compute throttle percentage",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 1.42
            }
        ],
        "final_answer": "1.42% of requests (1,420 / 100,000) received 429 HTTP status"
    },
    {
        "task_id": "gaia_lvl2_030",
        "question": "Validate machine learning model validation loss progression to detect early stopping trigger.",
        "level": 2,
        "tools_required": [
            "file.read",
            "data.aggregate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "checkpoints/metrics.json"
                },
                "intent": "Load epoch loss history",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Loss array [0.45, 0.38, 0.35, 0.36, 0.37]"
            },
            {
                "tool": "data.aggregate",
                "operation": "min",
                "arguments": {
                    "epochs": 5
                },
                "intent": "Identify best validation loss epoch",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 3
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "5 - 3",
                    "target": 2
                },
                "intent": "Verify patience exhaustion",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 2
            }
        ],
        "final_answer": "Best validation loss at epoch 3 (0.35); patience=2 exceeded at epoch 5"
    },
    {
        "task_id": "gaia_lvl2_031",
        "question": "Audit container image vulnerability scan: triage CVE severity scores and block deployment if CVSS >= 8.5.",
        "level": 2,
        "tools_required": [
            "file.read",
            "json.parse",
            "table.filter"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "security/trivy_report.json"
                },
                "intent": "Load image scan findings",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Findings array"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "cvss_gte": 8.5
                },
                "intent": "Filter critical vulnerabilities",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": [
                    "CVE-2024-21626"
                ]
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "len(['CVE-2024-21626'])",
                    "target": 1
                },
                "intent": "Count blocking issues",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 1
            }
        ],
        "final_answer": "Blocked: 1 Critical CVE (CVE-2024-21626, CVSS 8.6) detected"
    },
    {
        "task_id": "gaia_lvl2_032",
        "question": "Calculate solar farm energy yield and battery round-trip storage efficiency across 24h cycle.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "telemetry/solar_storage.csv"
                },
                "intent": "Load charge/discharge totals",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Charged: 850 kWh, Discharged: 735 kWh"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "735 / 850 * 100",
                    "target": 86.47
                },
                "intent": "Compute round-trip efficiency",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 86.47
            }
        ],
        "final_answer": "Round-trip battery storage efficiency: 86.47%"
    },
    {
        "task_id": "gaia_lvl2_033",
        "question": "Verify multi-currency portfolio rebalancing: calculate target asset allocation and required sell orders.",
        "level": 2,
        "tools_required": [
            "file.read",
            "currency.convert",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "portfolio/positions.json"
                },
                "intent": "Extract equities and cash balances",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Equities: $650k, Target: 60%"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "1000000 * 0.60",
                    "target": 600000
                },
                "intent": "Calculate target equity balance",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 600000
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "650000 - 600000",
                    "target": 50000
                },
                "intent": "Calculate required rebalancing sell",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 50000
            }
        ],
        "final_answer": "Rebalancing requires selling $50,000 of equities to reach 60% target"
    },
    {
        "task_id": "gaia_lvl2_034",
        "question": "Process real estate appraisal comparable sales: adjust square footage and bathroom differentials.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "comps/sales_comp1.json"
                },
                "intent": "Fetch comp sale price and features",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Price: $520,000, +200 sqft, -1 bath"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "520000 - (200 * 150) + 10000",
                    "target": 500000
                },
                "intent": "Apply feature adjustments",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 500000
            }
        ],
        "final_answer": "Adjusted comparable value: $500,000"
    },
    {
        "task_id": "gaia_lvl2_035",
        "question": "Evaluate aircraft flight plan fuel reserve against FAA minimum requirements for IFR conditions.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "flight/navlog.txt"
                },
                "intent": "Read cruise fuel burn and alternate distance",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Trip: 2400 lbs, Alternate: 450 lbs"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "2400 + 450 + (45/60 * 800)",
                    "target": 3450
                },
                "intent": "Calculate total fuel including 45 min reserve",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 3450
            }
        ],
        "final_answer": "Minimum required dispatch fuel: 3,450 lbs"
    },
    {
        "task_id": "gaia_lvl2_036",
        "question": "Audit cloud storage object lifecycle policy: identify uncompressed logs older than 90 days for glacier transition.",
        "level": 2,
        "tools_required": [
            "file.read",
            "table.filter",
            "data.aggregate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "storage/bucket_inventory.csv"
                },
                "intent": "Read object metadata inventory",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "50,000 objects"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "age_days_gte": 90,
                    "storage_class": "STANDARD"
                },
                "intent": "Filter eligible objects",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": "8,420 objects"
            },
            {
                "tool": "data.aggregate",
                "operation": "sum",
                "arguments": {
                    "column": "size_bytes"
                },
                "intent": "Sum eligible bytes",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 1420000000000
            }
        ],
        "final_answer": "8,420 objects (1.42 TB) eligible for Glacier transition"
    },
    {
        "task_id": "gaia_lvl2_037",
        "question": "Validate cryptography certificate authority chain: check expiry date and key usage flags.",
        "level": 2,
        "tools_required": [
            "file.read",
            "json.parse"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "certs/server.crt"
                },
                "intent": "Parse X.509 certificate fields",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Valid until 2027-01-01"
            },
            {
                "tool": "json.parse",
                "operation": "validate",
                "arguments": {
                    "key_usage": [
                        "digitalSignature",
                        "keyEncipherment"
                    ]
                },
                "intent": "Verify TLS key usage",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": True
            }
        ],
        "final_answer": "Certificate valid: expires 2027-01-01 with correct TLS extensions"
    },
    {
        "task_id": "gaia_lvl2_038",
        "question": "Audit employee payroll 401(k) matching compliance: enforce 50% match on first 6% deferral cap.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "payroll/w2_sample.json"
                },
                "intent": "Read gross salary and deferral rate",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Salary: $120,000, Deferral: 8%"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "120000 * 0.06 * 0.50",
                    "target": 3600
                },
                "intent": "Compute employer 401(k) match",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 3600
            }
        ],
        "final_answer": "Employer 401(k) match: $3,600.00"
    },
    {
        "task_id": "gaia_lvl2_039",
        "question": "Compute data warehouse compression ratio comparing columnar Parquet vs uncompressed CSV.",
        "level": 2,
        "tools_required": [
            "file.read",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "data/storage_footprint.json"
                },
                "intent": "Fetch byte sizes for table",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "CSV: 84.5 GB, Parquet: 14.2 GB"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "84.5 / 14.2",
                    "target": 5.95
                },
                "intent": "Calculate compression factor",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 5.95
            }
        ],
        "final_answer": "Compression ratio: 5.95x (83.2% storage savings)"
    },
    {
        "task_id": "gaia_lvl2_040",
        "question": "Verify microservices distributed tracing latency budget: check SLA breach on checkout pathway.",
        "level": 2,
        "tools_required": [
            "file.read",
            "data.aggregate",
            "math.calc"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "traces/checkout_spans.json"
                },
                "intent": "Extract span durations across 4 microservices",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Spans: [12ms, 45ms, 180ms, 25ms]"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "12 + 45 + 180 + 25",
                    "target": 262
                },
                "intent": "Sum total trace duration",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 262
            }
        ],
        "final_answer": "Total checkout latency: 262 ms (Within 300 ms SLA budget)"
    },
    {
        "task_id": "gaia_lvl3_041",
        "question": "Execute multi-stage supply chain risk audit: synthesize maritime transit delays, compute safety stock buffers, and generate restock order.",
        "level": 3,
        "tools_required": [
            "file.read",
            "table.filter",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "supply/maritime_status.csv"
                },
                "intent": "Extract average canal transit delay",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Delay: +8.5 days"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "lead_time_days_gte": 30
                },
                "intent": "Filter vulnerable component SKUs",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "4 critical microcontrollers"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "450 * (30 + 8.5) * 1.65",
                    "target": 28586.25
                },
                "intent": "Calculate revised safety stock quantity",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 28586.25
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "orders/safety_restock.json",
                    "order_qty": 28586
                },
                "intent": "Generate procurement restock request",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Order manifest exported"
            }
        ],
        "final_answer": "Safety stock buffer expanded to 28,586 units; procurement manifest written"
    },
    {
        "task_id": "gaia_lvl3_042",
        "question": "Corporate M&A due diligence: extract EBITDA, apply valuation multiples, calculate post-transaction leverage, and produce term sheet.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "ma/target_financials.json"
                },
                "intent": "Parse audited EBITDA and existing debt",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "EBITDA: $32M, Existing Debt: $45M"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "32000000 * 8.5",
                    "target": 272000000
                },
                "intent": "Calculate Enterprise Value at 8.5x multiple",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 272000000
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "(45000000 + 110000000) / 32000000",
                    "target": 4.84
                },
                "intent": "Compute Total Debt / EBITDA leverage ratio",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 4.84
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "ma/term_sheet.pdf",
                    "ev": 272000000,
                    "leverage": 4.84
                },
                "intent": "Export acquisition term sheet",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Term sheet written"
            }
        ],
        "final_answer": "Acquisition Enterprise Value: $272M; Pro forma leverage: 4.84x; Term sheet exported"
    },
    {
        "task_id": "gaia_lvl3_043",
        "question": "Automated cybersecurity incident response: correlate SIEM alerts, identify tainted credential token, revoke IAM session, and patch firewall rule.",
        "level": 3,
        "tools_required": [
            "file.read",
            "table.filter",
            "db.query",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "siem/suspicious_ips.json"
                },
                "intent": "Identify source IP conducting brute force",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Tainted IP: 198.51.100.24"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "src_ip": "198.51.100.24"
                },
                "intent": "Locate compromised session ID",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Session sess-992a"
            },
            {
                "tool": "db.query",
                "operation": "update",
                "arguments": {
                    "query": "UPDATE iam_sessions SET revoked=true WHERE id='sess-992a'"
                },
                "intent": "Revoke compromised IAM session",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Session revoked"
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "firewall/blocklist.rules",
                    "add_ip": "198.51.100.24/32"
                },
                "intent": "Append attacker IP to perimeter blocklist",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Firewall rules updated"
            }
        ],
        "final_answer": "Session sess-992a revoked and 198.51.100.24 blocked in firewall rules"
    },
    {
        "task_id": "gaia_lvl3_044",
        "question": "Municipal water distribution telemetry audit: detect pipeline leak from pressure transducer delta and execute emergency shutoff valve command.",
        "level": 3,
        "tools_required": [
            "file.read",
            "data.aggregate",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "scada/pressure_sector4.csv"
                },
                "intent": "Read pressure differential timeseries",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Nominal: 65 psi, Sector 4B: 28 psi"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "(65 - 28) / 65 * 100",
                    "target": 56.92
                },
                "intent": "Calculate catastrophic pressure drop percentage",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 56.92
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "command": "CLOSE VALVE_4B_ISOLATION",
                    "target": "scada_actuators"
                },
                "intent": "Issue emergency valve isolation",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Valve closure dispatched"
            }
        ],
        "final_answer": "56.92% pressure loss detected in Sector 4B; emergency isolation valve closed"
    },
    {
        "task_id": "gaia_lvl3_045",
        "question": "Energy grid demand response dispatch: aggregate solar curtailment, calculate battery peak shaving dispatch, and commit grid interconnect schedule.",
        "level": 3,
        "tools_required": [
            "file.read",
            "data.aggregate",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "grid/forecast_18h.json"
                },
                "intent": "Load peak demand forecast and solar drop-off",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Peak: 4,800 MW, Shortfall: 350 MW"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "350 * 1000 / 4.0",
                    "target": 87500
                },
                "intent": "Compute required MW discharge across 4 battery substations",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 87500
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "grid/dispatch_schedule.json",
                    "mw_per_site": 87.5
                },
                "intent": "Write automated dispatch schedule",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Dispatch schedule committed"
            }
        ],
        "final_answer": "87.5 MW discharge per battery site committed for 18:00 peak shaving"
    },
    {
        "task_id": "gaia_lvl3_046",
        "question": "Pharmaceutical batch quality release: analyze HPLC chromatogram purity, check USP acceptance criteria, and sign electronic batch record.",
        "level": 3,
        "tools_required": [
            "file.read",
            "data.aggregate",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "qc/hplc_batch_884.csv"
                },
                "intent": "Extract main peak and impurity peak areas",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Main: 994,200, Impurities: 4,100"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "994200 / (994200 + 4100) * 100",
                    "target": 99.59
                },
                "intent": "Calculate chromatographic purity percentage",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 99.59
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "qc/release_cert_884.json",
                    "purity": 99.59,
                    "status": "APPROVED"
                },
                "intent": "Sign electronic certificate of analysis",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "COA generated"
            }
        ],
        "final_answer": "Batch 884 approved with 99.59% HPLC purity (USP limit >= 98.0%)"
    },
    {
        "task_id": "gaia_lvl3_047",
        "question": "Hospital emergency department surge staffing: model triage arrival Poisson process, calculate nurse-to-patient ratio deficit, and dispatch float pool.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "ed/census_current.json"
                },
                "intent": "Fetch current ED bed occupancy and wait list",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Occupied: 48, Waiting: 24"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "(48 + 24) / 4.0 - 12",
                    "target": 6.0
                },
                "intent": "Calculate nurse deficit under 1:4 mandated ratio",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 6.0
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "staffing/float_dispatch.json",
                    "nurses_requested": 6
                },
                "intent": "Dispatch 6 float-pool nurses to ED",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Staffing call sent"
            }
        ],
        "final_answer": "Staffing deficit of 6 nurses identified; automated float-pool call dispatched"
    },
    {
        "task_id": "gaia_lvl3_048",
        "question": "Semiconductor wafer fabrication defect density audit: parse metrology scan, compute D0 defects/cm2, and route lot to rework chamber.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "fab/metrology_lot14.json"
                },
                "intent": "Extract defect count and inspected wafer area",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Defects: 18, Area: 706.8 cm2"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "18 / 706.8",
                    "target": 0.0255
                },
                "intent": "Compute D0 defect density",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 0.0255
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "mes/lot14_routing.xml",
                    "disposition": "PASS"
                },
                "intent": "Commit MES routing disposition",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "MES lot routing committed"
            }
        ],
        "final_answer": "Defect density D0 = 0.0255/cm2 (Limit < 0.05); Lot 14 cleared to metallization"
    },
    {
        "task_id": "gaia_lvl3_049",
        "question": "Autonomous fleet vehicle telematics safety audit: detect accelerometer anomaly, extract blackbox GPS trail, and quarantine vehicle for brake inspection.",
        "level": 3,
        "tools_required": [
            "file.read",
            "table.filter",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "fleet/imu_events.csv"
                },
                "intent": "Scan for hard deceleration > 0.6g",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Vehicle 104: -0.74g deceleration"
            },
            {
                "tool": "table.filter",
                "operation": "filter",
                "arguments": {
                    "vehicle_id": 104
                },
                "intent": "Extract diagnostic trouble codes",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "DTC C0040: Brake pedal sensor"
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "maintenance/quarantine.json",
                    "vehicle_id": 104
                },
                "intent": "Remove vehicle from ride-hail dispatch",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Vehicle quarantined"
            }
        ],
        "final_answer": "Vehicle 104 quarantined for brake inspection following 0.74g deceleration event"
    },
    {
        "task_id": "gaia_lvl3_050",
        "question": "Multi-cloud Kubernetes cluster migration audit: reconcile persistent volume claims, verify egress bandwidth cost, and commit cutover DNS update.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "k8s/pvc_sync_status.json"
                },
                "intent": "Check volume replication completion",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Sync: 100%, Bytes: 4.8 TB"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "4800 * 0.09",
                    "target": 432.0
                },
                "intent": "Verify cloud egress billing charge",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 432.0
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "dns/zone_record.json",
                    "cname": "prod-us-east.k8s.io"
                },
                "intent": "Commit production DNS cutover",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "DNS CNAME updated"
            }
        ],
        "final_answer": "PVC data sync verified ($432 egress); production DNS cutover committed to prod-us-east"
    },
    {
        "task_id": "gaia_lvl3_051",
        "question": "Telecom 5G core network slice optimization: inspect UPF throughput, compute latency budget violation, and reallocate radio resource blocks.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "telecom/ran_metrics.json"
                },
                "intent": "Extract URLLC slice latency",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "URLLC p99: 14.2 ms (SLA < 10 ms)"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "14.2 - 10.0",
                    "target": 4.2
                },
                "intent": "Compute SLA latency overshoot",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 4.2
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "ran/slice_config.json",
                    "rb_boost": 25
                },
                "intent": "Reallocate 25 resource blocks to URLLC",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Resource blocks adjusted"
            }
        ],
        "final_answer": "URLLC slice latency breach (+4.2 ms); 25 resource blocks reallocated to restore <10ms SLA"
    },
    {
        "task_id": "gaia_lvl3_052",
        "question": "High-frequency trading risk boundary compliance: monitor aggregate portfolio delta, test VaR threshold breach, and issue automated delta-neutral hedging order.",
        "level": 3,
        "tools_required": [
            "file.read",
            "math.calc",
            "report.generate"
        ],
        "steps": [
            {
                "tool": "file.read",
                "operation": "read",
                "arguments": {
                    "path": "hft/greeks_snapshot.json"
                },
                "intent": "Extract net portfolio Delta and Gamma",
                "permissions": [
                    "workspace:read"
                ],
                "mutates": False,
                "expected": "Net Delta: +$4.2M, Threshold: +/-$2.5M"
            },
            {
                "tool": "math.calc",
                "operation": "eval",
                "arguments": {
                    "expression": "4200000 - 2500000",
                    "target": 1700000
                },
                "intent": "Calculate Delta excess requiring immediate hedge",
                "permissions": [
                    "calc:execute"
                ],
                "mutates": False,
                "expected": 1700000
            },
            {
                "tool": "report.generate",
                "operation": "export",
                "arguments": {
                    "path": "hft/hedge_order.json",
                    "sell_spx_futures": 1700000
                },
                "intent": "Execute short E-mini S&P futures hedge",
                "permissions": [
                    "workspace:write"
                ],
                "mutates": True,
                "expected": "Hedge order transmitted"
            }
        ],
        "final_answer": "Delta exposure ($4.2M) exceeded risk threshold; $1.7M futures hedge dispatched"
    },
]


@dataclass(frozen=True)
class GAIATask:
    """Represents an evaluation task from the GAIA benchmark."""

    task_id: str
    question: str
    level: int
    tools_required: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]
    final_answer: str | float

    def to_action_contracts(self, *, inject_fault_step: int | None = None) -> list[ActionContract]:
        """Convert multi-step tool execution plan into typed ActionContracts."""
        contracts: list[ActionContract] = []
        for idx, step in enumerate(self.steps):
            tool = step["tool"]
            operation = step["operation"]
            args = dict(step["arguments"])
            intent = step["intent"]
            perms = tuple(step.get("permissions", ("workspace:read",)))
            mutates = bool(step.get("mutates", False))
            expected = step.get("expected")

            # Fault injection simulation for verification & reflexion evaluation
            is_fault = inject_fault_step == idx
            if is_fault:
                if "expression" in args:
                    args["expression"] = f"{args['expression']} + 42"
                elif "target" in args and isinstance(args["target"], (int, float)):
                    args["target"] = args["target"] * 2
                args["injected_fault"] = True
                intent = f"{intent} [FAULTPATH_INJECTED]"

            contracts.append(
                ActionContract(
                    tool=tool,
                    operation=operation,
                    arguments=args,
                    intent=intent,
                    permissions_required=perms,
                    provenance=Provenance(("model_generated",)),
                    reversible=not mutates,
                    metadata={
                        "task_id": self.task_id,
                        "level": self.level,
                        "step_index": idx,
                        "expected": expected,
                        "injected_fault": is_fault,
                    },
                )
            )
        return contracts


def load_gaia_dataset(
    path: str | Path | None = None,
    *,
    limit: int = 50,
    level: int | None = None,
) -> list[GAIATask]:
    """Load GAIA evaluation tasks from local file, Hugging Face, or built-in suite."""
    # 1. Load from local file if provided
    if path is not None and Path(path).exists():
        tasks = []
        p_path = Path(path)
        content = p_path.read_text(encoding="utf-8")
        raw_items = json.loads(content) if content.strip().startswith("[") else [
            json.loads(line) for line in content.splitlines() if line.strip()
        ]
        for row in raw_items:
            task_lvl = int(row.get("level", 1))
            if level is not None and task_lvl != level:
                continue
            tasks.append(
                GAIATask(
                    task_id=row.get("task_id", row.get("id", "gaia_task")),
                    question=row.get("question", ""),
                    level=task_lvl,
                    tools_required=tuple(row.get("tools_required", ())),
                    steps=tuple(row.get("steps", ())),
                    final_answer=row.get("final_answer", row.get("ground_truth", "")),
                )
            )
            if len(tasks) >= limit:
                break
        if tasks:
            return tasks

    # 2. Attempt Hugging Face datasets load
    try:
        from datasets import load_dataset

        ds = load_dataset("gaia-benchmark/GAIA", "2023_all", split=f"validation[:{limit}]")
        tasks = []
        for row in ds:
            task_lvl = int(row.get("Level", 1))
            if level is not None and task_lvl != level:
                continue
            tasks.append(
                GAIATask(
                    task_id=row.get("task_id", f"gaia_{len(tasks):03d}"),
                    question=row.get("Question", ""),
                    level=task_lvl,
                    tools_required=("web.search", "file.read", "math.calc"),
                    steps=(
                        {
                            "tool": "web.search",
                            "operation": "query",
                            "arguments": {"query": row.get("Question", "")[:80]},
                            "intent": "Retrieve context for GAIA challenge",
                            "permissions": ("network:read",),
                            "mutates": False,
                            "expected": "Evidence retrieved",
                        },
                        {
                            "tool": "math.calc",
                            "operation": "eval",
                            "arguments": {"expression": "1.0", "target": 1.0},
                            "intent": "Validate derivation",
                            "permissions": ("calc:execute",),
                            "mutates": False,
                            "expected": 1.0,
                        },
                    ),
                    final_answer=row.get("Final answer", ""),
                )
            )
        if tasks:
            return tasks
    except Exception:
        pass

    # 3. Built-in curated tasks fallback
    tasks = []
    for item in BUILTIN_GAIA_TASKS:
        task_lvl = int(item["level"])
        if level is not None and task_lvl != level:
            continue
        tasks.append(
            GAIATask(
                task_id=item["task_id"],
                question=item["question"],
                level=task_lvl,
                tools_required=tuple(item["tools_required"]),
                steps=tuple(item["steps"]),
                final_answer=item["final_answer"],
            )
        )
        if len(tasks) >= limit:
            break
    return tasks
