"""Zotero Bridge 数据模型."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AttachmentInfo(BaseModel):
    """Zotero PDF 附件信息."""

    id: str = Field(description="附件在 Zotero 中的 key")
    filename: str = Field(description="文件名")
    path: str = Field(description="本地绝对路径")
    contentType: str = Field(default="application/pdf")


class AnnotationInfo(BaseModel):
    """Zotero 阅读批注信息."""

    attachmentKey: str = Field(description="所属附件的 key")
    type: str = Field(description="highlight / note / underline / image")
    page: str = Field(default="", description="页码标签")
    text: str = Field(default="", description="批注选中的文本")
    comment: str = Field(default="", description="批注评论")
    color: str = Field(default="", description="颜色")
    position: Optional[dict[str, Any]] = Field(default=None, description="位置信息")


class ZoteroItem(BaseModel):
    """Zotero 文献条目推送数据."""

    key: str = Field(description="条目在 Zotero 中的 key")
    libraryID: Optional[int] = Field(default=None)
    title: str = Field(default="")
    authors: str = Field(default="")
    abstract: str = Field(default="")
    url: str = Field(default="")
    doi: str = Field(default="")
    date: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    annotations: list[AnnotationInfo] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """批量导入请求体."""

    items: list[ZoteroItem] = Field(default_factory=list)
    auto_index: bool = Field(
        default=False,
        description="是否立即调用 PDFParserPipeline 进行解析和索引（可能较慢）",
    )


class ImportResult(BaseModel):
    """单个条目的导入结果."""

    zotero_key: str
    status: str = Field(description="imported / skipped / error")
    doc_id: Optional[str] = Field(default=None)
    path: Optional[str] = Field(default=None)
    message: Optional[str] = Field(default=None)


class ImportResponse(BaseModel):
    """批量导入响应体."""

    imported: int = 0
    failed: int = 0
    results: list[ImportResult] = Field(default_factory=list)
