"""Safe arithmetic. Parses with ``ast`` and walks an allowlist of node types;
nothing is ever passed to ``eval``/``exec``."""

from __future__ import annotations

import ast
import operator
import re
from typing import Callable

MAX_EXPR_LENGTH = 200
MAX_DEPTH = 40
MAX_EXPONENT = 64
MAX_BASE = 10**9
MAX_INT_BITS = 2000


class CalcError(ValueError):
    """The expression is invalid, unsafe or unsupported."""


def _pow(a, b):
    if abs(b) > MAX_EXPONENT or (isinstance(a, int) and abs(a) > MAX_BASE):
        raise CalcError("That power is too large for me to compute.")
    return operator.pow(a, b)


_BINARY: dict[type, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _pow,
}


def _eval(node: ast.AST, depth: int):
    if depth > MAX_DEPTH:
        raise CalcError("That expression is too deeply nested.")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _eval(node.operand, depth + 1)
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval(node.left, depth + 1)
        right = _eval(node.right, depth + 1)
        try:
            result = _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalcError("I can't divide by zero.") from exc
        except OverflowError as exc:
            raise CalcError("That number is too large.") from exc
        if isinstance(result, int) and result.bit_length() > MAX_INT_BITS:
            raise CalcError("That number is too large.")
        return result
    raise CalcError("I can only do basic arithmetic.")


def evaluate(expression: str):
    """Evaluate a plain arithmetic expression such as ``(2 + 3) * 4``."""
    if not expression or len(expression) > MAX_EXPR_LENGTH:
        raise CalcError("That expression is empty or too long.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise CalcError("I couldn't read that as a calculation.") from exc
    return _eval(tree.body, 0)


def format_number(value) -> str:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CalcError("That result isn't a usable number.")
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10g}"
    return str(value)


_WORD_OPERATORS = [
    (r"\bto the power of\b", "**"),
    (r"\bmultiplied by\b", "*"),
    (r"\bdivided by\b", "/"),
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\btimes\b", "*"),
    (r"\binto\b", "*"),
    (r"\bover\b", "/"),
]
_CALC_PREFIX = re.compile(
    r"^(?:what(?:'s| is)|calculate|compute|solve|how much is|calc)\s+", re.IGNORECASE
)
_ALLOWED_CHARS = re.compile(r"[\d\s.+\-*/()%]+")


def to_expression(text: str) -> str | None:
    """Return a clean arithmetic string if ``text`` looks like a calculation."""
    candidate = text.strip().rstrip("?=! .")
    candidate = _CALC_PREFIX.sub("", candidate)
    candidate = candidate.lower()
    for pattern, symbol in _WORD_OPERATORS:
        candidate = re.sub(pattern, f" {symbol} ", candidate)
    candidate = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", candidate)
    candidate = candidate.replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate or not _ALLOWED_CHARS.fullmatch(candidate):
        return None
    if not re.search(r"\d", candidate) or not re.search(r"[+\-*/%]", candidate.lstrip("+-")):
        return None
    return candidate
