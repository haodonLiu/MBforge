# MBForge Parser IO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `src/parser_io/` 模块，提供 UniParser 客户端封装和统一数据模型，支持探索 UniParser 返回格式。

**Architecture:** 采用轻量级设计，模块化分层：config（配置）→ models（数据模型）→ client（客户端封装）。配置从项目根目录 `.env` 加载，数据模型优先为后续 Agent 和 openSAR 模块提供稳定接口。

**Tech Stack:** Python 3.10+, python-dotenv, UniParser-Tools (本地依赖)

---

## 文件结构

```
MBForge/
  src/
    parser_io/
      __init__.py       # 模块入口，导出 ParserClient, ParseResult, MoleculeData, SARTask
      config.py         # 配置加载：ParserConfig dataclass + load_config()
      models.py         # 数据模型：ParseResult, MoleculeData, SARTask
      client.py         # UniParser 客户端封装：ParserClient
  openSAR/              # 子模块（不修改）
  UniParser-Tools/      # 子模块（通过 sys.path 引用）
  .env                  # 环境变量配置模板
  tests/
    parser_io/         # 单元测试
      __init__.py
      test_config.py
      test_models.py
      test_client.py
```

---

## Task 1: 创建目录结构和基础文件

**Files:**
- Create: `src/parser_io/__init__.py`
- Create: `tests/parser_io/__init__.py`

- [ ] **Step 1: 创建 src/parser_io/__init__.py**

```python
"""MBForge Parser IO 模块.

提供 UniParser 客户端封装和统一数据模型，用于集成 PDF 解析和 SAR 分析流水线。

示例:
    >>> from parser_io import ParserClient, ParserConfig, load_config
    >>> config = load_config()
    >>> client = ParserClient(config)
"""

from .config import ParserConfig, load_config, validate_config
from .models import ParseResult, MoleculeData, SARTask
from .client import ParserClient

__all__ = [
    "ParserConfig",
    "load_config",
    "validate_config",
    "ParseResult",
    "MoleculeData",
    "SARTask",
    "ParserClient",
]
```

- [ ] **Step 2: 创建 tests/parser_io/__init__.py**

```python
"""Parser IO 单元测试."""
```

- [ ] **Step 3: 提交**

```bash
git add src/parser_io/__init__.py tests/parser_io/__init__.py
git commit -m "feat(parser_io): create module structure"
```

---

## Task 2: 实现 config.py - 配置管理

**Files:**
- Create: `src/parser_io/config.py`
- Test: `tests/parser_io/test_config.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/parser_io/test_config.py
import pytest
from parser_io.config import ParserConfig, load_config, validate_config


def test_parser_config_dataclass():
    config = ParserConfig(host="https://example.com", api_key="test-key")
    assert config.host == "https://example.com"
    assert config.api_key == "test-key"


def test_validate_config_success():
    config = ParserConfig(host="https://example.com", api_key="test-key")
    assert validate_config(config) is True


def test_validate_config_empty_host():
    config = ParserConfig(host="", api_key="test-key")
    assert validate_config(config) is False


def test_validate_config_empty_api_key():
    config = ParserConfig(host="https://example.com", api_key="")
    assert validate_config(config) is False


def test_validate_config_missing_protocol():
    config = ParserConfig(host="example.com", api_key="test-key")
    assert validate_config(config) is False


def test_validate_config_no_scheme():
    """host 必须以 http:// 或 https:// 开头"""
    config = ParserConfig(host="example.com", api_key="test-key")
    assert validate_config(config) is False
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_config.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: 编写 config.py 实现**

```python
"""配置管理模块.

从项目根目录的 .env 文件加载 UniParser 配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


@dataclass
class ParserConfig:
    """UniParser 配置."""

    host: str
    api_key: str

    def __post_init__(self) -> None:
        """验证配置值."""
        if not self.host:
            raise ValueError("host cannot be empty")
        if not self.api_key:
            raise ValueError("api_key cannot be empty")


def find_env_file() -> Optional[Path]:
    """查找项目根目录的 .env 文件.

    从当前目录向上查找，直到找到 .env 文件或到达文件系统根目录。
    """
    current = Path.cwd()

    # 首先检查当前目录
    env_cwd = current / ".env"
    if env_cwd.exists():
        return env_cwd

    # 检查 MBForge 项目根目录（向上查找）
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return env_file

    return None


def load_config() -> ParserConfig:
    """从 .env 加载配置.

    查找流程:
    1. 如果 dotenv 可用，尝试加载 .env 文件
    2. 从环境变量读取 UNIPARSER_HOST 和 UNIPARSER_API_KEY

    Returns:
        ParserConfig 实例

    Raises:
        ValueError: 缺少必需的配置项
    """
    # 尝试加载 .env 文件
    env_file = find_env_file()
    if env_file and load_dotenv:
        load_dotenv(env_file)

    host = os.environ.get("UNIPARSER_HOST", "")
    api_key = os.environ.get("UNIPARSER_API_KEY", "")

    if not host:
        raise ValueError(
            "UNIPARSER_HOST is not set. "
            "Please set it in .env or environment variables."
        )
    if not api_key:
        raise ValueError(
            "UNIPARSER_API_KEY is not set. "
            "Please set it in .env or environment variables."
        )

    return ParserConfig(host=host, api_key=api_key)


def validate_config(config: ParserConfig) -> bool:
    """验证配置完整性.

    Args:
        config: ParserConfig 实例

    Returns:
        配置是否有效
    """
    if not config.host:
        return False
    if not config.host.startswith("http://") and not config.host.startswith("https://"):
        return False
    if not config.api_key:
        return False
    return True
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/parser_io/config.py tests/parser_io/test_config.py
git commit -m "feat(parser_io): add config module with ParserConfig and load_config"
```

---

## Task 3: 实现 models.py - 数据模型

**Files:**
- Create: `src/parser_io/models.py`
- Test: `tests/parser_io/test_models.py`

- [ ] **Step 1: 编写失败的测试**

```python
# tests/parser_io/test_models.py
import pytest
from dataclasses import asdict
from parser_io.models import ParseResult, MoleculeData, SARTask


def test_parse_result_creation():
    result = ParseResult(
        status="success",
        token="abc123",
        raw_data={"key": "value"},
    )
    assert result.status == "success"
    assert result.token == "abc123"
    assert result.raw_data == {"key": "value"}


def test_parse_result_to_dict():
    result = ParseResult(
        status="success",
        token="abc123",
        raw_data={"key": "value"},
    )
    d = asdict(result)
    assert d["status"] == "success"
    assert d["token"] == "abc123"


def test_molecule_data_creation():
    mol = MoleculeData(
        smiles="CCO",
        name="ethanol",
        activity=10.5,
        source="page 1",
    )
    assert mol.smiles == "CCO"
    assert mol.name == "ethanol"
    assert mol.activity == 10.5
    assert mol.source == "page 1"


def test_molecule_data_optional_activity():
    mol = MoleculeData(smiles="CCO", name="ethanol")
    assert mol.activity is None


def test_sar_task_creation():
    molecules = [
        MoleculeData(smiles="CCO", name="ethanol", activity=10.0),
        MoleculeData(smiles="CC", name="ethane", activity=20.0),
    ]
    task = SARTask(molecules=molecules, metadata={"source": "test.pdf"})
    assert len(task.molecules) == 2
    assert task.metadata["source"] == "test.pdf"


def test_sar_task_empty_molecules():
    task = SARTask(molecules=[], metadata={})
    assert len(task.molecules) == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_models.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: 编写 models.py 实现**

```python
"""数据模型定义.

定义 Parser IO 模块的核心数据类型，用于 UniParser 返回结果的
结构化表示，以及向 openSAR 传递的分子数据格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParseResult:
    """UniParser 返回的原始结果.

    Attributes:
        status: 解析状态，如 "success", "error"
        token: 解析任务的唯一标识符，用于获取结果
        raw_data: 原始返回数据，格式待探索（探索阶段保存为 JSON 分析）
    """

    status: str
    token: str
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MoleculeData:
    """提取的分子数据，供 openSAR 使用。

    Attributes:
        smiles: 分子的 SMILES 字符串
        name: 分子名称
        activity: 活性值（如 IC50），单位应为 nM
        source: 来源位置描述，如 "page 5, figure 3"
    """

    smiles: str
    name: str
    activity: Optional[float] = None
    source: str = ""


@dataclass
class SARTask:
    """SAR 分析任务.

    包含一组分子数据及其元信息，可直接传递给 openSAR 进行分析。

    Attributes:
        molecules: 分子数据列表
        metadata: 任务元信息，如来源文件、解析时间等
    """

    molecules: List[MoleculeData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_models.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/parser_io/models.py tests/parser_io/test_models.py
git commit -m "feat(parser_io): add data models (ParseResult, MoleculeData, SARTask)"
```

---

## Task 4: 实现 client.py - UniParser 客户端封装

**Files:**
- Create: `src/parser_io/client.py`
- Modify: `src/parser_io/__init__.py` (更新导出)
- Test: `tests/parser_io/test_client.py`

- [ ] **Step 1: 编写失败的测试（mock 模式）**

```python
# tests/parser_io/test_client.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from parser_io.client import ParserClient
from parser_io.config import ParserConfig
from parser_io.models import ParseResult


@pytest.fixture
def mock_config():
    return ParserConfig(host="https://uniparser.example.com", api_key="test-key")


@pytest.fixture
def mock_client(mock_config):
    return ParserClient(mock_config)


def test_parser_client_init(mock_config):
    client = ParserClient(mock_config)
    assert client.config.host == "https://uniparser.example.com"
    assert client.config.api_key == "test-key"


@patch("parser_io.client.UniParserClient")
def test_parse_pdf_calls_underlying_client(MockUniParser, mock_config):
    """验证 parse_pdf 调用底层 UniParserClient."""
    mock_instance = MockUniParser.return_value
    mock_instance.trigger_file.return_value = {
        "status": "success",
        "token": "test-token-123",
    }
    mock_instance.get_result.return_value = {
        "status": "success",
        "data": {"pages": []},
    }

    client = ParserClient(mock_config)
    result = client.parse_pdf("test.pdf")

    assert result.status == "success"
    assert result.token == "test-token-123"
    mock_instance.trigger_file.assert_called_once()


@patch("parser_io.client.UniParserClient")
def test_get_result_returns_raw_data(MockUniParser, mock_config):
    """验证 get_result 返回原始数据."""
    mock_instance = MockUniParser.return_value
    mock_instance.get_result.return_value = {
        "status": "success",
        "data": {"content": "test content"},
    }

    client = ParserClient(mock_config)
    raw = client.get_result("some-token")

    assert raw["status"] == "success"
    assert "data" in raw


@patch("parser_io.client.UniParserClient")
def test_parse_pdf_with_table_enabled(MockUniParser, mock_config):
    """验证 parse_pdf 启用 table 模式."""
    mock_instance = MockUniParser.return_value
    mock_instance.trigger_file.return_value = {"status": "success", "token": "token123"}

    client = ParserClient(mock_config)
    client.parse_pdf("document.pdf", table=True)

    call_kwargs = mock_instance.trigger_file.call_args[1]
    assert call_kwargs["table"] is True


@patch("parser_io.client.UniParserClient")
def test_parse_and_wait_sync_mode(MockUniParser, mock_config):
    """验证同步解析模式."""
    mock_instance = MockUniParser.return_value
    mock_instance.trigger_file.return_value = {"status": "success", "token": "sync-token"}
    mock_instance.get_result.return_value = {
        "status": "completed",
        "data": {"result": "done"},
    }

    client = ParserClient(mock_config)
    result = client.parse_and_wait("sync.pdf")

    assert result.token == "sync-token"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_client.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: 编写 client.py 实现**

```python
"""UniParser 客户端封装.

对 UniParser-Tools 的 UniParserClient 进行封装，提供简化的同步接口，
用于 PDF 解析和结果获取。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# 尝试从 UniParser-Tools 导入，如果不可用则提供 mock 或提示安装
try:
    from uniparser_tools.api.clients import UniParserClient as UniParserClientBase
    from uniparser_tools.common.constant import ParseMode, ParseModeTextual
    _UNIPARSER_AVAILABLE = True
except ImportError:
    UniParserClientBase = None  # type: ignore
    _UNIPARSER_AVAILABLE = False

from .config import ParserConfig
from .models import ParseResult


class ParserClient:
    """UniParser 客户端封装.

    提供简化的接口来解析 PDF 文件并获取结果。
    支持同步和异步两种模式。

    Attributes:
        config: ParserConfig 实例

    Example:
        >>> config = load_config()
        >>> client = ParserClient(config)
        >>> result = client.parse_pdf("document.pdf")
        >>> print(f"Token: {result.token}")
    """

    def __init__(self, config: ParserConfig):
        """初始化 ParserClient.

        Args:
            config: ParserConfig 实例

        Raises:
            ImportError: UniParser-Tools 未安装
        """
        self.config = config
        if not _UNIPARSER_AVAILABLE:
            raise ImportError(
                "UniParser-Tools is not installed. "
                "Please install it with: pip install uniparser-tools"
            )
        self._client = UniParserClientBase(
            host=config.host,
            api_key=config.api_key,
        )

    def parse_pdf(
        self,
        pdf_path: Union[str, Path],
        *,
        sync: bool = True,
        textual: Union[ParseModeTextual, bool] = ParseModeTextual.DigitalExported,
        table: Union[ParseMode, bool] = ParseMode.Disable,
        molecule: Union[ParseMode, bool] = ParseMode.Disable,
        figure: Union[ParseMode, bool] = ParseMode.Disable,
        **kwargs,
    ) -> ParseResult:
        """解析 PDF 文件.

        Args:
            pdf_path: PDF 文件路径
            sync: 是否同步等待解析完成，默认 True
            textual: 文本解析模式
            table: 表格解析模式
            molecule: 分子解析模式
            figure: 图表解析模式
            **kwargs: 其他参数传递给底层客户端

        Returns:
            ParseResult 对象，包含 status, token, raw_data
        """
        pdf_path = str(Path(pdf_path).resolve())

        response = self._client.trigger_file(
            file_path=pdf_path,
            sync=sync,
            textual=textual,
            table=table,
            molecule=molecule,
            figure=figure,
            **kwargs,
        )

        return ParseResult(
            status=response.get("status", "unknown"),
            token=response.get("token", ""),
            raw_data=response,
        )

    def get_result(
        self,
        token: str,
        *,
        content: bool = True,
        objects: bool = False,
        pages_dict: bool = False,
        pages_tree: bool = False,
        molecule_source: bool = False,
    ) -> Dict[str, Any]:
        """获取解析结果.

        Args:
            token: parse_pdf 返回的 token
            content: 是否返回文档文本内容
            objects: 是否返回语义对象列表
            pages_dict: 是否返回每页原始布局字典
            pages_tree: 是否返回嵌套树结构
            molecule_source: 是否包含分子 SMILES 源

        Returns:
            解析结果字典
        """
        return self._client.get_result(
            token=token,
            content=content,
            objects=objects,
            pages_dict=pages_dict,
            pages_tree=pages_tree,
            molecule_source=molecule_source,
        )

    def parse_and_wait(
        self,
        pdf_path: Union[str, Path],
        *,
        timeout: int = 300,
        poll_interval: int = 2,
        **kwargs,
    ) -> ParseResult:
        """同步解析 PDF，等待完成.

        发送解析请求后，轮询直到完成或超时。

        Args:
            pdf_path: PDF 文件路径
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
            **kwargs: 传递给 parse_pdf 的其他参数

        Returns:
            ParseResult 对象

        Raises:
            TimeoutError: 解析超时
        """
        import time

        result = self.parse_pdf(pdf_path, sync=False, **kwargs)

        elapsed = 0
        while elapsed < timeout:
            response = self._client.get_result(token=result.token, content=True)

            if response.get("status") == "completed":
                result.raw_data = response
                return result

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Parsing timed out after {timeout} seconds")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/test_client.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/parser_io/client.py src/parser_io/__init__.py tests/parser_io/test_client.py
git commit -m "feat(parser_io): add ParserClient with UniParser integration"
```

---

## Task 5: 创建 .env 模板

**Files:**
- Create: `.env.template`

- [ ] **Step 1: 创建 .env.template**

```env
# UniParser Configuration
UNIPARSER_HOST=https://your-uniparser-server.com
UNIPARSER_API_KEY=your-api-key-here
```

- [ ] **Step 2: 创建 .env 示例文件（不提交到 git）**

```env
# UniParser Configuration
UNIPARSER_HOST=https://uniparser.example.com
UNIPARSER_API_KEY=demo-key
```

- [ ] **Step 3: 添加 .env 到 .gitignore（如果不存在）**

```bash
echo ".env" >> .gitignore
```

- [ ] **Step 4: 提交**

```bash
git add .env.template .gitignore
git commit -m "feat: add .env.template for UniParser configuration"
```

---

## Task 6: 更新根目录 CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` - 添加 MBForge 项目概览和 parser_io 文档

- [ ] **Step 1: 更新 CLAUDE.md**

在文件开头部分添加 parser_io 模块的说明：

```markdown
## MBForge 项目概览

MBForge 是整合 UniParser-Tools 和 openSAR 的自动化 SAR 分析流水线项目。

### 模块结构

| 模块 | 用途 | 目录 |
|------|------|------|
| **parser_io** | PDF 解析 IO、配置管理、数据模型 | `src/parser_io/` |
| **openSAR** | SAR 分析工具箱 | `openSAR/` |
| **UniParser-Tools** | 文档解析 SDK | `UniParser-Tools/` |

### parser_io 模块

```bash
# 解析 PDF
cd MBForge
export UNIPARSER_HOST=https://your-server.com
export UNIPARSER_API_KEY=your-key
python -c "
from parser_io import ParserClient, load_config
config = load_config()
client = ParserClient(config)
result = client.parse_pdf('document.pdf')
print(f'Token: {result.token}')
raw = client.get_result(result.token)
print(f'Result: {raw}')
"
```

### 统一环境配置

项目使用 `.env` 文件管理配置：

```bash
# 复制模板
cp .env.template .env
# 编辑配置
vim .env
```
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with MBForge project overview"
```

---

## Task 7: 最终验证

- [ ] **Step 1: 运行所有测试**

Run: `cd C:/Users/10954/Desktop/MBForge && python -m pytest tests/parser_io/ -v`

- [ ] **Step 2: 验证模块可导入**

Run: `cd C:/Users/10954/Desktop/MBForge && python -c "from parser_io import ParserClient, ParseResult, MoleculeData, SARTask; print('Import OK')"`

- [ ] **Step 3: 检查文件结构**

Run: `find src/parser_io -name "*.py" | sort`

---

## 总结

实现完成后，项目结构如下：

```
MBForge/
  src/
    parser_io/
      __init__.py
      config.py
      models.py
      client.py
  tests/
    parser_io/
      __init__.py
      test_config.py
      test_models.py
      test_client.py
  .env.template
  .env
  CLAUDE.md
```

下一步：
1. 探索 UniParser 返回格式
2. 根据实际格式调整 models.py
3. 设计 Agent 模块

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-18-parser-io-implementation.md`.**
