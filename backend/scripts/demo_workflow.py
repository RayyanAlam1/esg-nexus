"""Runs the demo workflow end-to-end against a running API (default http://localhost:8000).

    python scripts/demo_workflow.py [--base http://localhost:8000]

Login → dashboard → GHG trend → metric drill-down (calculation, evidence, framework mapping, quality,
governance) → standards gaps → materiality → evidence gaps → copilot → evaluation → report builder →
draft → validate → review/approve → final PDF. Prints one line per step; exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import sys

import httpx

ACCOUNTS = {
    "executive": ("cso@ecorp.local", "Exec!2024"),
    "manager": ("manager@ecorp.local", "Manager!2024"),
    "reviewer": ("reviewer@ecorp.local", "Review!2024"),
    "approver": ("approver@ecorp.local", "Approve!2024"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()
    api = args.base.rstrip("/") + "/api/v1"
    c = httpx.Client(timeout=120)
    tok = {}
    for role, (email, pw) in ACCOUNTS.items():
        r = c.post(f"{api}/auth/login", json={"email": email, "password": pw})
        r.raise_for_status()
        tok[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print(f"[ 1] login {role:9s} ok")

    def get(path, role="manager", **params):
        r = c.get(f"{api}{path}", headers=tok[role], params=params)
        r.raise_for_status()
        return r.json()

    def post(path, role="manager", json=None, **params):
        r = c.post(f"{api}{path}", headers=tok[role], json=json, params=params)
        return r

    ov = get("/esg/overview", "executive")
    print(f"[ 3] dashboard readiness {ov['readiness']['overall']}% · open issues {ov['issues']['total']} · KPIs {len(ov['kpis'])}")
    env = get("/esg/pillar/environment", kpi_only=True)
    print(f"[ 4] environment pillar: {len(env['topics'])} topics")
    hist = get("/metrics/ENV.GHG.SCOPE1/detail")
    print(f"[ 6] Scope 1 trend: {[(s['period'], s['value']) for s in hist['series'] if s['value'] is not None]}")
    d = get("/metrics/SOC.OHS.TRIR_CONTRACTOR/detail")
    print(f"[ 8] calculation: {d['calculation']['formula']} → {round(d['calculation']['result'], 4)} (reported {d['card']['value']})")
    print(f"[ 9] evidence: {[e['code'] for e in d['evidence']]}")
    print(f"[10] framework mapping: {[f['code'] for f in d['metric']['framework_requirements']]}")
    print(f"[11] data quality: {d['quality']['overall']} → {d['quality']['explanation'][:2]}")
    print(f"[12] governance: {[g['rule'] for g in d['governance']] or 'no rules triggered'}")
    cov = get("/frameworks/IFRS_S/coverage")
    print(f"[15] IFRS S1/S2 alignment {cov['alignment_pct']}% · missing {cov['missing']} · partial {cov['partial']}")
    gaps = [r["code"] for r in cov["requirements"] if r["status"] == "missing"]
    print(f"[16] gaps: {gaps[:6]}")
    mats = get("/materiality/assessments")
    mat = get(f"/materiality/assessments/{mats[0]['id']}")
    print(f"[18] materiality matrix: {len(mat['topics'])} topics, {len([t for t in mat['topics'] if t['is_material']])} material")
    eg = get("/evidence/gaps")
    print(f"[20] evidence coverage {eg['coverage_pct']}% ({eg['covered']}/{eg['required']})")
    ans = post("/copilot/ask", json={"question": "Why did our Scope 1 emissions increase in FY2023?"}).json()
    print(f"[23] copilot ({ans['status']}, confidence {ans['confidence']}): {ans['answer'][:160]}…")
    ev = get("/evaluations/summary")
    print(
        f"[25] evaluation: AI {ev['overall_scores']['ai_quality']} · data {ev['overall_scores']['data_quality']} · evidence {ev['overall_scores']['evidence_coverage']} · alignment {ev['overall_scores']['framework_alignment']}"
    )
    rep = post("/reports", json={"period_code": "FY2023", "template_code": "ESG_ANNUAL", "framework_codes": ["WEF_SCM", "UNGC", "UN_SDG"]}).json()
    rid = rep["id"]
    print(f"[28] report #{rid} created with {len(rep['sections'])} sections")
    draft = post(f"/reports/{rid}/generate-draft").json()
    print(f"[29] draft generated: {sum(1 for s in draft['sections'] if s['status'] == 'ai_generated')} AI sections")
    val = post(f"/reports/{rid}/validate").json()
    print(f"[31] validation: {[(x['check'], x['passed']) for x in val['checks']]}")
    for s in draft["sections"]:
        c.put(f"{api}/reports/{rid}/sections/{s['code']}", headers=tok["reviewer"], json={"state": "reviewed"})
        c.put(f"{api}/reports/{rid}/sections/{s['code']}", headers=tok["approver"], json={"state": "approved"})
    r = post(f"/reports/{rid}/transition", "approver", json={"state": "approved", "comment": "Demo approval"})
    if r.status_code != 200:
        print("[32] approval blocked:", r.json()["error"])
        return 1
    print("[32] report approved and locked")
    fin = post(f"/reports/{rid}/generate", "approver", format="pdf", final=True).json()
    print(f"[33] final PDF v{fin['version']} · {fin['size_bytes']} bytes · sha256 {fin['file_hash'][:12]}… → GET /api/v1/reports/versions/{fin['id']}/download")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPStatusError as exc:
        print("HTTP error:", exc.response.status_code, exc.response.text[:300])
        sys.exit(1)
