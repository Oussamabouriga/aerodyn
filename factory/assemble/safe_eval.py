from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, Callable


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_ALLOWED_FUNCS: Dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "clamp": clamp,
    "abs": abs,
    "round": round,
}


_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Compare,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.IfExp,
)


@dataclass
class SafeEval:
    """
    Small safe expression evaluator:
    - allows math ops, comparisons, if-expressions, and a few safe functions.
    - blocks attribute access, indexing, imports, etc.
    """

    def eval(self, expr: str, env: Dict[str, Any]) -> Any:
        tree = ast.parse(expr, mode="eval")
        self._validate(tree)
        code = compile(tree, "<equation>", "eval")
        safe_globals = {"__builtins__": {}, **_ALLOWED_FUNCS}
        return eval(code, safe_globals, env)

    def _validate(self, node: ast.AST) -> None:
        for n in ast.walk(node):
            if not isinstance(n, _ALLOWED_NODES):
                raise ValueError(f"Disallowed expression node: {type(n).__name__}")

            # Only allow calling allowed funcs by name
            if isinstance(n, ast.Call):
                if not isinstance(n.func, ast.Name) or n.func.id not in _ALLOWED_FUNCS:
                    raise ValueError("Only safe functions are allowed: min, max, clamp, abs, round")

            # No attribute access
            if isinstance(n, ast.Attribute):
                raise ValueError("Attribute access is not allowed")

            # No subscripts (indexing)
            if isinstance(n, ast.Subscript):
                raise ValueError("Indexing is not allowed")