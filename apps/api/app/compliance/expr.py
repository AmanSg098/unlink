"""A tiny, safe arithmetic language shared by custom KPIs and jurisdiction rules.

Allowed: numbers, + - * /, unary minus, parentheses, a caller-supplied set of variable names,
min(...), max(...), abs(x), round(x[, n]), floor(x), ceil(x), clamp(x, lo, hi), and (when enabled)
metric("name", default). Everything else is rejected at parse time. No eval().
"""

import ast
import math
import re
from collections.abc import Collection, Mapping

MAX_LEN = 500
METRIC_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
FUNCS = {"min", "max", "abs", "round", "clamp", "floor", "ceil", "metric"}
ARITY = {"abs": (1, 1), "round": (1, 2), "clamp": (3, 3), "min": (2, 20), "max": (2, 20), "floor": (1, 1),
         "ceil": (1, 1)}
_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b}


class ExprError(ValueError):
    pass


def parse(expression: str, names: Collection[str], allow_metric: bool = False) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ExprError("Expression is empty")
    if len(expression) > MAX_LEN:
        raise ExprError(f"Expression is longer than {MAX_LEN} characters")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"Syntax error at column {exc.offset}") from exc
    _check(tree.body, set(names), allow_metric)
    return tree


def _check(node: ast.AST, names: set[str], allow_metric: bool) -> None:
    match node:
        case ast.Constant(value=v) if isinstance(v, (int, float)) and not isinstance(v, bool):
            return
        case ast.Name(id=name):
            if name not in names:
                hint = ' or metric("name", default)' if allow_metric else ""
                raise ExprError(f"Unknown field '{name}'. Use one of {', '.join(sorted(names))}{hint}")
        case ast.BinOp(op=op, left=l, right=r):
            if type(op) not in _BINOPS:
                raise ExprError(f"Operator {type(op).__name__} is not allowed")
            _check(l, names, allow_metric)
            _check(r, names, allow_metric)
        case ast.UnaryOp(op=ast.USub() | ast.UAdd(), operand=o):
            _check(o, names, allow_metric)
        case ast.Call(func=ast.Name(id=fn), args=args, keywords=[]) if fn in FUNCS:
            if fn == "metric":
                if (not allow_metric or len(args) != 2 or not isinstance(args[0], ast.Constant)
                        or not isinstance(args[0].value, str) or not METRIC_RE.match(args[0].value)):
                    raise ExprError('metric() takes a lowercase name and a default, e.g. metric("csat", 3)')
                _check(args[1], names, allow_metric)
                return
            lo, hi = ARITY[fn]
            if not lo <= len(args) <= hi:
                raise ExprError(f"{fn}() takes {lo}-{hi} arguments")
            for a in args:
                _check(a, names, allow_metric)
        case _:
            raise ExprError(f"'{type(node).__name__}' is not allowed in expressions")


def evaluate(tree: ast.Expression, env: Mapping[str, float], metrics: Mapping[str, float] | None = None) -> float:
    metrics = metrics or {}

    def ev(n: ast.AST) -> float:
        match n:
            case ast.Constant(value=v):
                return float(v)
            case ast.Name(id=name):
                return float(env[name])
            case ast.BinOp(op=op, left=l, right=r):
                try:
                    return _BINOPS[type(op)](ev(l), ev(r))
                except ZeroDivisionError as exc:
                    raise ExprError("Division by zero") from exc
            case ast.UnaryOp(op=ast.USub(), operand=o):
                return -ev(o)
            case ast.UnaryOp(operand=o):
                return ev(o)
            case ast.Call(func=ast.Name(id="metric"), args=[ast.Constant(value=name), default]):
                v = metrics.get(name)
                return float(v) if v is not None else ev(default)
            case ast.Call(func=ast.Name(id=fn), args=args):
                vals = [ev(a) for a in args]
                if fn == "clamp":
                    return min(max(vals[0], vals[1]), vals[2])
                if fn == "round":
                    return float(round(vals[0], int(vals[1]) if len(vals) > 1 else 0))
                if fn == "floor":
                    return float(math.floor(vals[0]))
                if fn == "ceil":
                    return float(math.ceil(vals[0]))
                return float({"min": min, "max": max, "abs": lambda x: abs(x)}[fn](*vals))
        raise ExprError("Invalid expression")

    result = ev(tree.body)
    if not math.isfinite(result):
        raise ExprError("Expression produced a non-finite number")
    return result
