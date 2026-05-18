# MBForge Parser IO 设计文档

## 概述

本文档描述 MBForge 项目中 Parser IO 模块的设计，用于集成 UniParser-Tools 和 openSAR，构成自动化 SAR 分析流水线。

## 目标

1. 统一项目文件架构
2. 构建 Parser IO 模块，提供统一的数据模型和客户端封装
3. 支持探索 UniParser 返回格式

## 架构决策

### 目录结构

采用"统一 src 目录"结构：

```
MBForge/
  src/
    parser_io/           # Parser IO 模块（新增）
      __init__.py
      models.py          # 数据模型
      client.py          # UniParser 客户端封装
      config.py          # 配置加载
  openSAR/               # 子模块
  UniParser-Tools/       # 子模块
  .env                   # 统一配置
```

### 设计原则

- **轻量级**：探索阶段避免过度设计
- **数据模型优先**：先定义清晰的数据结构，让后续模块有稳定接口
- **配置集中**：所有配置通过 .env 统一管理

## 模块设计

### 1. config.py - 配置管理

从项目根目录的 `.env` 文件加载配置。

**环境变量：**
```env
# UniParser 配置
UNIPARSER_HOST=https://your-uniparser-server.com
UNIPARSER_API_KEY=your-api-key
```

**接口：**
```python
@dataclass
class ParserConfig:
    host: str
    api_key: str

def load_config() -> ParserConfig:
    """从 .env 加载配置"""
    ...

def validate_config(config: ParserConfig) -> bool:
    """验证配置完整性"""
    ...
```

### 2. models.py - 数据模型

定义 Parser IO 的核心数据类型。

**类层次：**
```
ParseResult          # Parser 返回的原始结果
    └── status: str
    └── token: str
    └── raw_data: dict

MoleculeData         # 提取的分子数据（供 openSAR 使用）
    └── smiles: str
    └── name: str
    └── activity: Optional[float]
    └── source: str

SARTask              # SAR 分析任务
    └── molecules: List[MoleculeData]
    └── metadata: dict
```

### 3. client.py - UniParser 客户端封装

封装 UniParser-Tools 的 `UniParserClient`，提供简化的接口。

**接口：**
```python
class ParserClient:
    def __init__(self, config: ParserConfig)
    def parse_pdf(self, pdf_path: str, **kwargs) -> ParseResult:
        """解析 PDF 文件"""

    def get_result(self, token: str, **kwargs) -> dict:
        """获取解析结果"""

    def parse_and_wait(self, pdf_path: str, timeout: int = 300) -> ParseResult:
        """同步解析，等待完成"""
```

## 数据流

```
PDF 文件
    ↓
ParserClient.parse_pdf()
    ↓
UniParser 服务（外部）
    ↓
ParseResult (token + raw_data)
    ↓
[探索阶段] 保存 raw_data 到 JSON，分析格式
    ↓
[后续阶段] Agent 提取 MoleculeData
    ↓
SARTask
    ↓
openSAR 处理
```

## 文件清单

| 文件 | 用途 |
|------|------|
| `src/parser_io/__init__.py` | 模块入口，导出主要接口 |
| `src/parser_io/config.py` | 配置加载和验证 |
| `src/parser_io/models.py` | 数据模型定义 |
| `src/parser_io/client.py` | UniParser 客户端封装 |
| `.env` | 环境变量配置 |

## 实现顺序

1. 创建 `src/parser_io/` 目录结构
2. 实现 `config.py` - 配置加载
3. 实现 `models.py` - 数据模型（初始版本）
4. 实现 `client.py` - 客户端封装
5. 创建 `.env` 模板
6. 编写基础测试

## 后续步骤

- 探索 UniParser 返回的 `raw_data` 格式
- 根据实际格式调整 `models.py`
- 设计 Agent 模块（提取 MoleculeData）
- 集成 openSAR

## 状态

- [x] 设计完成
- [ ] 实现 config.py
- [ ] 实现 models.py
- [ ] 实现 client.py
- [ ] 创建 .env 模板
- [ ] 单元测试
