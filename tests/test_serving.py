"""Tests for the Day 4 serving layer that don't need a cluster or a model:
config loading, the OpenAI payload builder, and that every k8s manifest is valid
YAML with the fields we depend on.
"""

from __future__ import annotations

import yaml

from src.serving import ROOT, load_serve_cfg
from src.serving.payload import build_chat_payload

CFG = load_serve_cfg()
DEPLOY = ROOT / "deploy"


# ---------------- config ----------------
def test_serve_config_has_required_fields():
    assert CFG["model"]["gguf_repo"].startswith("vinmlops/")
    assert CFG["model"]["gguf_file"].endswith(".gguf")
    assert CFG["server"]["port"] == 8080
    assert 0 < CFG["decoding"]["temperature"] <= 1


# ---------------- payload builder ----------------
def test_payload_includes_system_and_user():
    p = build_chat_payload("What is an ETF?", CFG)
    roles = [m["role"] for m in p["messages"]]
    assert roles == ["system", "user"]
    assert p["messages"][-1]["content"] == "What is an ETF?"


def test_payload_defaults_come_from_config():
    p = build_chat_payload("hi", CFG)
    assert p["temperature"] == CFG["decoding"]["temperature"]
    assert p["max_tokens"] == CFG["decoding"]["max_tokens"]


def test_payload_overrides_win():
    p = build_chat_payload("hi", CFG, temperature=0.9, max_tokens=10)
    assert p["temperature"] == 0.9
    assert p["max_tokens"] == 10


def test_payload_can_drop_system_prompt():
    p = build_chat_payload("hi", CFG, system_prompt="")
    assert [m["role"] for m in p["messages"]] == ["user"]


# ---------------- kubernetes manifests are valid YAML ----------------
def test_all_manifests_are_valid_yaml():
    files = sorted(DEPLOY.glob("*.yaml"))
    assert files, "no manifests found"
    for f in files:
        docs = list(yaml.safe_load_all(f.read_text()))
        assert docs and all(d.get("kind") for d in docs if d), f"{f.name} missing kind"


def test_deployment_wires_config_secret_and_probes():
    dep = yaml.safe_load((DEPLOY / "deployment.yaml").read_text())
    container = dep["spec"]["template"]["spec"]["containers"][0]
    # pulls non-secret settings from the ConfigMap
    assert container["envFrom"][0]["configMapRef"]["name"] == "finbot-serve-config"
    # pulls HF_TOKEN from the Secret
    assert any(e.get("name") == "HF_TOKEN" for e in container["env"])
    # has all three probe types (startup for the slow model load)
    assert "startupProbe" in container
    assert "readinessProbe" in container
    assert "livenessProbe" in container


def test_service_is_clusterip_named_for_the_diagram():
    svc = yaml.safe_load((DEPLOY / "service.yaml").read_text())
    assert svc["metadata"]["name"] == "llama-cpp-svc"  # other components address this name
    assert svc["spec"]["type"] == "ClusterIP"
    assert svc["spec"]["ports"][0]["port"] == 8080


def test_entrypoint_enables_prometheus_metrics():
    text = (ROOT / "serving" / "entrypoint.sh").read_text()
    assert "--metrics" in text  # Day 6 Prometheus scrapes /metrics from the model


def test_configmap_matches_serve_yaml_model():
    cm = yaml.safe_load((DEPLOY / "configmap.yaml").read_text())
    assert cm["data"]["GGUF_REPO"] == CFG["model"]["gguf_repo"]
    assert cm["data"]["GGUF_FILE"] == CFG["model"]["gguf_file"]
