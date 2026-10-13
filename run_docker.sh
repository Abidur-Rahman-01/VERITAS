#!/usr/bin/env bash
# VERITAS Docker Runner for Linux / WSL
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -eq 0 ]; then
    echo "========================================================"
    echo "VERITAS Docker CLI - Experiment Runner"
    echo "========================================================"
    echo "Usage:"
    echo "  ./run_docker.sh build            Build the Docker images"
    echo "  ./run_docker.sh test             Run test suite inside Docker container"
    echo "  ./run_docker.sh reproduce        Run full replication statistical audit"
    echo "  ./run_docker.sh bash             Launch interactive bash shell in container"
    echo "  ./run_docker.sh veritas [args]   Run veritas CLI command in container"
    echo ""
    echo "Examples:"
    echo "  ./run_docker.sh build"
    echo "  ./run_docker.sh test"
    echo "  ./run_docker.sh veritas awareness plan --config configs/awareness-pilot.example.yaml"
    echo "========================================================"
    exit 0
fi

CMD="$1"
shift || true

case "$CMD" in
    build)
        echo "Building VERITAS Docker images..."
        docker compose build veritas-sandbox veritas
        ;;
    test)
        echo "Running VERITAS tests in Docker..."
        docker compose run --rm veritas-test
        ;;
    reproduce)
        echo "Running replication audit in Docker..."
        docker compose run --rm veritas-reproduce
        ;;
    bash)
        echo "Launching interactive shell in Docker container..."
        docker compose run --rm veritas-bash
        ;;
    veritas)
        docker compose run --rm veritas "$@"
        ;;
    *)
        docker compose run --rm veritas "$CMD" "$@"
        ;;
esac
