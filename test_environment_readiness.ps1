# VERITAS Environment Readiness Diagnostic
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "VERITAS Runtime Environment Diagnostic" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Check CPU Hardware Virtualization
Write-Host "1. Checking CPU Hardware Virtualization (BIOS/Firmware)..." -NoNewline
$cpu = Get-CimInstance Win32_Processor
if ($cpu.VirtualizationFirmwareEnabled) {
    Write-Host " [PASSED]" -ForegroundColor Green
    Write-Host "   -> Intel VT-x is Enabled in ASUS BIOS." -ForegroundColor Gray
} else {
    Write-Host " [ACTION REQUIRED]" -ForegroundColor Red
    Write-Host "   -> Intel VT-x is DISABLED in ASUS ROG BIOS." -ForegroundColor Yellow
    Write-Host "   -> Restart PC -> Press Del/F2 -> Advanced -> CPU Configuration -> Intel Virtualization Technology -> Enabled." -ForegroundColor Yellow
}

# 2. Check WSL Status
Write-Host "2. Checking Windows Subsystem for Linux (WSL)..." -NoNewline
try {
    $wslStatus = wsl.exe --status 2>&1 | Out-String
    if ($wslStatus -match "Default Version: 2" -and $wslStatus -notmatch "unable to start") {
        Write-Host " [PASSED]" -ForegroundColor Green
    } elseif ($wslStatus -match "Changes will not be effective until the system is rebooted") {
        Write-Host " [REBOOT REQUIRED]" -ForegroundColor Yellow
        Write-Host "   -> WSL installed, pending system reboot." -ForegroundColor Yellow
    } else {
        Write-Host " [PENDING REBOOT/VT-X]" -ForegroundColor Yellow
        Write-Host "   -> WSL2 waiting for BIOS Virtualization to be enabled." -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAILED]" -ForegroundColor Red
}

# 3. Check Docker Engine
Write-Host "3. Checking Docker Daemon..." -NoNewline
try {
    $dockerInfo = docker info 2>&1 | Out-String
    if ($dockerInfo -match "Server:" -and $dockerInfo -notmatch "failed to connect") {
        Write-Host " [PASSED]" -ForegroundColor Green
        Write-Host "   -> Docker engine is running and responding." -ForegroundColor Gray
    } else {
        Write-Host " [IDLE / NOT STARTED]" -ForegroundColor Yellow
        Write-Host "   -> Open Docker Desktop after reboot." -ForegroundColor Gray
    }
} catch {
    Write-Host " [NOT FOUND]" -ForegroundColor Red
}

# 4. Check Local LLM Backend (Ollama)
Write-Host "4. Checking Local Ollama Models..." -NoNewline
try {
    $ollamaProc = Get-Process ollama -ErrorAction SilentlyContinue
    if ($ollamaProc) {
        Write-Host " [PASSED]" -ForegroundColor Green
        $models = ollama list 2>&1 | Out-String
        Write-Host "   -> Ollama is running with available models:" -ForegroundColor Gray
        $models.Split("`n") | Select-Object -First 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    } else {
        Write-Host " [NOT RUNNING]" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [NOT FOUND]" -ForegroundColor Red
}

# 5. Check VERITAS CLI
Write-Host "5. Checking VERITAS Python Environment..." -NoNewline
if (Test-Path ".\.venv\Scripts\veritas.exe") {
    $doctor = .\.venv\Scripts\veritas.exe doctor 2>&1 | Out-String
    if ($doctor -match '"configuration":"valid"') {
        Write-Host " [PASSED]" -ForegroundColor Green
        Write-Host "   -> VERITAS CLI is installed and configuration is valid." -ForegroundColor Gray
    } else {
        Write-Host " [WARNING]" -ForegroundColor Yellow
        Write-Host "   -> Doctor returned: $doctor" -ForegroundColor Gray
    }
} else {
    Write-Host " [MISSING]" -ForegroundColor Red
}

Write-Host "========================================================" -ForegroundColor Cyan
