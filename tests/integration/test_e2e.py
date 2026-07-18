from __future__ import annotations


def test_end_to_end_eval(client):
    r = client.post("/v1/datasets", json={"name": "qa", "dataset_id": "qa-golden"})
    assert r.status_code == 200, r.text
    body = r.json()
    ds_id, version = body["dataset_id"], body["version"]

    r = client.post(
        f"/v1/datasets/{ds_id}/cases?version={version}",
        json={"inputs": {"query": "hello"}, "expected": {"answer": "hello"}},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/v1/runs",
        json={
            "dataset_id": ds_id,
            "dataset_version": version,
            "agent": {"agent_id": "cs", "tenant_id": "t"},
            "scorer_set": ["promptfoo_accuracy"],
        },
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "done"
    run_id = run["run_id"]

    r = client.get(f"/v1/runs/{run_id}/report")
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["metrics_summary"]["accuracy"] == 1.0
    report_id = report["report_id"]

    r = client.get(f"/v1/reports/{report_id}?baseline=ignored")
    assert r.status_code == 200
    assert r.json()["report_id"] == report_id

    r = client.get(f"/v1/reports/{report_id}/export?fmt=md")
    assert r.status_code == 200
    assert "Eval Report" in r.json()["markdown"]


def test_unknown_scorer_rejected(client):
    r = client.post("/v1/datasets", json={"name": "qa", "dataset_id": "x"})
    assert r.status_code == 200
    ds_id, version = r.json()["dataset_id"], r.json()["version"]
    # Add a case so the scoring stage actually runs and resolves the scorer.
    r = client.post(
        f"/v1/datasets/{ds_id}/cases?version={version}",
        json={"inputs": {"query": "hi"}},
    )
    assert r.status_code == 200
    r = client.post(
        "/v1/runs",
        json={
            "dataset_id": ds_id,
            "dataset_version": version,
            "agent": {"agent_id": "cs", "tenant_id": "t"},
            "scorer_set": ["does_not_exist"],
        },
    )
    # Scorer lookup fails -> 400.
    assert r.status_code == 400, r.text
