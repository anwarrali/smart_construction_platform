"""No function may reference a name it never receives.

## Why this exists

`GET /api/v1/projects/{id}` shipped with this in its body:

    if not has_permission(db, current_user, "cost_validation.review", project.id):

`db` was never a parameter of that handler. Python is happy to compile it — a
free variable is only resolved when the line actually runs — so the module
imported cleanly, the app started, every other endpoint worked, and this one
raised `NameError` on every single call.

What made it expensive was how it *looked*. An unhandled exception propagates
past `CORSMiddleware` to Starlette's error handler, which returns a bare 500
with no headers on it. The browser therefore reported:

    No 'Access-Control-Allow-Origin' header is present

and the obvious next move — "fix CORS" — would have been wrong twice over:
CORS was correctly configured all along, and changing it would have hidden a
real 500 behind a readable error message.

Two more of the same kind were found in the same sweep (`task.project_id` in
`_validate_task_assignees`, where the parameter is `project_id`; and
`has_permission` used at module scope in `attachments.py` where the import was
function-local). None of the three was reachable by the existing suite.

## Why a static check rather than more endpoint tests

Endpoint tests find this only where somebody thought to write one, and the bug
lives specifically in the branches nobody exercised — the permission check that
only runs for one kind of caller, on one project shape. A whole-tree scan finds
every instance for the cost of one test, and it fails at import time in CI
rather than as a browser error in somebody's afternoon.

This is deliberately narrow: it only reports names that are neither a
parameter, nor bound anywhere in the function, nor defined at module level, nor
a builtin. It does not type-check, and it will not catch an attribute that does
not exist. It catches exactly the mistake above.
"""

from __future__ import annotations

import ast
import builtins
import pathlib

BUILTINS = frozenset(dir(builtins))

#: Where the application lives. Tests and migrations are excluded: a migration
#: is a historical document, and the test tree has its own fixtures.
APP_ROOT = pathlib.Path("app")


def _module_level_names(tree: ast.Module) -> set[str]:
    """Every name a function body can reach through the module's own globals.

    Top-level statements only. Walking the whole tree would sweep up every
    function's parameters as well, which is what made the first version of this
    check silently pass over the very bug it was written for: `db` is a
    parameter of forty other handlers in the same file.
    """
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= {
                    item.id for item in ast.walk(target) if isinstance(item, ast.Name)
                }
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For)):
            # Conditional imports and module-level loops still bind globally.
            for item in ast.walk(node):
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
                    names.add(item.id)
                elif isinstance(item, (ast.Import, ast.ImportFrom)):
                    for alias in item.names:
                        names.add((alias.asname or alias.name).split(".")[0])
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(item.name)
    return names


def _bound_in(node: ast.AST) -> set[str]:
    """Every name bound anywhere inside a function, including nested scopes.

    `ast.walk` descends into nested functions and comprehensions on purpose: a
    closure genuinely can read its enclosing function's locals, so treating
    those as bound is correct and avoids a false positive on every decorator
    and every FastAPI dependency factory in the codebase.
    """
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
            names.add(item.id)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(item.name)
        elif isinstance(item, (ast.Import, ast.ImportFrom)):
            for alias in item.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(item, ast.ExceptHandler) and item.name:
            names.add(item.name)
        elif isinstance(item, ast.arg):
            names.add(item.arg)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.add(item.target.id)
        elif isinstance(item, (ast.Global, ast.Nonlocal)):
            names |= set(item.names)
    return names


def _undefined_names() -> list[str]:
    findings: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_names = _module_level_names(tree)

        def check(function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            in_scope = _bound_in(function)
            for item in ast.walk(function):
                if not (isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)):
                    continue
                if item.id in in_scope or item.id in module_names or item.id in BUILTINS:
                    continue
                findings.append(
                    f"{path.as_posix()}:{item.lineno} "
                    f"in {function.name}() -> '{item.id}'"
                )

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                check(node)
            elif isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        check(member)
    return sorted(set(findings))


def test_no_function_references_a_name_it_never_receives():
    findings = _undefined_names()
    assert findings == [], (
        "These names are read but never bound — each is a NameError waiting for "
        "the branch that reaches it, and through a browser it will look like a "
        "CORS failure rather than a 500:\n  " + "\n  ".join(findings)
    )


def test_the_check_actually_catches_the_bug_it_was_written_for():
    """A guard against the guard quietly passing everything.

    The first version of this scan collected module-level names with
    `ast.walk`, which swept in every parameter of every function in the file —
    so `db` looked defined and the real bug scanned clean. This reproduces the
    shipped defect in miniature and asserts the checker still sees it.
    """
    source = (
        "from fastapi import Depends\n"
        "def other(db=None):\n"
        "    return db\n"
        "def handler(project=None, current_user=None):\n"
        "    return has_permission(db, current_user, 'x', project.id)\n"
    )
    tree = ast.parse(source)
    module_names = _module_level_names(tree)
    handler = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "handler"
    )
    in_scope = _bound_in(handler)
    unresolved = {
        item.id for item in ast.walk(handler)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
        and item.id not in in_scope and item.id not in module_names
        and item.id not in BUILTINS
    }
    assert "db" in unresolved, "the checker must still catch the original defect"
    assert "has_permission" in unresolved, "an unimported call is the same class of bug"
