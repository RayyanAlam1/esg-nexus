"""Report templates are YAML configuration: add a file here to add a template."""

from __future__ import annotations

from pathlib import Path

import yaml

TEMPLATE_DIR = Path(__file__).resolve().parent


def load_templates() -> list[dict]:
    out = []
    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out.append({"code": data["code"], "name": data["name"], "description": data.get("description"), "sections": data["sections"]})
    return out


def get_template(code: str) -> dict | None:
    return next((t for t in load_templates() if t["code"] == code), None)
