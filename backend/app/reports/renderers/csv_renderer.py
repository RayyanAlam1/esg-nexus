from __future__ import annotations

import csv
import io


def render(payload: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "metric", "pillar", "unit", payload["period_code"], "prior", "status", "kind", "assurance", "evidence"])
    for r in payload["metric_rows"]:
        w.writerow([r["code"], r["name"], r["pillar"], r["unit"], r["value"], r["previous"], r["status"], r["kind"], r["assurance"], "|".join(r["evidence"])])
    return buf.getvalue().encode("utf-8-sig")
