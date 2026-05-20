"""Markdown 预览组件."""

from __future__ import annotations

from typing import Optional

import markdown
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget


class MarkdownPreview(QWebEngineView):
    """基于 QWebEngineView 的 Markdown 实时预览."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._md = markdown.Markdown(extensions=[
            "tables",
            "fenced_code",
            "toc",
            "nl2br",
        ])
        self.setStyleSheet("border: none;")
        settings = self.settings()
        if settings is not None:
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._base_html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
                line-height: 1.6;
                color: #d4d4d4;
                background: #1e1e1e;
                padding: 20px 40px;
                max-width: 900px;
                margin: 0 auto;
            }
            h1, h2, h3, h4, h5, h6 { color: #e2e2e2; margin-top: 24px; margin-bottom: 16px; }
            h1 { border-bottom: 1px solid #444; padding-bottom: 8px; }
            h2 { border-bottom: 1px solid #333; padding-bottom: 6px; }
            code {
                background: #2d2d2d;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 0.9em;
            }
            pre {
                background: #2d2d2d;
                padding: 12px;
                border-radius: 6px;
                overflow-x: auto;
            }
            pre code { background: none; padding: 0; }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 16px 0;
            }
            th, td {
                border: 1px solid #444;
                padding: 8px 12px;
                text-align: left;
            }
            th { background: #2d2d2d; }
            blockquote {
                border-left: 4px solid #094771;
                margin: 0;
                padding: 8px 16px;
                background: #252526;
            }
            a { color: #4fc1ff; }
            img { max-width: 100%; }
        </style>
        </head>
        <body>{content}</body>
        </html>
        """
        self.setHtml(self._base_html.format(content=""))

    def set_markdown(self, text: str):
        """设置 Markdown 文本并渲染."""
        self._md.reset()
        html = self._md.convert(text)
        full_html = self._base_html.format(content=html)
        self.setHtml(full_html)
