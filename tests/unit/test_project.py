"""测试项目管理模块."""

import tempfile
from pathlib import Path

import pytest

from mbforge.core.project import Project
from mbforge.core.settings import ProjectSettings


class TestProject:
    def test_create_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Project.create(Path(tmpdir), name="TestProject")
            assert project.name == "TestProject"
            assert (project.root / ".mbforge").exists()

    def test_open_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Project.create(Path(tmpdir), name="OpenTest")
            opened = Project.open(Path(tmpdir))
            assert opened is not None
            assert opened.name == "OpenTest"

    def test_scan_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Project.create(Path(tmpdir))
            # 创建测试文件
            (project.root / "test.md").write_text("# Hello")
            (project.root / "data.txt").write_text("data")
            entries = project.scan_files()
            assert len(entries) == 2
            assert any(e.path.name == "test.md" for e in entries)

    def test_settings_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Project.create(Path(tmpdir))
            project.settings.name = "Updated"
            project.save_settings()
            opened = Project.open(Path(tmpdir))
            assert opened.settings.name == "Updated"
