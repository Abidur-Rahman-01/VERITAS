# VERITAS Runtime Environment: Docker & WSL2 Setup Guide

This document explains how VERITAS connects with Docker and WSL2 to run experiments, benchmarks, and sandboxed coding tasks at runtime.

---

## 1. Architecture Overview

VERITAS uses a two-tier Docker architecture to isolate agent execution and grade software engineering benchmarks:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Windows / WSL Host                                                          │
│                                                                             │
│  ┌───────────────────────────────┐        ┌───────────────────────────────┐ │
│  │ Docker Engine / Desktop       │◄───────│ Local LLMs (Ollama / VLLM)    │ │
│  │ (WSL 2 Backend)               │        │ http://localhost:11434        │ │
│  └──────────────▲────────────────┘        └───────────────────────────────┘ │
│                 │ /var/run/docker.sock mounted                               │
│  ┌──────────────┴─────────────────────────────────────────────────────────┐ │
│  │ Coordinator Container (`veritas:latest`)                               │ │
│  │   - Python 3.12 + isolated venv at `/opt/venv`                         │ │
│  │   - Veritas CLI + SWE-bench + dev tooling                              │ │
│  │   - Mounts project workspace at `/app` (live code & artifact sync)     │ │
│  │   - Communicates with Host models via `host.docker.internal`           │ │
│  └──────────────┬─────────────────────────────────────────────────────────┘ │
│                 │ Spawns on demand (Docker-out-of-Docker)                   │
│  ┌──────────────▼─────────────────────────────────────────────────────────┐ │
│  │ Sandbox Containers (`veritas-sandbox:local` / SWE benchmark images)    │ │
│  │   - Disposable, non-networked (`--network none`)                        │ │
│  │   - Drops capabilities (`--cap-drop ALL`), strict memory/CPU caps       │ │
│  │   - Executes tool actions (read/write/pytest/diff) safely               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Components:
1. **`veritas:latest` (built from `Dockerfile`)**:
   - The primary coordinator environment containing Python 3.12, `uv`, `veritas`, and `swebench`.
   - Uses `/opt/venv` to keep the container's Linux virtual environment separate from the host's `/app` volume mount.
   - Accesses `/var/run/docker.sock` to launch sandboxes.
2. **`veritas-sandbox:local` (built from `Dockerfile.sandbox`)**:
   - The sandbox execution image with `pytest` and unprivileged execution limits.
3. **`docker-compose.yml`**:
   - Pre-configured targets: `veritas`, `veritas-test`, `veritas-reproduce`, and `veritas-bash`.

---

## 2. Hardware & System Requirements

Running Linux containers and WSL2 on Windows requires hardware-level CPU virtualization:

| Component | Status / Requirement |
|---|---|
| **CPU** | Intel Core i9-11900 |
| **Motherboard** | ASUS ROG MAXIMUS XII EXTREME |
| **BIOS Setting** | **Intel (VMX) Virtualization Technology** must be **Enabled** |
| **Windows OS** | Windows 11 Pro (Build 26200+) |
| **Windows Features** | `Microsoft-Windows-Subsystem-Linux` & `VirtualMachinePlatform` |
| **Container Engine**| Docker Desktop with WSL2 backend |

---

## 3. Step-by-Step Setup

### Step 1: Run the Automated Enablement Script
Open the VERITAS project folder and double-click `enable_docker_wsl.bat` (or run it in PowerShell):
```cmd
.\enable_docker_wsl.bat
```
This script automatically:
- Requests Administrator permissions (UAC prompt).
- Detects whether Intel VT-x is enabled in BIOS.
- Enables `Microsoft-Windows-Subsystem-Linux` and `VirtualMachinePlatform` via Windows DISM.
- Sets WSL default version to 2 and prepares the WSL kernel.

### Step 2: Enable Intel VT-x in ASUS BIOS
During PC reboot:
1. Tap **DEL** or **F2** repeatedly as the PC turns on to enter the **ASUS UEFI BIOS**.
2. Press **F7** to enter **Advanced Mode** (if in EZ Mode).
3. Click the **Advanced** tab at the top.
4. Click **CPU Configuration**.
5. Scroll down to **Intel (VMX) Virtualization Technology** and change it from **Disabled** to **Enabled**.
6. Press **F10** (Save Changes & Reset), then press **Enter**.

### Step 3: Launch Docker Desktop
Once Windows boots:
1. Open **Docker Desktop** from the Start Menu.
2. Docker Desktop will detect WSL2 and start the Linux container engine automatically.
3. Verify in PowerShell:
   ```powershell
   docker info
   ```

---

## 4. Running Experiments at Runtime

Use `run_docker.bat` (CMD), `run_docker.ps1` (PowerShell), or `./run_docker.sh` (WSL / Bash).

### Action-Time TSE Experiment (Three Arms)

The action-time experiment uses the same actor in every arm: `qwen3-coder:30b`. Ollama’s official Qwen3-Coder catalog currently provides a 30B model (about 19 GB on disk), rather than a 20B tag. Arms 1 and 2 use `qwen2.5-coder:14b` as verifier; Arm 0 remains unverified and makes no verifier calls. Ollama runs on the Windows host, and Docker reaches it through `host.docker.internal` using `VERITAS_OLLAMA_BASE_URL`.

In PowerShell, from the project root:

```powershell
ollama pull qwen3-coder:30b
ollama pull qwen2.5-coder:14b
docker compose build veritas
docker compose run --rm --entrypoint python veritas scripts/run_action_time_tse_experiment.py --tasks 20 --output artifacts/action_time_pilot
docker compose run --rm --entrypoint python veritas scripts/analyze_action_time_study.py --study-dir artifacts/action_time_pilot
docker compose run --rm --entrypoint python veritas scripts/generate_tse_action_time_figures.py --study-dir artifacts/action_time_pilot
```

After the pilot finishes, run the current 60-task registry (180 task-arm trials):

```powershell
docker compose run --rm --entrypoint python veritas scripts/run_action_time_tse_experiment.py --tasks 60 --output artifacts/action_time_study
docker compose run --rm --entrypoint python veritas scripts/analyze_action_time_study.py --study-dir artifacts/action_time_study
docker compose run --rm --entrypoint python veritas scripts/generate_tse_action_time_figures.py --study-dir artifacts/action_time_study
```

This runner uses its configured local sandbox inside the coordinator container; it does not start a nested Docker sandbox for each trial. The `veritas-sandbox` image is used by other Docker-backed grading workflows.

### A. Build the Project Images
```cmd
run_docker.bat build
```
*(or `.\run_docker.ps1 build`)*

### B. Run the Full Test Suite in Docker
Runs all unit and integration Docker sandbox tests:
```cmd
run_docker.bat test
```

### C. Run Replication & Statistical Audit
Re-runs every statistical contrast, Fisher exact test, and figure generator reported in the paper:
```cmd
run_docker.bat reproduce
```

### D. Run the Evaluation-Awareness Pilot Experiment
Plan the experimental factorial design:
```cmd
run_docker.bat veritas awareness plan --config configs/awareness-pilot.example.yaml --output runs/pilot
```
Execute the trial run:
```cmd
run_docker.bat veritas awareness run --study runs/pilot
```
Grade completed patches with the independent grader:
```cmd
run_docker.bat veritas awareness grade --study runs/pilot
```
Generate statistical reports:
```cmd
run_docker.bat veritas awareness report --study runs/pilot
```

### E. Interactive Container Shell
For debugging or manual shell operations inside the Linux container:
```cmd
run_docker.bat bash
```

---

## 5. Troubleshooting

- **`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`**:
  Docker Desktop is not currently running. Start Docker Desktop from the Start Menu after enabling VT-x in BIOS.
- **`WslRegisterDistribution failed with error: 0x80370102`**:
  Intel VT-x is not enabled in BIOS. Follow Step 2 above to turn on Intel (VMX) Virtualization Technology.
- **`Cannot connect to Ollama at host.docker.internal:11434`**:
  Ensure Ollama is running on your host machine and listening on `0.0.0.0:11434` (set `OLLAMA_HOST=0.0.0.0:11434` in Windows environment variables).
