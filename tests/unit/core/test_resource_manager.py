"""Tests for resource catalog integrity verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

from mbforge.core.resource_manager import (
    RESOURCE_CATALOG,
    ResourceInfo,
    ResourceStatus,
    ResourceType,
    _check_model_file,
    _check_model_snapshot,
    _compute_sha256,
    _verify_model_path,
)


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_resource_info_has_checksum_fields() -> None:
    """ResourceInfo must carry sha256/expected_size defaults."""
    info = ResourceInfo(
        id="test",
        name="Test",
        type=ResourceType.MODEL,
        description="",
    )
    assert info.sha256 == ""
    assert info.expected_size == 0


def test_verify_model_path_file_matching(tmp_path: Path) -> None:
    data = b"hello molscribe"
    f = tmp_path / "model.pth"
    f.write_bytes(data)
    info = ResourceInfo(
        id="test",
        name="Test",
        type=ResourceType.MODEL,
        description="",
        sha256=_sha256_of_bytes(data),
        expected_size=len(data),
    )
    assert _verify_model_path(f, info) is True


def test_verify_model_path_file_hash_mismatch(tmp_path: Path) -> None:
    f = tmp_path / "model.pth"
    f.write_bytes(b"good data")
    info = ResourceInfo(
        id="test",
        name="Test",
        type=ResourceType.MODEL,
        description="",
        sha256="0" * 64,
        expected_size=f.stat().st_size,
    )
    assert _verify_model_path(f, info) is False


def test_verify_model_path_file_size_mismatch(tmp_path: Path) -> None:
    data = b"exact data"
    f = tmp_path / "model.pth"
    f.write_bytes(data)
    info = ResourceInfo(
        id="test",
        name="Test",
        type=ResourceType.MODEL,
        description="",
        expected_size=len(data) + 1,
    )
    assert _verify_model_path(f, info) is False


def test_verify_model_path_no_checksum_skips(tmp_path: Path) -> None:
    f = tmp_path / "model.pth"
    f.write_bytes(b"anything")
    info = ResourceInfo(
        id="test",
        name="Test",
        type=ResourceType.MODEL,
        description="",
    )
    assert _verify_model_path(f, info) is True


def test_verify_model_path_snapshot_single_file(tmp_path: Path) -> None:
    data = b"snapshot weights"
    dest = tmp_path / "MolScribe"
    dest.mkdir()
    weight = dest / "swin_base_char_aux_1m680k.pth"
    weight.write_bytes(data)
    info = ResourceInfo(
        id="molscribe",
        name="MolScribe",
        type=ResourceType.MODEL,
        description="",
        files=["swin_base_char_aux_1m680k.pth"],
        sha256=_sha256_of_bytes(data),
        expected_size=len(data),
    )
    assert _verify_model_path(dest, info) is True


def test_verify_model_path_snapshot_missing_file(tmp_path: Path) -> None:
    dest = tmp_path / "MolScribe"
    dest.mkdir()
    info = ResourceInfo(
        id="molscribe",
        name="MolScribe",
        type=ResourceType.MODEL,
        description="",
        files=["missing.pth"],
        sha256="0" * 64,
        expected_size=1,
    )
    assert _verify_model_path(dest, info) is False


def test_compute_sha256_matches_stdlib(tmp_path: Path) -> None:
    data = b"compute me"
    f = tmp_path / "x"
    f.write_bytes(data)
    assert _compute_sha256(f) == hashlib.sha256(data).hexdigest()


def test_check_model_file_flags_size_mismatch(tmp_path: Path) -> None:
    """_check_model_file should report PARTIAL when the found file size differs."""
    repo_dir = tmp_path / "MolScribe"
    repo_dir.mkdir()
    weight = repo_dir / "swin_base_char_aux_1m680k.pth"
    weight.write_bytes(b"short")
    info = RESOURCE_CATALOG["molscribe"]
    # Temporarily point the MBForge cache dir to our tmp_path via monkeypatching
    import mbforge.core.resource_manager as rm

    original_get_model_cache_dir = rm._get_model_cache_dir
    try:
        rm._get_model_cache_dir = lambda: tmp_path
        result = _check_model_file(info)
        assert result.status == ResourceStatus.PARTIAL, result
        assert "大小" in result.error or "size" in result.error.lower()
    finally:
        rm._get_model_cache_dir = original_get_model_cache_dir


def test_check_model_snapshot_flags_size_mismatch(tmp_path: Path) -> None:
    """_check_model_snapshot should report PARTIAL when directory size differs."""
    repo_dir = tmp_path / "MolScribe"
    repo_dir.mkdir()
    weight = repo_dir / "swin_base_char_aux_1m680k.pth"
    weight.write_bytes(b"short")
    info = RESOURCE_CATALOG["molscribe"]
    import mbforge.core.resource_manager as rm

    original_get_model_cache_dir = rm._get_model_cache_dir
    try:
        rm._get_model_cache_dir = lambda: tmp_path
        result = _check_model_snapshot(info)
        assert result.status == ResourceStatus.PARTIAL, result
        assert "大小" in result.error or "size" in result.error.lower()
    finally:
        rm._get_model_cache_dir = original_get_model_cache_dir


def test_molscribe_catalog_hash_present() -> None:
    """The MolScribe entry must have a non-empty SHA-256 and positive size."""
    info = RESOURCE_CATALOG["molscribe"]
    assert len(info.sha256) == 64
    assert info.expected_size > 0


def test_check_model_file_handles_none_info(tmp_path: Path) -> None:
    """_check_model_file must not crash when given a None ResourceInfo."""
    result = _check_model_file(None)  # type: ignore[arg-type]
    assert result.status == ResourceStatus.ERROR


def test_check_model_snapshot_handles_none_info(tmp_path: Path) -> None:
    """_check_model_snapshot must not crash when given a None ResourceInfo."""
    result = _check_model_snapshot(None)  # type: ignore[arg-type]
    assert result.status == ResourceStatus.ERROR


def test_verify_model_path_handles_none_info(tmp_path: Path) -> None:
    """_verify_model_path must return False when given a None ResourceInfo."""
    f = tmp_path / "x.pth"
    f.write_bytes(b"x")
    assert _verify_model_path(f, None) is False  # type: ignore[arg-type]
