"""Markdown 预览组件."""

from __future__ import annotations

from typing import Optional

import markdown
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
                font-size: 15px;
                line-height: 1.7;
                color: #212529;
                background: #ffffff;
                padding: 24px 40px;
                max-width: 900px;
                margin: 0 auto;
            }
            h1, h2, h3, h4, h5, h6 {
                color: #212529;
                margin-top: 28px;
                margin-bottom: 16px;
                font-weight: 600;
            }
            h1 { border-bottom: 2px solid #e9ecef; padding-bottom: 10px; font-size: 28px; }
            h2 { border-bottom: 1px solid #e9ecef; padding-bottom: 8px; font-size: 22px; }
            h3 { font-size: 18px; }
            code {
                background: #f1f3f5;
                padding: 3px 8px;
                border-radius: 6px;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 0.9em;
                color: #c2255c;
            }
            pre {
                background: #f8f9fa;
                padding: 16px;
                border-radius: 12px;
                overflow-x: auto;
                border: 1px solid #e9ecef;
            }
            pre code { background: none; padding: 0; color: #212529; }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 16px 0;
                border-radius: 10px;
                overflow: hidden;
                border: 1px solid #e9ecef;
            }
            th, td {
                border: 1px solid #e9ecef;
                padding: 10px 14px;
                text-align: left;
            }
            th { background: #f8f9fa; font-weight: 600; }
            tr:nth-child(even) { background: #f8f9fa; }
            blockquote {
                border-left: 4px solid #74c0fc;
                margin: 0;
                padding: 12px 20px;
                background: #f8f9fa;
                border-radius: 0 10px 10px 0;
            }
            a { color: #1971c2; text-decoration: none; }
            a:hover { text-decoration: underline; }
            img { max-width: 100%; border-radius: 10px; }
            hr { border: none; border-top: 1px solid #e9ecef; margin: 24px 0; }
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
