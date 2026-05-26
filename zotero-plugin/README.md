# MBForge Bridge for Zotero

将 Zotero 文献一键推送到 MBForge 进行分子知识库深度解析。

## 功能

- **右键推送**：在 Zotero 条目或分类上右键，选择「推送到 MBForge」
- **批量推送**：支持同时推送多个选中的条目，或整个分类下的所有文献
- **完整元数据**：自动携带标题、作者、摘要、DOI、标签
- **PDF 附件**：通过本地文件路径直接读取，无需大文件上传
- **阅读批注**：高亮、笔记、下划线等 annotations 一并同步
- **自动索引**：可选推送后立即调用 MBForge 解析管线进行索引
- **可配置**：支持自定义 MBForge 服务地址和端口

## 目录结构

```
zotero-plugin/
├── manifest.json          # Zotero 插件清单
├── bootstrap.js           # 插件主逻辑（菜单注册、推送、设置）
├── prefs.js               # 默认偏好设置
├── locale/
│   ├── en-US/
│   │   └── mbforge-bridge.ftl
│   └── zh-CN/
│       └── mbforge-bridge.ftl
└── README.md              # 本文件
```

## 安装方法

### 前提条件

1. 安装 [Zotero 7](https://www.zotero.org/download/) 或更高版本
2. 已安装并配置好 MBForge（本项目）

### 方式一：直接安装 XPI（推荐）

#### 第 1 步：打包插件

在项目根目录执行：

```bash
cd zotero-plugin
zip -r ../mbforge-bridge.xpi manifest.json bootstrap.js prefs.js locale/ README.md
```

#### 第 2 步：安装到 Zotero

1. 打开 Zotero
2. 点击菜单 **Tools → Add-ons**（工具 → 附加组件）
3. 点击右上角的齿轮图标 ⚙️，选择 **Install Add-on From File...**
4. 选择刚才生成的 `mbforge-bridge.xpi` 文件
5. 安装完成后重启 Zotero

### 方式二：加载源码（开发调试）

1. 关闭 Zotero
2. 找到 Zotero 的 Profile 目录：
   - Windows: `%APPDATA%\Zotero\Zotero\Profiles\xxxx.default\extensions\`
   - macOS: `~/Library/Application Support/Zotero/Profiles/xxxx.default/extensions/`
   - Linux: `~/.zotero/zotero/xxxx.default/extensions/`
3. 在该目录下新建一个文本文件，文件名为插件 ID：`mbforge-bridge@mbforge.org`
4. 文件内容写 `zotero-plugin` 文件夹的**绝对路径**，例如：
   ```
   C:\Users\10954\Desktop\MBForge\zotero-plugin
   ```
5. 保存文件，启动 Zotero
6. 插件会自动加载，修改源码后重启 Zotero 即可生效

## 使用方法

### 1. 启动 MBForge Bridge 服务

在终端中进入 MBForge 项目目录，执行：

```bash
# 方式 1：使用已有项目
uv run mbforge zotero-bridge --project ./my-project

# 方式 2：指定端口（默认 8233）
uv run mbforge zotero-bridge --project ./my-project --port 8233

# 方式 3：后台运行（Windows PowerShell）
Start-Process -WindowStyle Hidden -FilePath "uv" -ArgumentList "run","mbforge","zotero-bridge","--project","./my-project"
```

服务启动后会监听 `http://localhost:8233`。

### 2. 配置插件（可选）

如果 MBForge Bridge 服务不在本机默认端口，需要配置插件：

1. Zotero 菜单 → **Tools → MBForge Bridge 设置**
2. 修改服务地址和端口
3. 可选择「推送后自动解析索引」
4. 点击保存

### 3. 推送文献

**推送单个/多个条目：**
1. 在 Zotero 主列表中选中一个或多个文献条目（按住 Ctrl 或 Shift 多选）
2. 右键 → **推送到 MBForge**
3. 等待提示完成

**推送整个分类：**
1. 在左侧分类树中右键点击一个 Collection（分类）
2. 选择 **推送该分类到 MBForge**
3. 该分类下的所有条目会批量推送

### 4. 在 MBForge 中查看

推送完成后：
- PDF 文件保存在 `{项目}/zotero_imports/{zotero_key}_{filename}.pdf`
- 阅读批注保存在 `{项目}/.mbforge/zotero_annotations/{zotero_key}.json`
- 文献已自动加入项目索引
- 如果在设置中启用了「自动索引」，MBForge 会自动调用 PDFParserPipeline 解析

## 故障排除

| 问题 | 原因 | 解决 |
|------|------|------|
| 推送失败：请确认服务已启动 | MBForge Bridge 未运行 | 执行 `uv run mbforge zotero-bridge --project ./my-project` |
| 检测器不可用 | MolImagePipeline 模型未下载 | 下载 MolDetv2/MolScribe 模型到 `~/.cache/mbforge/models/` |
| 未找到 PDF 附件 | 条目只有元数据没有 PDF | 先通过 Zotero 的「Find Available PDF」获取附件 |
| 右键菜单不出现 | 插件未正确加载 | 检查 Add-ons 列表中 MBForge Bridge 是否启用 |

## 更新插件

重新执行打包命令生成新的 `.xpi` 文件，然后在 Zotero 的 Add-ons 管理中重新安装即可。

## 卸载

Zotero 菜单 → **Tools → Add-ons** → 找到 MBForge Bridge → 点击 **Remove**。
