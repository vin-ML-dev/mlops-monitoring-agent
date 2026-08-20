"""Offline validation of the Day-6 monitoring config (no cluster needed):
- every manifest is valid YAML with a kind
- the PrometheusRule has the expected alerts, each fully specified
- the Grafana dashboard JSON parses
- the Helm values have the settings that make our objects discoverable
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / "monitoring"

EXPECTED_ALERTS = {
    "GatewayDown",
    "ModelDown",
    "ModelDependencyUnhealthy",
    "HighBackendErrorRate",
    "HighLatencyDegraded",
    "PodRestartChurn",
    "AgentHeartbeatLost",
}


def test_all_manifests_are_valid_yaml_with_kind():
    # values-kind.yaml is a Helm VALUES file, not a k8s manifest -> no kind
    files = [f for f in sorted(MON.glob("*.yaml")) if f.name != "values-kind.yaml"]
    assert files, "no monitoring manifests found"
    for f in files:
        docs = [d for d in yaml.safe_load_all(f.read_text()) if d]
        assert docs, f"{f.name} is empty"
        for d in docs:
            assert d.get("kind"), f"{f.name} missing kind"


def test_values_file_is_valid_yaml():
    vals = yaml.safe_load((MON / "values-kind.yaml").read_text())
    assert isinstance(vals, dict) and "prometheus" in vals


def test_prometheus_rules_are_complete():
    rule_doc = yaml.safe_load((MON / "prometheus-rules.yaml").read_text())
    assert rule_doc["kind"] == "PrometheusRule"
    found = set()
    for group in rule_doc["spec"]["groups"]:
        assert group.get("name")
        for r in group["rules"]:
            found.add(r["alert"])
            assert r.get("expr"), f"{r['alert']} missing expr"
            assert "for" in r, f"{r['alert']} missing for"
            assert r["labels"].get("severity") in {"warning", "critical"}, r["alert"]
            assert r["annotations"].get("summary"), f"{r['alert']} missing summary"
            assert r["annotations"].get("description"), f"{r['alert']} missing description"
    assert found == EXPECTED_ALERTS, f"alert mismatch: {found ^ EXPECTED_ALERTS}"


def test_severity_split_exists():
    rule_doc = yaml.safe_load((MON / "prometheus-rules.yaml").read_text())
    sevs = {r["labels"]["severity"] for g in rule_doc["spec"]["groups"] for r in g["rules"]}
    assert "critical" in sevs and "warning" in sevs, "need both severities for routing"


def test_gateway_servicemonitor_targets_metrics_path():
    sm = yaml.safe_load((MON / "servicemonitor-gateway.yaml").read_text())
    assert sm["kind"] == "ServiceMonitor"
    ep = sm["spec"]["endpoints"][0]
    assert ep["path"] == "/metrics"
    assert ep["port"] == "http"
    assert sm["spec"]["selector"]["matchLabels"]["app"] == "fastapi-gateway"


def test_grafana_dashboard_json_parses():
    cm = yaml.safe_load((MON / "grafana-dashboard.yaml").read_text())
    assert cm["metadata"]["labels"]["grafana_dashboard"] == "1"
    dash = json.loads(cm["data"]["finbot.json"])
    assert dash["title"] and dash["panels"], "dashboard has no panels"


def test_values_make_our_objects_discoverable():
    vals = yaml.safe_load((MON / "values-kind.yaml").read_text())
    spec = vals["prometheus"]["prometheusSpec"]
    # these MUST be false or Prometheus ignores our ServiceMonitors/Rules
    assert spec["serviceMonitorSelectorNilUsesHelmValues"] is False
    assert spec["ruleSelectorNilUsesHelmValues"] is False


def test_alertmanager_routes_to_slack_via_secret_file():
    vals = yaml.safe_load((MON / "values-kind.yaml").read_text())
    am = vals["alertmanager"]
    assert "alertmanager-slack" in am["alertmanagerSpec"]["secrets"]
    receivers = am["config"]["receivers"]
    slack = [r for r in receivers if r.get("slack_configs")]
    assert slack, "no slack receiver configured"
    for r in slack:
        for sc in r["slack_configs"]:
            assert sc["api_url_file"].endswith("/webhook")  # webhook from the mounted secret
            assert sc["send_resolved"] is True, "should send resolved notifications"
