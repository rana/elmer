"""Tests for doc-only project detection (ADR-056)."""

import os
from pathlib import Path

import pytest

from elmer.invariants import is_doc_only_project


class TestIsDocOnlyProject:
    """Tests for is_doc_only_project()."""

    def test_empty_dir_is_doc_only(self, tmp_path):
        assert is_doc_only_project(tmp_path) is True

    def test_markdown_only_is_doc_only(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "CLAUDE.md").write_text("# Instructions")
        assert is_doc_only_project(tmp_path) is True

    def test_package_json_is_not_doc_only(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        assert is_doc_only_project(tmp_path) is False

    def test_pyproject_toml_is_not_doc_only(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert is_doc_only_project(tmp_path) is False

    def test_makefile_is_not_doc_only(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:")
        assert is_doc_only_project(tmp_path) is False

    def test_cargo_toml_is_not_doc_only(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert is_doc_only_project(tmp_path) is False

    def test_go_mod_is_not_doc_only(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        assert is_doc_only_project(tmp_path) is False

    def test_dockerfile_is_not_doc_only(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        assert is_doc_only_project(tmp_path) is False
