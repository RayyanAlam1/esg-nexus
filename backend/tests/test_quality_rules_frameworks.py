from sqlalchemy import select

from app.engines import data_quality, lineage, readiness
from app.engines import frameworks as fw_engine
from app.engines import rules as rules_engine
from app.engines.evidence_resolution import resolve
from app.models import Requirement
from tests.conftest import metric


def test_quality_missing_value_scores_zero(ctx):
    r = data_quality.assess(ctx["db"], ctx["tenant"].id, metric(ctx["db"], "ENV.GHG.SCOPE3"), ctx["group"], ctx["fy2023"], persist=False)
    assert r.overall == 0 and "Data unavailable" in r.explanation[0]


def test_quality_flags_reported_vs_recalculated_inconsistency(ctx):
    m = metric(ctx["db"], "ENV.WASTE.TOTAL")
    r = data_quality.assess(ctx["db"], ctx["tenant"].id, m, ctx["efert"], ctx["fy2023"], persist=False)
    assert r.scores["consistency"] < 100
    assert any("differs from recalculated" in n for n in r.explanation)


def test_quality_estimate_deduction(ctx):
    r = data_quality.assess(
        ctx["db"],
        ctx["tenant"].id,
        metric(ctx["db"], "ENV.ENERGY.SOLARIZED_TOWERS_PCT"),
        ctx["db"]
        .execute(select(__import__("app.models", fromlist=["Entity"]).Entity).where(__import__("app.models", fromlist=["Entity"]).Entity.code == "ENFRA"))
        .scalars()
        .first(),
        ctx["fy2023"],
        persist=False,
    )
    assert r.scores["accuracy"] < 100 and any("estimate" in n for n in r.explanation)


def test_rules_engine_context_and_outcomes(ctx):
    db = ctx["db"]
    m = metric(db, "ENV.GHG.SCOPE3")
    context = rules_engine.metric_value_context(db, m, ctx["group"], ctx["fy2023"], None)
    assert context["is_null"] is True and context["metric"]["is_kpi"] is True
    outcomes = rules_engine.evaluate_rules(rules_engine.active_rules(db, ctx["tenant"].id, "metric_value"), context)
    triggered = {o.rule_code for o in outcomes if o.triggered}
    assert "GR-003" in triggered  # KPI missing at group level
    assert "GR-001" not in triggered


def test_blocking_rule_for_scope1_without_evidence(ctx):
    db = ctx["db"]
    m = metric(db, "ENV.GHG.SCOPE1")
    context = rules_engine.metric_value_context(db, m, ctx["efert"], ctx["fy2023"], None)
    context.update({"status": "final", "reporting_status": "final", "evidence_count": 0, "is_null": False})
    outcomes = rules_engine.evaluate_rules(rules_engine.active_rules(db, ctx["tenant"].id, "metric_value"), context)
    gr1 = next(o for o in outcomes if o.rule_code == "GR-001")
    assert gr1.triggered and gr1.blocks and "EFERT" in gr1.message


def test_evidence_inheritance_for_consolidated_and_calculated_values(ctx):
    db = ctx["db"]
    ev, how = resolve(db, metric(db, "ENV.GHG.SCOPE1"), ctx["group"], ctx["fy2023"])  # consolidated group value
    assert ev and "inherited_children" in how
    ev2, _how2 = resolve(db, metric(db, "SOC.OHS.TRIR_EMP"), ctx["group"], ctx["fy2023"])  # reported + inputs
    assert ev2 and any(e.code == "EV-RPT23-P67" for e in ev2)


def test_framework_coverage_and_gaps(ctx):
    db = ctx["db"]
    cov = fw_engine.coverage(db, ctx["tenant"].id, ctx["org"].id, ctx["fy2023"], "WEF_SCM")
    assert cov["applicable"] == 21 and 60 <= cov["alignment_pct"] <= 95  # 66.7 % from data alone; rises as narratives are drafted
    req = db.execute(select(Requirement).where(Requirement.code == "WEF.PLANET.GHG_EMISSIONS")).scalars().first()
    status = fw_engine.requirement_status(db, ctx["tenant"].id, ctx["org"].id, ctx["fy2023"], req)
    assert status["status"] == "partial" and status["metric_gap"] is True  # Scope 3 not reported
    assert "compliance certification" in cov["disclaimer"]


def test_lineage_graph_reaches_evidence(ctx):
    g = lineage.build(ctx["db"], ctx["tenant"].id, metric(ctx["db"], "SOC.OHS.TRIR_EMP"), ctx["group"], ctx["fy2023"])
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"metric", "calculation", "evidence"} <= kinds
    assert any(e["relation"] == "input" for e in g["edges"])


def test_readiness_components(ctx):
    r = readiness.compute(ctx["db"], ctx["tenant"].id, ctx["org"].id, ctx["fy2023"], framework_codes=["WEF_SCM", "UNGC", "UN_SDG"])
    assert set(r.components) == {"data_completeness", "data_quality", "evidence_coverage", "framework_alignment", "governance_checks", "ai_evaluation", "human_approvals"}
    assert 0 <= r.overall <= 100 and r.components["evidence_coverage"] >= 95
