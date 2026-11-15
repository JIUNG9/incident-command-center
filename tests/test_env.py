"""VIGIL_* env lookup with the deprecated TEAMMATE_* fallback."""

from __future__ import annotations

import warnings

import pytest

from vigil import env
from vigil.config import load_config
from vigil.indexer.main import Indexer


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("VIGIL_TOP_K", "TEAMMATE_TOP_K", "VIGIL_LLM_MODEL", "TEAMMATE_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_new_name_is_read_without_warning(monkeypatch):
    monkeypatch.setenv("VIGIL_TOP_K", "9")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert env.get("TOP_K", "6") == "9"


def test_old_name_still_works_and_warns(monkeypatch):
    monkeypatch.setenv("TEAMMATE_TOP_K", "7")
    with pytest.warns(DeprecationWarning, match="set VIGIL_TOP_K instead"):
        assert env.get("TOP_K", "6") == "7"


def test_new_name_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("VIGIL_TOP_K", "9")
    monkeypatch.setenv("TEAMMATE_TOP_K", "7")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert env.get("TOP_K") == "9"


def test_default_when_neither_is_set():
    assert env.get("TOP_K", "6") == "6"
    assert env.get("TOP_K") is None


def test_empty_new_value_does_not_fall_back_to_old(monkeypatch):
    # An empty VIGIL_ value is a deliberate "unset it", not a request for the old name.
    monkeypatch.setenv("VIGIL_TOP_K", "")
    monkeypatch.setenv("TEAMMATE_TOP_K", "7")
    assert env.get("TOP_K", "6") == ""


def test_config_override_reads_old_llm_name_and_warns(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAMMATE_LLM_MODEL", "legacy-model")
    with pytest.warns(DeprecationWarning, match="VIGIL_LLM_MODEL"):
        cfg = load_config(tmp_path)
    assert cfg.llm.model == "legacy-model"


def test_indexer_reads_old_chunk_size(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAMMATE_CHUNK_SIZE", "123")
    with pytest.warns(DeprecationWarning, match="VIGIL_CHUNK_SIZE"):
        idx = Indexer(brain_root=tmp_path)
    assert idx.chunk_size == 123
