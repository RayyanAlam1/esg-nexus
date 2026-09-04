"""Golden calculation tests: known inputs from the 2023 report → expected outputs. These fail if a formula changes."""

import pytest

from app.engines import consolidation, metric_engine
from tests.conftest import metric


def calc(ctx, code, entity=None, period=None):
    return metric_engine.calculate(ctx["db"], ctx["tenant"].id, metric(ctx["db"], code), entity or ctx["group"], period or ctx["fy2023"], persist=False)


def test_trir_employees_matches_report(ctx):
    r = calc(ctx, "SOC.OHS.TRIR_EMP")
    assert r.status == "ok"
    assert r.value == pytest.approx(3 * 200_000 / 6_840_000)  # 0.0877 → printed 0.09
    assert round(r.value, 2) == 0.09
    assert r.inputs["SOC.OHS.RECORDABLE_EMP"]["value"] == 3 and r.inputs["SOC.OHS.HOURS_EMP"]["value"] == 6_840_000


def test_trir_contractors_includes_fatality(ctx):
    r = calc(ctx, "SOC.OHS.TRIR_CONTRACTOR")
    assert r.value == pytest.approx((13 + 1) * 200_000 / 29_600_000)
    assert round(r.value, 2) == 0.09
    prev = calc(ctx, "SOC.OHS.TRIR_CONTRACTOR", period=ctx["fy2022"])
    assert round(prev.value, 2) == 0.13


def test_hire_and_turnover_rates(ctx):
    assert round(calc(ctx, "SOC.WORKFORCE.HIRE_RATE_PCT").value) == 15  # 353 / 2,370
    assert round(calc(ctx, "SOC.WORKFORCE.TURNOVER_RATE_PCT").value) == 16  # 389 / 2,370
    assert round(calc(ctx, "SOC.WORKFORCE.TURNOVER_RATE_PCT", period=ctx["fy2022"]).value) == 18


def test_consolidated_totals_reproduce_printed_group_totals(ctx):
    db, t = ctx["db"], ctx["tenant"].id
    assert metric_engine.get_value(db, t, "ENV.GHG.SCOPE1", ctx["group"], ctx["fy2023"])[0] == 7_327_238
    assert metric_engine.get_value(db, t, "ENV.GHG.SCOPE2", ctx["group"], ctx["fy2023"])[0] == 69_000
    assert metric_engine.get_value(db, t, "ENV.ENERGY.TOTAL", ctx["group"], ctx["fy2023"])[0] == 92_448_453
    assert metric_engine.get_value(db, t, "ENV.WATER.WITHDRAWN", ctx["group"], ctx["fy2023"])[0] == 56_218
    assert metric_engine.get_value(db, t, "SOC.WORKFORCE.TOTAL", ctx["group"], ctx["fy2023"])[0] == 3_514


def test_consolidation_contributions_and_excluded_entities(ctx):
    agg = consolidation.aggregate(ctx["db"], metric(ctx["db"], "ENV.GHG.SCOPE1"), ctx["group"], ctx["fy2023"])
    assert agg.value == 7_327_238
    included = {c["entity"] for c in agg.contributions if c["included"]}
    assert {"EEL", "EFERT", "EPCL", "ENFRA"} <= included
    assert all(c["factor"] == 0 for c in agg.contributions if c["entity"] == "FCEPL")  # equity-accounted associate excluded


def test_derived_metrics_and_checks(ctx):
    assert calc(ctx, "ENV.GHG.SCOPE1_2_TOTAL").value == 7_396_238
    assert calc(ctx, "ENV.WATER.BALANCE_CHECK").value == pytest.approx(0.0)  # withdrawn − consumed − discharged
    assert calc(ctx, "SOC.WORKFORCE.TOTAL_CHECK").value == 3_514
    assert calc(ctx, "ECO.TAX.TOTAL").value == 83_013  # vs 83,012 printed (rounding) — surfaced as a finding, not corrected
    assert calc(ctx, "ENV.GHG.YOY_CHANGE_PCT").value == pytest.approx((7_396_238 - 6_904_931) / 6_904_931 * 100)


def test_missing_inputs_return_data_unavailable_not_a_number(ctx):
    r = calc(ctx, "ENV.ENERGY.RENEWABLE_SHARE_PCT")  # renewable consumption not disclosed
    assert r.status == "missing_inputs" and r.value is None
    assert "Data unavailable" in metric_engine.explain(r)


def test_reported_values_are_never_overwritten_by_recalculation(ctx):
    from sqlalchemy import select

    from app.models import MetricValue

    m = metric(ctx["db"], "ENV.WASTE.TOTAL")
    mv = (
        ctx["db"]
        .execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == ctx["efert"].id, MetricValue.period_id == ctx["fy2023"].id))
        .scalars()
        .first()
    )
    assert mv.source_type == "reported" and mv.value_numeric == 1_949  # printed; 257 + 1,694 = 1,951 recalculated
    r = metric_engine.calculate(ctx["db"], ctx["tenant"].id, m, ctx["efert"], ctx["fy2023"], persist=True)
    ctx["db"].commit()
    assert r.value == 1_951
    ctx["db"].refresh(mv)
    assert mv.value_numeric == 1_949 and mv.calculation_run_id == r.run_id
