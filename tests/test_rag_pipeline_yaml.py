"""Behavior tests for the public API of rag_pipeline_yaml."""

from __future__ import annotations

import pytest

import rag_pipeline_yaml


def test_normalize_trims_and_lowercases() -> None:
    assert rag_pipeline_yaml.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        rag_pipeline_yaml.normalize(value)


def test_version_is_semver() -> None:
    parts = rag_pipeline_yaml.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
