"""Zotero-MBForge 桥接服务.

提供本地 HTTP API，接收 Zotero 插件推送的文献条目、PDF 附件与批注，
导入到 MBForge 项目 Vault 中。
"""

from __future__ import annotations

__all__ = ["run_server"]
