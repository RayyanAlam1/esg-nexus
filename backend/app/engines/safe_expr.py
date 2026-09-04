"""Safe expression evaluator shared by the metric engine (formulas) and the governance engine (rule conditions).

Only a whitelisted subset of Python's AST is allowed: literals, names, attribute access on the context,
arithmetic, comparisons, boolean logic, `in`, unary ops, subscripts on dict/list, and calls to
whitelisted functions. No imports, no lambdas, no comprehensions, no dunder access.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Tuple,
    ast.List,
    ast.IfExp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


class ExpressionError(ValueError):
    pass


def _safe_div(a, b, default=None):
    if a is None or b in (None, 0):
        return default
    return a / b


def _pct(a, b, default=None):
    v = _safe_div(a, b, None)
    return default if v is None else v * 100


def _yoy(current, previous, default=None):
    if current is None or previous in (None, 0):
        return default
    return (current - previous) / abs(previous) * 100


def _coalesce(*args):
    for a in args:
        if a is not None:
            return a
    return None


def _nz(v, default=0):
    return default if v is None else v


def _sum(*args):
    vals = [a for a in args if a is not None]
    if not vals:
        return None
    total = 0
    for v in vals:
        total += sum(v) if isinstance(v, (list, tuple)) else v
    return total


SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": lambda *a: min(x for x in a if x is not None) if any(x is not None for x in a) else None,
    "max": lambda *a: max(x for x in a if x is not None) if any(x is not None for x in a) else None,
    "sum": _sum,
    "len": len,
    "safe_div": _safe_div,
    "pct": _pct,
    "yoy": _yoy,
    "coalesce": _coalesce,
    "nz": _nz,
    "sqrt": math.sqrt,
    "float": float,
    "int": int,
    "str": str,
    "lower": lambda s: (s or "").lower(),
    "startswith": lambda s, p: str(s or "").startswith(p),
    "contains": lambda s, p: p in (s or ""),
}


class Ctx(dict):
    """Dict with attribute access so rules can be written as `metric.code == 'X'`."""

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        value = self.get(item)
        if isinstance(value, dict) and not isinstance(value, Ctx):
            return Ctx(value)
        return value


def _validate(node: ast.AST) -> None:
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_NODES):
            raise ExpressionError(f"Disallowed syntax: {type(child).__name__}")
        if isinstance(child, ast.Attribute) and child.attr.startswith("__"):
            raise ExpressionError("Dunder access is not allowed")
        if isinstance(child, ast.Name) and child.id.startswith("__"):
            raise ExpressionError("Dunder names are not allowed")
        if isinstance(child, ast.Call) and (not isinstance(child.func, ast.Name) or child.func.id not in SAFE_FUNCTIONS):
            raise ExpressionError("Only whitelisted functions may be called")


def evaluate(expression: str, context: dict[str, Any] | None = None) -> Any:
    """Evaluate `expression` against `context`. Raises ExpressionError on unsafe syntax."""
    if not expression or not expression.strip():
        raise ExpressionError("Empty expression")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Syntax error: {exc.msg}") from exc
    _validate(tree)
    env: dict[str, Any] = dict(SAFE_FUNCTIONS)
    env.update({"None": None, "True": True, "False": False})
    for key, value in (context or {}).items():
        env[key] = Ctx(value) if isinstance(value, dict) and not isinstance(value, Ctx) else value
    code = compile(tree, "<expr>", "eval")
    # SECURITY NOTE: eval() is used deliberately as the final step of a *safe expression parser*.
    # The AST has been validated above against a strict whitelist (no imports, lambdas, comprehensions,
    # attribute dunders or arbitrary calls) and builtins are removed, so only arithmetic/boolean logic over
    # the supplied context and whitelisted helper functions can execute.
    try:
        return eval(code, {"__builtins__": {}}, env)
    except ZeroDivisionError:
        return None
    except (TypeError, AttributeError, KeyError, IndexError) as exc:
        raise ExpressionError(f"Evaluation error: {exc}") from exc


# --- metric formula helpers ------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_.\-]+)(?:@([a-z_]+(?::[A-Za-z0-9_\-]+)?))?\}")


def extract_placeholders(formula: str) -> list[tuple[str, str | None]]:
    """Return [(metric_code, modifier)] for every `{CODE}` / `{CODE@prev}` / `{CODE@entity:EEL}` token."""
    return [(m.group(1), m.group(2)) for m in PLACEHOLDER_RE.finditer(formula or "")]


def compile_formula(formula: str) -> tuple[str, dict[str, tuple[str, str | None]]]:
    """Replace placeholders with variable names and return (expression, {var: (code, modifier)})."""
    mapping: dict[str, tuple[str, str | None]] = {}

    def _sub(match: re.Match) -> str:
        key = (match.group(1), match.group(2))
        for var, existing in mapping.items():
            if existing == key:
                return var
        var = f"v{len(mapping)}"
        mapping[var] = key
        return var

    expr = PLACEHOLDER_RE.sub(_sub, formula)
    return expr, mapping
