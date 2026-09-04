import pytest

from app.engines.safe_expr import ExpressionError, compile_formula, evaluate, extract_placeholders


def test_arithmetic_and_helpers():
    assert evaluate("safe_div(10, 4)") == 2.5
    assert evaluate("safe_div(1, 0)") is None
    assert evaluate("pct(25, 200)") == 12.5
    assert evaluate("yoy(110, 100)") == pytest.approx(10.0)
    assert evaluate("nz(None) + 5") == 5
    assert evaluate("coalesce(None, None, 3)") == 3


def test_nested_context_attribute_access():
    ctx = {"metric": {"code": "ENV.GHG.SCOPE1", "is_kpi": True}, "entity": {"kind": "group"}, "evidence_count": 0, "status": "final"}
    assert evaluate("metric.code == 'ENV.GHG.SCOPE1' and status in ('final', 'approved') and evidence_count == 0", ctx) is True
    assert evaluate("metric.is_kpi and entity.kind == 'group'", ctx) is True
    assert evaluate("metric.missing is None", ctx) is True


@pytest.mark.parametrize("bad", ["__import__('os')", "(lambda: 1)()", "[x for x in range(3)]", "metric.__class__", "open('x')", "a = 1", "import os"])
def test_disallowed_syntax_is_rejected(bad):
    with pytest.raises(ExpressionError):
        evaluate(bad, {"metric": {}})


def test_placeholders_and_compile():
    f = "safe_div({SOC.OHS.RECORDABLE_EMP} * 200000, {SOC.OHS.HOURS_EMP}) + yoy({X.Y.Z}, {X.Y.Z@prev})"
    assert extract_placeholders(f) == [("SOC.OHS.RECORDABLE_EMP", None), ("SOC.OHS.HOURS_EMP", None), ("X.Y.Z", None), ("X.Y.Z", "prev")]
    expr, mapping = compile_formula(f)
    assert len(mapping) == 4 and "{" not in expr
    env = {"v0": 3, "v1": 6_840_000, "v2": 110, "v3": 100}
    assert evaluate(expr, env) == pytest.approx(3 * 200000 / 6_840_000 + 10.0)
