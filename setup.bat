@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════╗
echo ║     MBForge 一键配置脚本（交互式）       ║
echo ╚══════════════════════════════════════════╝
echo.

set "PYTHON=.venv\Scripts\python.exe"

:: ═══════════════════════════════════════════
:: 1. 基础环境检查
:: ═══════════════════════════════════════════
echo ═══ 基础环境检查 ═══

where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] 未找到 uv，请先安装
    exit /b 1
)
for /f "tokens=*" %%i in ('uv --version') do echo [OK] %%i

if not exist ".venv" (
    echo [INFO] 创建虚拟环境 ...
    uv venv .venv --python 3.12
    echo [OK] 虚拟环境已创建
) else (
    echo [OK] 虚拟环境已存在
)

echo [INFO] 安装依赖 ...
uv sync --dev
echo [OK] 主依赖安装完成

%PYTHON% -c "import csar" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] 安装 openSAR ...
    uv pip install -e openSAR/ --python .venv\Scripts\python.exe
    echo [OK] csar 已安装
) else (
    echo [OK] csar 已存在
)

:: ═══════════════════════════════════════════
:: 2. UniParser 配置
:: ═══════════════════════════════════════════
echo.
echo ═══ UniParser 配置 ═══
set "UNIPARSER_HOST="
set "UNIPARSER_KEY="
set /p "configure_uniparser=是否配置 UniParser？[Y/n]: "
if /i "%configure_uniparser%"=="n" goto :skip_uniparser
set /p "UNIPARSER_HOST=UniParser 服务地址 [https://your-server.com]: "
if "%UNIPARSER_HOST%"=="" set "UNIPARSER_HOST=https://your-server.com"
set /p "UNIPARSER_KEY=UniParser API Key: "
echo [OK] UniParser 已配置: %UNIPARSER_HOST%
:skip_uniparser

:: ═══════════════════════════════════════════
:: 3. Ollama 检测
:: ═══════════════════════════════════════════
echo.
echo ═══ Ollama 检测 ═══
set "OLLAMA_AVAILABLE=0"
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
    set "OLLAMA_AVAILABLE=1"
    echo [OK] 检测到 Ollama
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if %ERRORLEVEL%==0 (
        echo [OK] Ollama 服务运行中
    ) else (
        echo [WARN] Ollama 已安装但服务未运行
    )
) else (
    echo [INFO] 未检测到 Ollama
)

:: ═══════════════════════════════════════════
:: 4. LLM 配置
:: ═══════════════════════════════════════════
echo.
echo ═══ LLM 配置 ═══
echo 选择 LLM 提供商:
echo   1) OpenAI 兼容 API
echo   2) Anthropic
if "%OLLAMA_AVAILABLE%"=="1" echo   3) Ollama（本地）
set /p "llm_choice=选择 [1]: "
if "%llm_choice%"=="" set "llm_choice=1"

set "LLM_PROVIDER=openai_compatible"
set "LLM_BASE_URL=https://api.siliconflow.cn/v1"
set "LLM_API_KEY="
set "LLM_MODEL=Qwen/Qwen2.5-7B-Instruct"

if "%llm_choice%"=="1" goto :llm_openai
if "%llm_choice%"=="2" goto :llm_anthropic
if "%llm_choice%"=="3" goto :llm_ollama
goto :llm_done

:llm_openai
set "LLM_PROVIDER=openai_compatible"
set /p "LLM_BASE_URL=API Base URL [!LLM_BASE_URL!]: "
if "!LLM_BASE_URL!"=="" set "LLM_BASE_URL=https://api.siliconflow.cn/v1"
set /p "LLM_API_KEY=API Key: "
set /p "LLM_MODEL=模型名称 [!LLM_MODEL!]: "
if "!LLM_MODEL!"=="" set "LLM_MODEL=Qwen/Qwen2.5-7B-Instruct"
goto :llm_done

:llm_anthropic
set "LLM_PROVIDER=anthropic"
set "LLM_BASE_URL=https://api.minimaxi.com/anthropic"
set /p "LLM_BASE_URL=API Base URL [!LLM_BASE_URL!]: "
if "!LLM_BASE_URL!"=="" set "LLM_BASE_URL=https://api.minimaxi.com/anthropic"
set /p "LLM_API_KEY=API Key: "
set "LLM_MODEL=MiniMax-M2.7"
set /p "LLM_MODEL=模型名称 [!LLM_MODEL!]: "
if "!LLM_MODEL!"=="" set "LLM_MODEL=MiniMax-M2.7"
goto :llm_done

:llm_ollama
set "LLM_PROVIDER=ollama"
set "LLM_BASE_URL=http://localhost:11434/v1"
set "LLM_API_KEY=ollama"
set "LLM_MODEL=qwen2.5:7b"
set /p "LLM_MODEL=模型名称 [!LLM_MODEL!]: "
if "!LLM_MODEL!"=="" set "LLM_MODEL=qwen2.5:7b"
goto :llm_done

:llm_done
echo [OK] LLM: %LLM_PROVIDER% / %LLM_MODEL%

:: ═══════════════════════════════════════════
:: 5. Embedding / Rerank 配置
:: ═══════════════════════════════════════════
echo.
echo ═══ Embedding / Rerank 配置 ═══

set "EMBED_MODEL=BAAI/bge-small-zh-v1.5"
set "EMBED_DEVICE=cpu"
set "RERANK_MODEL=BAAI/bge-reranker-base"
set "RERANK_DEVICE=cpu"

echo Embedding 模型:
echo   1) BAAI/bge-small-zh-v1.5（轻量）
echo   2) BAAI/bge-large-zh-v1.5（高精度）
echo   3) Qwen/Qwen3-Embedding-0.6B（推荐）
set /p "embed_choice=选择 [1]: "
if "%embed_choice%"=="" set "embed_choice=1"
if "%embed_choice%"=="2" set "EMBED_MODEL=BAAI/bge-large-zh-v1.5"
if "%embed_choice%"=="3" set "EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B"

echo Rerank 模型:
echo   1) BAAI/bge-reranker-base（默认）
echo   2) BAAI/bge-reranker-v2-m3（多语言）
echo   3) Qwen/Qwen3-Reranker-0.6B（推荐）
set /p "rerank_choice=选择 [1]: "
if "%rerank_choice%"=="" set "rerank_choice=1"
if "%rerank_choice%"=="2" set "RERANK_MODEL=BAAI/bge-reranker-v2-m3"
if "%rerank_choice%"=="3" set "RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B"

echo [OK] Embedding: %EMBED_MODEL%
echo [OK] Rerank: %RERANK_MODEL%

:: ═══════════════════════════════════════════
:: 6. 写入 .env
:: ═══════════════════════════════════════════
echo.
echo ═══ 写入配置文件 ═══

if exist ".env" (
    set /p "overwrite=.env 已存在，是否覆盖？[y/N]: "
    if /i not "!overwrite!"=="y" (
        echo [INFO] 保留现有 .env
        goto :env_done
    )
    copy .env .env.bak >nul
    echo [OK] 已备份 .env → .env.bak
)

(
echo # UniParser Configuration
echo UNIPARSER_HOST=%UNIPARSER_HOST%
echo UNIPARSER_API_KEY=%UNIPARSER_KEY%
echo.
echo # ---------- LLM ----------
echo MBFORGE_LLM_PROVIDER=%LLM_PROVIDER%
echo MBFORGE_LLM_BASE_URL=%LLM_BASE_URL%
echo MBFORGE_LLM_API_KEY=%LLM_API_KEY%
echo MBFORGE_LLM_MODEL=%LLM_MODEL%
echo MBFORGE_LLM_MAX_TOKENS=4096
echo MBFORGE_LLM_TEMPERATURE=0.7
echo MBFORGE_LLM_TOP_P=0.9
echo.
echo # ---------- Embedding ----------
echo MBFORGE_EMBED_PROVIDER=sentence_transformers
echo MBFORGE_EMBED_MODEL=%EMBED_MODEL%
echo MBFORGE_EMBED_DEVICE=%EMBED_DEVICE%
echo.
echo # ---------- Rerank ----------
echo MBFORGE_RERANK_MODEL=%RERANK_MODEL%
echo MBFORGE_RERANK_DEVICE=%RERANK_DEVICE%
echo.
echo # ---------- UV Mirror ----------
echo UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
echo UV_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
) > .env
echo [OK] .env 已写入

:env_done

:: ═══════════════════════════════════════════
:: 7. 验证
:: ═══════════════════════════════════════════
echo.
echo ═══ 验证安装 ═══

%PYTHON% -c "import torch; print(f'PyTorch {torch.__version__}, CUDA={torch.cuda.is_available()}')" 2>nul && echo [OK] PyTorch OK || echo [WARN] PyTorch 异常
%PYTHON% -c "import lxml.etree; print(f'lxml {lxml.etree.__version__}')" 2>nul && echo [OK] lxml OK || echo [WARN] lxml 异常
%PYTHON% -c "import csar; print(f'csar {csar.__version__}')" 2>nul && echo [OK] csar OK || echo [WARN] csar 异常
%PYTHON% -c "import mbforge; print(f'mbforge {mbforge.__version__}')" 2>nul && echo [OK] mbforge OK || echo [WARN] mbforge 异常

echo.
echo ╔══════════════════════════════════════════╗
echo ║  配置完成! 运行 uv run mbforge 启动应用  ║
echo ╚══════════════════════════════════════════╝

endlocal
