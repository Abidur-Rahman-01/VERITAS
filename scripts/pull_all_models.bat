@echo off
setlocal

echo Updating PATH to include Ollama...
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"

where ollama >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] ollama.exe was not found in %LOCALAPPDATA%\Programs\Ollama or in PATH.
    echo Please make sure Ollama is installed.
    exit /b 1
)

echo Ollama found:
ollama --version

echo ======================================================
echo Pulling requested models...
echo ======================================================

set "MODELS=tinyllama qwen2.5:1.5b qwen2.5:3b llama3.2:3b phi3.5 qwen2.5:7b llama3.1:8b gemma3:4b gemma3:12b qwen2.5:14b"

for %%m in (%MODELS%) do (
    echo.
    echo ------------------------------------------------------
    echo [PULLING] %%m ...
    echo ------------------------------------------------------
    ollama pull %%m
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Failed to pull %%m
    ) else (
        echo [SUCCESS] Pulled %%m
    )
)

echo.
echo ======================================================
echo All model pulls attempted. Current models in Ollama:
echo ======================================================
ollama list

endlocal
