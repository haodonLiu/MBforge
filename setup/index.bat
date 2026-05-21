@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ========================================
echo     MBForge one-click setup (interactive)
echo ========================================
echo.

set "PYTHON=.venv\Scripts\python.exe"
set "SCRIPT_DIR=%~dp0"

:: === 01 Basic Environment ===
echo --- Basic Environment Check ---
where uv >nul 2>&1
if errorlevel 1 (
    echo [FAIL] uv not found
    exit /b 1
)
for /f "tokens=*" %%i in ('uv --version') do echo [OK] %%i

if not exist ".venv" (
    uv venv .venv --python 3.12
    echo [OK] venv created
) else (echo [OK] venv exists)

uv sync --dev
%PYTHON% -c "import csar" >nul 2>&1
if errorlevel 1 (
    uv pip install -e setup/openSAR/ --python .venv\Scripts\python.exe
)
echo [OK] dependencies installed

:: === 02 UniParser ===
echo.
echo --- UniParser Config ---
set "UNIPARSER_HOST="
set "UNIPARSER_KEY="
set /p "UP=Configure UniParser? [Y/n]: "
if /i not "%UP%"=="n" (
    set /p "UNIPARSER_HOST=Server URL [https://uniparser.dp.tech/]: "
    if "!UNIPARSER_HOST!"=="" set "UNIPARSER_HOST=https://uniparser.dp.tech/"
    set /p "UNIPARSER_KEY=API Key: "
)

:: === 03 Ollama ===
echo.
echo --- Ollama Detection ---
set "OLLAMA_AVAILABLE=0"
where ollama >nul 2>&1
if not errorlevel 1 (
    set "OLLAMA_AVAILABLE=1"
    echo [OK] Ollama detected
)

:: === 04 LLM ===
echo.
echo --- LLM Config ---
echo   1) OpenAI compatible API
echo   2) Anthropic
if "%OLLAMA_AVAILABLE%"=="1" echo   3) Ollama
set /p "LC=Select [1]: "
if "%LC%"=="" set "LC=1"

set "LLM_PROVIDER=openai_compatible"
set "LLM_BASE_URL=https://api.siliconflow.cn/v1"
set "LLM_API_KEY="
set "LLM_MODEL=Qwen/Qwen2.5-7B-Instruct"

if "%LC%"=="2" (
    set "LLM_PROVIDER=anthropic"
    set "LLM_BASE_URL=https://api.minimaxi.com/anthropic"
    set "LLM_MODEL=MiniMax-M2.7"
)
if "%LC%"=="3" if "%OLLAMA_AVAILABLE%"=="1" (
    set "LLM_PROVIDER=ollama"
    set "LLM_BASE_URL=http://localhost:11434/v1"
    set "LLM_API_KEY=ollama"
    set "LLM_MODEL=qwen2.5:7b"
)

set /p "LLM_BASE_URL=API Base URL [!LLM_BASE_URL!]: "
if "!LLM_BASE_URL!"=="" set "LLM_BASE_URL=!LLM_BASE_URL!"
set /p "LLM_API_KEY=API Key: "
set /p "LLM_MODEL=Model [!LLM_MODEL!]: "
if "!LLM_MODEL!"=="" set "LLM_MODEL=!LLM_MODEL!"
echo [OK] LLM: %LLM_PROVIDER% / %LLM_MODEL%

:: === 05 Embedding / Rerank ===
echo.
echo --- Model Config ---
set "EMBED_MODEL=BAAI/bge-small-zh-v1.5"
set "RERANK_MODEL=BAAI/bge-reranker-base"

echo Embedding: 1) bge-small  2) bge-large  3) Qwen3-Embedding
set /p "EC=Select [1]: "
if "%EC%"=="2" set "EMBED_MODEL=BAAI/bge-large-zh-v1.5"
if "%EC%"=="3" set "EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B"

echo Rerank: 1) bge-base  2) bge-v2-m3  3) Qwen3-Reranker
set /p "RC=Select [1]: "
if "%RC%"=="2" set "RERANK_MODEL=BAAI/bge-reranker-v2-m3"
if "%RC%"=="3" set "RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B"

:: === 05b Embedding/Rerank Device ===
echo.
echo --- Embedding/Rerank Device ---
set "EMBED_DEVICE=cpu"
set "RERANK_DEVICE=cpu"
%PYTHON% -c "import torch; assert torch.cuda.is_available()" 2>nul
if not errorlevel 1 (
    echo   GPU detected, use CUDA for inference?
    echo   1) Yes (GPU)  2) No (CPU)
    set /p "GD=Select [2]: "
    if "!GD!"=="1" (
        set "EMBED_DEVICE=cuda"
        set "RERANK_DEVICE=cuda"
        echo [OK] GPU mode enabled
    ) else (
        echo [OK] CPU mode
    )
) else (
    echo [OK] No GPU detected, using CPU
)

:: === 07b Model Cache Directories ===
echo.
echo --- Model Cache Directories ---
set "HF_HOME=%USERPROFILE%\Models\HuggingFace"
set "MODELSCOPE_CACHE=%USERPROFILE%\Models\ModelScope"
set "TORCH_HOME=%USERPROFILE%\Models\Torch"
set "OLLAMA_MODELS=%USERPROFILE%\Models\Ollama"
echo   Default: %%USERPROFILE%%\Models\...
set /p "HC=Customize cache directories? [y/N]: "
if /i "!HC!"=="y" (
    set /p "HF_HOME=  HuggingFace [%%HF_HOME%%]: "
    set /p "MODELSCOPE_CACHE=  ModelScope [%%MODELSCOPE_CACHE%%]: "
    set /p "TORCH_HOME=  PyTorch [%%TORCH_HOME%%]: "
    set /p "OLLAMA_MODELS=  Ollama [%%OLLAMA_MODELS%%]: "
    echo [OK] Custom cache dirs set
) else (
    echo [OK] Using default: %%USERPROFILE%%\Models\...
)

:: === 07 Write .env ===
echo.
echo --- Write Config ---
if exist ".env" copy .env .env.bak >nul 2>&1

(
echo # UniParser
echo UNIPARSER_HOST=%UNIPARSER_HOST%
echo UNIPARSER_API_KEY=%UNIPARSER_KEY%
echo.
echo # LLM
echo MBFORGE_LLM_PROVIDER=%LLM_PROVIDER%
echo MBFORGE_LLM_BASE_URL=%LLM_BASE_URL%
echo MBFORGE_LLM_API_KEY=%LLM_API_KEY%
echo MBFORGE_LLM_MODEL=%LLM_MODEL%
echo MBFORGE_LLM_MAX_TOKENS=4096
echo MBFORGE_LLM_TEMPERATURE=0.7
echo MBFORGE_LLM_TOP_P=0.9
echo.
echo # Embedding
echo MBFORGE_EMBED_PROVIDER=sentence_transformers
echo MBFORGE_EMBED_MODEL=%EMBED_MODEL%
echo MBFORGE_EMBED_DEVICE=%EMBED_DEVICE%
echo.
echo # Rerank
echo MBFORGE_RERANK_MODEL=%RERANK_MODEL%
echo MBFORGE_RERANK_DEVICE=%RERANK_DEVICE%
echo.
echo # Model Cache Directories
echo HF_HOME=%HF_HOME%
echo MODELSCOPE_CACHE=%MODELSCOPE_CACHE%
echo TORCH_HOME=%TORCH_HOME%
echo OLLAMA_MODELS=%OLLAMA_MODELS%
) > .env
echo [OK] .env written

:: === 08 Verify ===
echo.
echo --- Verify ---
%PYTHON% -c "import torch; print(f'PyTorch OK, CUDA={torch.cuda.is_available()}')" 2>nul
if errorlevel 1 (echo [WARN] PyTorch) else (echo [OK] PyTorch)

%PYTHON% -c "import mbforge; print('mbforge OK')" 2>nul
if errorlevel 1 (echo [WARN] mbforge) else (echo [OK] mbforge)

echo.
echo ========================================
echo   Setup done! Run: uv run mbforge
echo ========================================

endlocal
