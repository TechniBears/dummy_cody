import pytest


def test_primary_is_opus_46_inference_profile(render_root_config):
    primary = render_root_config["agents"]["defaults"]["model"]["primary"]
    assert primary == "amazon-bedrock/us.anthropic.claude-opus-4-6-v1"


def test_amazon_bedrock_provider_declared(render_root_config):
    """Provider shape MUST match OpenClaw's runtime schema (regression for 2026-04-26 crash):
    baseUrl=string, api=bedrock-converse-stream, auth=string enum (NOT a dict),
    no 'region' key (region is derived from baseUrl).
    """
    providers = render_root_config["models"]["providers"]
    assert "amazon-bedrock" in providers
    bedrock = providers["amazon-bedrock"]
    assert isinstance(bedrock.get("baseUrl"), str) and bedrock["baseUrl"].startswith("https://"), \
        f"baseUrl must be an https:// URL, got {bedrock.get('baseUrl')!r}"
    assert "bedrock-runtime" in bedrock["baseUrl"], \
        f"baseUrl must point at bedrock-runtime, got {bedrock['baseUrl']!r}"
    assert bedrock.get("api") == "bedrock-converse-stream", \
        f"api must be 'bedrock-converse-stream', got {bedrock.get('api')!r}"
    assert bedrock.get("auth") in ("api-key", "aws-sdk", "oauth", "token"), \
        f"auth must be one of OpenClaw's allowed strings, got {bedrock.get('auth')!r}"
    assert "region" not in bedrock, \
        "'region' is not a valid OpenClaw bedrock provider key — derive it from baseUrl"


def test_all_model_aliases_declared(render_root_config):
    bedrock_models = render_root_config["models"]["providers"]["amazon-bedrock"]["models"]
    declared = {m["id"] for m in bedrock_models}
    expected = {
        "us.anthropic.claude-opus-4-6-v1",
        "us.anthropic.claude-opus-4-7",
        "us.anthropic.claude-sonnet-4-6",
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    }
    assert expected.issubset(declared)


def test_local_ollama_fallback_present(render_root_config):
    providers = render_root_config["models"]["providers"]
    assert "ollama" in providers
    ollama_models = {m["id"] for m in providers["ollama"]["models"]}
    assert "gemma3:4b" in ollama_models, "Smaller Gemma needed; 26B times out on g4dn.2xlarge"


def test_fallback_chain_uses_inference_profile_format(render_root_config):
    fallbacks = render_root_config["agents"]["defaults"]["model"]["fallbacks"]
    for fb in fallbacks:
        provider, _, model_id = fb.partition("/")
        if provider == "amazon-bedrock":
            assert model_id.startswith(("us.", "global.")), \
                f"Bedrock fallback {fb!r} must use inference-profile ID, not raw model ID"


def test_per_model_cache_retention_set_for_bedrock(render_root_config):
    defaults_models = render_root_config["agents"]["defaults"].get("models", {})
    assert defaults_models, "agents.defaults.models block missing"
    for ref, params in defaults_models.items():
        if ref.startswith("amazon-bedrock/"):
            assert params.get("params", {}).get("cacheRetention") in ("short", "long"), \
                f"{ref} missing cacheRetention"


def test_per_skill_models_emitted_as_agents_list(monkeypatch, tmp_path):
    """When a SKILL.md declares metadata.openclaw.model, renderer emits agents.list[]."""
    skills_dir = tmp_path / "skills" / "outlook-draft"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\n"
        "name: outlook-draft\n"
        "description: test skill\n"
        'metadata: {"openclaw":{"emoji":"📝","requires":{"bins":["outlook-draft"]},'
        '"model":"amazon-bedrock/us.anthropic.claude-opus-4-6-v1"}}\n'
        "---\n# body\n"
    )

    import render_root_openclaw_config as r
    monkeypatch.setattr(r, "SKILLS_ROOT", tmp_path / "skills")
    cfg = r.build_config()

    agents_list = cfg.get("agents", {}).get("list", [])
    by_id = {a.get("id"): a for a in agents_list}
    assert "outlook-draft" in by_id, "outlook-draft skill not present in agents.list"
    assert by_id["outlook-draft"]["model"]["primary"] == \
        "amazon-bedrock/us.anthropic.claude-opus-4-6-v1"


def test_skill_without_model_is_omitted_from_agents_list(monkeypatch, tmp_path):
    """A SKILL.md without metadata.openclaw.model produces no agents.list entry."""
    skills_dir = tmp_path / "skills" / "audio-transcribe"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\n"
        "name: audio-transcribe\n"
        "description: test skill\n"
        'metadata: {"openclaw":{"emoji":"🎙️","requires":{"bins":["whisper-ctranslate2"]}}}\n'
        "---\n# body\n"
    )

    import render_root_openclaw_config as r
    monkeypatch.setattr(r, "SKILLS_ROOT", tmp_path / "skills")
    cfg = r.build_config()

    agents_list = cfg.get("agents", {}).get("list", [])
    assert all(a.get("id") != "audio-transcribe" for a in agents_list)


def test_exec_security_is_full(render_root_config):
    """Exec policy uses security=full (no allowlist restrictions on test VM)."""
    exec_cfg = render_root_config["tools"]["exec"]
    assert exec_cfg["security"] == "full"
    assert exec_cfg["ask"] == "off"
    assert "safeBins" not in exec_cfg
    assert "safeBinProfiles" not in exec_cfg
