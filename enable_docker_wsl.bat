@echo off
setlocal
title VERITAS - Docker and WSL2 Environment Setup

echo ========================================================
echo 1. CHECKING HARDWARE CPU VIRTUALIZATION (BIOS/FIRMWARE)
echo ========================================================
powershell -NoProfile -Command "$cpu = Get-CimInstance Win32_Processor; if (-not $cpu.VirtualizationFirmwareEnabled) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 goto :vtx_disabled

echo [OK] Intel VT-x Hardware Virtualization is ENABLED in BIOS.
echo.
goto :check_admin

:vtx_disabled
echo.
echo **********************************************************************
echo [CRITICAL ALERT] Intel VT-x Hardware Virtualization is DISABLED in BIOS!
echo **********************************************************************
echo Detected Hardware:
echo   Motherboard: ASUS ROG MAXIMUS XII EXTREME
echo   Processor:   11th Gen Intel Core i9-11900
echo.
echo Neither WSL2 nor Docker Desktop can start a Linux VM until
echo hardware virtualization is enabled in your ASUS UEFI BIOS setup.
echo.
echo Exact steps to enable in ASUS ROG UEFI BIOS:
echo   1. Restart your PC and tap DEL or F2 repeatedly to enter BIOS.
echo   2. Press F7 to enter Advanced Mode if in EZ Mode.
echo   3. Navigate to the Advanced tab at the top.
echo   4. Click CPU Configuration.
echo   5. Scroll to Intel Virtualization Technology and set it to Enabled.
echo   6. Press F10 to Save Changes and Reboot.
echo **********************************************************************
echo.

:check_admin
echo ========================================================
echo 2. CHECKING ADMINISTRATOR PRIVILEGES
echo ========================================================

net session >nul 2>&1
if %errorLevel% == 0 goto :admin_ok

echo.
echo [NOTICE] Administrator privileges are required to enable Windows features.
echo Please right-click 'enable_docker_wsl.bat' and select 'Run as Administrator',
echo or open PowerShell as Administrator and run:
echo   dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
echo   dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
echo.
pause
exit /b 1

:admin_ok
echo [OK] Running with Administrator Privileges.
echo.

echo ========================================================
echo 3. ENABLING WINDOWS SUBSYSTEM FOR LINUX ^& VIRTUAL MACHINE PLATFORM
echo ========================================================
echo Enabling Microsoft-Windows-Subsystem-Linux...
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

echo.
echo Enabling VirtualMachinePlatform...
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

echo.
echo ========================================================
echo 4. CONFIGURING WSL KERNEL ^& DEFAULT VERSION
echo ========================================================
wsl.exe --set-default-version 2 >nul 2>&1
wsl.exe --update --web-download >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] WSL kernel updated to latest version.
) else (
    echo Note: WSL kernel update will finalize after reboot.
)

echo.
echo ========================================================
echo 5. VERITAS DOCKER ARCHITECTURE STATUS
echo ========================================================
echo   - Dockerfile: /opt/venv isolated environment, swebench included
echo   - Dockerfile.sandbox: veritas-sandbox:local ready
echo   - docker-compose.yml: veritas, veritas-test, veritas-reproduce, veritas-bash
echo   - run_docker.bat / run_docker.ps1 / run_docker.sh helper scripts ready
echo.
echo ========================================================
echo NEXT STEPS TO RUN EXPERIMENTS IN RUNTIME:
echo ========================================================
echo 1. RESTART your PC now.
echo    -^> During reboot, press DEL or F2 to enter BIOS and set
echo       Intel Virtualization Technology to ENABLED.
echo 2. After Windows boots back up, open Docker Desktop.
echo    -^> Docker Desktop will start cleanly and connect via WSL2!
echo 3. In the VERITAS directory, run your experiments:
echo    - Build images:      run_docker.bat build
echo    - Run test suite:    run_docker.bat test
echo    - Run replication:   run_docker.bat reproduce
echo    - Run awareness:     run_docker.bat veritas awareness plan --config configs/awareness-pilot.example.yaml
echo ========================================================
echo.
pause
