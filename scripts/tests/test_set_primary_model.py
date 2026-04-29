import json

import pytest


def test_alias_resolution_resolves_known_alias():
    from set_primary_model import resolve_alias

    assert resolve_alias("opus") == "amazon-bedrock/us.anthropic.claude-opus-4-6-v1"
    assert resolve_alias("sonnet-1m") == "amazon-bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert resolve_alias("gemma") == "ollama/gemma3:4b"


def test_alias_resolution_passes_through_full_id():
    from set_primary_model import resolve_alias

    full = "amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert resolve_alias(full) == full


def test_alias_resolution_rejects_unknown():
    from set_primary_model import resolve_alias

    with pytest.raises(ValueError, match="unknown model"):
        resolve_alias("gpt-4o")


def test_set_primary_writes_atomic(tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "ollama/gemma3:4b", "fallbacks": []}}},
    }))
    from set_primary_model import set_primary_model

    result = set_primary_model("opus", config_path=cfg_path, dry_run=False, restart=False)

    assert result["primary"] == "amazon-bedrock/us.anthropic.claude-opus-4-6-v1"
    written = json.loads(cfg_path.read_text())
    assert written["agents"]["defaults"]["model"]["primary"] == result["primary"]
    assert not list(tmp_path.glob("*.tmp"))


def test_set_primary_dry_run_does_not_write(tmp_path):
    cfg_path = tmp_path / "openclaw.json"
    original = {"agents": {"defaults": {"model": {"primary": "ollama/gemma3:4b", "fallbacks": []}}}}
    cfg_path.write_text(json.dumps(original))
    from set_primary_model import set_primary_model

    result = set_primary_model("opus", config_path=cfg_path, dry_run=True, restart=False)

    assert result["primary"] == "amazon-bedrock/us.anthropic.claude-opus-4-6-v1"
    assert json.loads(cfg_path.read_text()) == original


def test_set_primary_preserves_file_mode(tmp_path):
    """Atomic write must preserve mode of the existing file.

    Regression: 2026-04-25 the bot crashed in a 5106-restart loop because
    tempfile.mkstemp created the new file 0600 and os.replace kept it that
    way. With openclaw service running as user openclaw, the config became
    unreadable and validate-openclaw-config crashed every startup.
    """
    import os

    cfg_path = tmp_path / "openclaw.json"
    cfg_path.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "ollama/gemma3:4b", "fallbacks": []}}},
    }))
    os.chmod(cfg_path, 0o644)
    expected_mode = cfg_path.stat().st_mode & 0o777

    from set_primary_model import set_primary_model
    set_primary_model("opus", config_path=cfg_path, dry_run=False, restart=False)

    assert (cfg_path.stat().st_mode & 0o777) == expected_mode, \
        f"mode should remain {oct(expected_mode)}, got {oct(cfg_path.stat().st_mode & 0o777)}"
