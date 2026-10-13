@echo off
setlocal

:: VERITAS Docker Runner for Windows
:: Convenient shortcut to build, test, and run runtime experiments in Docker

cd /d "%~dp0"

if "%~1"=="" (
    echo ========================================================
    echo VERITAS Docker CLI - Experiment Runner
    echo ========================================================
    echo Usage:
    echo   run_docker.bat build            Build the Docker images
    echo   run_docker.bat test             Run test suite inside Docker container
    echo   run_docker.bat reproduce        Run full replication statistical audit
    echo   run_docker.bat bash             Launch interactive bash shell in container
    echo   run_docker.bat veritas [args]   Run veritas CLI command in container
    echo.
    echo Examples:
    echo   run_docker.bat build
    echo   run_docker.bat test
    echo   run_docker.bat veritas awareness plan --config configs/awareness-pilot.example.yaml
    echo   run_docker.bat veritas --help
    echo ========================================================
    exit /b 0
)

if /i "%~1"=="build" (
    echo Building VERITAS Docker images...
    docker compose build veritas-sandbox veritas
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="test" (
    echo Running VERITAS tests in Docker...
    docker compose run --rm veritas-test
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="reproduce" (
    echo Running replication audit in Docker...
    docker compose run --rm veritas-reproduce
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="bash" (
    echo Launching interactive shell in Docker container...
    docker compose run --rm veritas-bash
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="veritas" (
    shift
    docker compose run --rm veritas %*
    exit /b %ERRORLEVEL%
)

:: Pass through any other command to docker compose run veritas
docker compose run --rm veritas %*
exit /b %ERRORLEVEL%
