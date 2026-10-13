<#
.SYNOPSIS
    VERITAS Docker Runner for PowerShell
.DESCRIPTION
    Helper script to build, test, and run runtime experiments in Docker.
.EXAMPLE
    .\run_docker.ps1 build
    .\run_docker.ps1 test
    .\run_docker.ps1 reproduce
    .\run_docker.ps1 bash
    .\run_docker.ps1 veritas awareness plan --config configs/awareness-pilot.example.yaml
#>

param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $RepoRoot

if (-not $Arguments -or $Arguments.Count -eq 0) {
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "VERITAS Docker CLI - Experiment Runner" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "Usage:"
    Write-Host "  .\run_docker.ps1 build            Build the Docker images"
    Write-Host "  .\run_docker.ps1 test             Run test suite inside Docker"
    Write-Host "  .\run_docker.ps1 reproduce        Run full replication statistical audit"
    Write-Host "  .\run_docker.ps1 bash             Launch interactive bash shell"
    Write-Host "  .\run_docker.ps1 veritas <args>   Run veritas CLI command"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run_docker.ps1 build"
    Write-Host "  .\run_docker.ps1 test"
    Write-Host "  .\run_docker.ps1 veritas awareness plan --config configs/awareness-pilot.example.yaml"
    Write-Host "========================================================" -ForegroundColor Cyan
    exit 0
}

$Command = $Arguments[0]
$Rest = $Arguments | Select-Object -Skip 1

switch ($Command.ToLower()) {
    "build" {
        Write-Host "Building VERITAS Docker images..." -ForegroundColor Green
        docker compose build veritas-sandbox veritas
    }
    "test" {
        Write-Host "Running VERITAS tests in Docker..." -ForegroundColor Green
        docker compose run --rm veritas-test
    }
    "reproduce" {
        Write-Host "Running replication audit in Docker..." -ForegroundColor Green
        docker compose run --rm veritas-reproduce
    }
    "bash" {
        Write-Host "Launching interactive shell in Docker container..." -ForegroundColor Green
        docker compose run --rm veritas-bash
    }
    "veritas" {
        docker compose run --rm veritas @Rest
    }
    default {
        docker compose run --rm veritas @Arguments
    }
}
