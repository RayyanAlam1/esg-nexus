"""API, RBAC, ingestion and end-to-end report workflow tests."""

import io


def test_health_and_openapi(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/ready").json()["seeded"] is True
    assert len(client.get("/api/v1/openapi.json").json()["paths"]) > 90


def test_auth_and_rbac(client, tokens):
    assert client.get("/api/v1/esg/overview").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "manager@ecorp.local", "password": "wrong"}).status_code == 401
    me = client.get("/api/v1/auth/me", headers=tokens["auditor"]).json()
    assert "audit.read" in me["capabilities"] and "data.write" not in me["capabilities"]
    assert client.get("/api/v1/admin/users", headers=tokens["analyst"]).status_code == 403
    assert client.get("/api/v1/admin/users", headers=tokens["admin"]).status_code == 200
    assert client.get("/api/v1/audit", headers=tokens["contributor"]).status_code == 403
    r = client.post(
        "/api/v1/governance/rules", json={"code": "GR-T1", "description": "t", "scope": "metric_value", "condition": "is_null", "action": "WARN"}, headers=tokens["manager"]
    )
    assert r.status_code == 403  # governance.manage is org_admin only


def test_executive_overview_answers_the_five_questions(client, tokens):
    body = client.get("/api/v1/esg/overview", headers=tokens["executive"]).json()
    assert body["period"]["code"] == "FY2023"
    rd = body["readiness"]
    assert 0 < rd["overall"] <= 100 and len(rd["components"]) == 7 and rd["explanation"]
    kpis = {k["code"]: k for k in body["kpis"]}
    assert kpis["ENV.GHG.SCOPE1_2_TOTAL"]["value"] == 7_396_238 and kpis["ENV.GHG.SCOPE1_2_TOTAL"]["yoy_pct"] > 7
    assert kpis["SOC.OHS.TRIR_CONTRACTOR"]["trend"] == "improving"
    assert "top" in body["issues"] and body["what_changed"]


def test_metric_detail_drilldown(client, tokens):
    d = client.get("/api/v1/metrics/SOC.OHS.TRIR_EMP/detail", headers=tokens["analyst"]).json()
    assert d["card"]["value"] == 0.09 and d["calculation"]["status"] == "ok" and round(d["calculation"]["result"], 4) == 0.0877
    assert d["evidence"] and d["evidence"][0]["printed_page"] == "67"
    assert d["quality"]["overall"] > 80 and d["lineage"]["nodes"] and d["series"]
    assert any(fr["framework"] == "WEF_SCM" for fr in d["metric"]["framework_requirements"])
    assert client.get("/api/v1/metrics/NOPE.X.Y/detail", headers=tokens["analyst"]).status_code == 404


def test_entity_scoped_contributor(client, tokens):
    r = client.get("/api/v1/metrics/ENV.GHG.SCOPE1/detail?entity=EPCL", headers=tokens["contributor"])
    assert r.status_code == 403  # contributor is scoped to EFERT
    assert client.get("/api/v1/metrics/ENV.GHG.SCOPE1/detail?entity=EFERT", headers=tokens["contributor"]).status_code == 200


def test_manual_value_guardrail_and_audit(client, tokens):
    r = client.post(
        "/api/v1/metrics/ENV.GHG.SCOPE1/values", json={"entity_code": "EFERT", "period_code": "FY2024", "value_numeric": -10, "reason": "test"}, headers=tokens["analyst"]
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "guardrail_rejected"
    r = client.post(
        "/api/v1/metrics/ENV.GHG.SCOPE1/values",
        json={"entity_code": "EFERT", "period_code": "FY2024", "value_numeric": 1_850_000, "reason": "FY2024 estimate", "is_estimate": True},
        headers=tokens["analyst"],
    )
    assert r.status_code == 200 and r.json()["status"] == "draft"
    audit = client.get("/api/v1/audit?object_id=ENV.GHG.SCOPE1/EFERT/FY2024", headers=tokens["auditor"]).json()
    assert audit["total"] >= 1 and audit["items"][0]["action"] == "data.modify"


def test_csv_ingestion_validates_rows(client, tokens):
    csv = b"metric_code,entity_code,period_code,value\nENV.WATER.WITHDRAWN,EPCL,FY2024,5000\nENV.WATER.WITHDRAWN,EPCL,FY2024,abc\nENV.NOPE,EPCL,FY2024,1\n"
    r = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("water.csv", io.BytesIO(csv), "text/csv")},
        data={"dataset_code": "DS-TEST-WATER", "source_code": "SRC-MANUAL"},
        headers=tokens["contributor"],
    )
    body = r.json()
    assert r.status_code == 200 and body["rows"] == 3 and body["valid_rows"] == 1 and body["loaded_values"] == 1
    r = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")},
        data={"dataset_code": "DS-X", "source_code": "SRC-MANUAL"},
        headers=tokens["contributor"],
    )
    assert r.json()["status"] == "rejected"
    recs = client.get(f"/api/v1/datasets/versions/{body['dataset_version_id']}/records?only_invalid=true", headers=tokens["analyst"]).json()
    assert recs["total"] == 2 and recs["items"][0]["issues"]


def test_frameworks_and_materiality_endpoints(client, tokens):
    cov = client.get("/api/v1/frameworks/WEF_SCM/coverage", headers=tokens["manager"]).json()
    assert cov["applicable"] == 21 and "not a compliance certification" in cov["disclaimer"]
    req = client.get("/api/v1/frameworks/requirements/WEF.PEOPLE.WAGE_LEVEL", headers=tokens["manager"]).json()
    assert any(m["omission_reason"] for m in req["mappings"])  # CEO pay ratio omission recorded
    mats = client.get("/api/v1/materiality/assessments", headers=tokens["manager"]).json()
    detail = client.get(f"/api/v1/materiality/assessments/{mats[0]['id']}", headers=tokens["manager"]).json()
    assert len([t for t in detail["topics"] if t["is_material"]]) == 10 and detail["stakeholder_inputs"]


def test_report_workflow_end_to_end(client, tokens):
    m, rv, ap = tokens["manager"], tokens["reviewer"], tokens["approver"]
    r = client.post("/api/v1/reports", json={"period_code": "FY2023", "template_code": "WEF_CORE", "framework_codes": ["WEF_SCM", "UNGC"]}, headers=m)
    assert r.status_code == 200
    rid = r.json()["id"]
    r = client.post(f"/api/v1/reports/{rid}/generate-draft", headers=m).json()
    assert r["status"] == "ai_generated" and all(s["status"] != "blocked" for s in r["sections"])
    v = client.post(f"/api/v1/reports/{rid}/validate", headers=m).json()
    assert len(v["checks"]) == 9 and v["blocked"] is True  # sections not yet approved → GR-022
    assert client.post(f"/api/v1/reports/{rid}/transition", json={"state": "approved"}, headers=ap).status_code == 422
    assert client.put(f"/api/v1/reports/{rid}/sections/cover", json={"state": "approved"}, headers=m).status_code == 403
    for s in r["sections"]:
        client.put(f"/api/v1/reports/{rid}/sections/{s['code']}", json={"state": "reviewed"}, headers=rv)
        assert client.put(f"/api/v1/reports/{rid}/sections/{s['code']}", json={"state": "approved"}, headers=ap).status_code == 200
    v = client.post(f"/api/v1/reports/{rid}/validate", headers=m).json()
    assert v["blocked"] is False, v["reason"]
    preview = client.get(f"/api/v1/reports/{rid}/preview", headers=m).json()
    assert preview["pages"][0]["title"] == "Cover" and len(preview["pages"]) > 10
    assert client.post(f"/api/v1/reports/{rid}/generate?format=pdf&final=true", headers=m).status_code == 403
    assert client.post(f"/api/v1/reports/{rid}/transition", json={"state": "approved"}, headers=ap).json()["locked"] is True
    for fmt in ("pdf", "docx", "xlsx", "csv"):
        out = client.post(f"/api/v1/reports/{rid}/generate?format={fmt}&final=true", headers=ap).json()
        assert out["is_final"] and out["size_bytes"] > 1000 and out["file_hash"]
        assert client.get(f"/api/v1/reports/versions/{out['id']}/download", headers=ap).status_code == 200
    # approved report freezes the period's data (GR-020)
    r = client.post("/api/v1/metrics/ENV.GHG.SCOPE1/values", json={"entity_code": "EFERT", "period_code": "FY2023", "value_numeric": 1}, headers=m)
    assert r.status_code == 422 and r.json()["error"]["code"] == "governance_blocked"
    assert client.post(f"/api/v1/reports/{rid}/transition", json={"state": "published"}, headers=ap).json()["status"] == "published"


def test_evaluation_centre_summary(client, tokens):
    s = client.get("/api/v1/evaluations/summary", headers=tokens["executive"]).json()
    assert s["ai_quality"]["evaluated_outputs"] > 0 and s["data_quality"]["overall"] > 80
    assert set(s["overall_scores"]) == {"ai_quality", "data_quality", "evidence_coverage", "framework_alignment", "report_readiness"}
