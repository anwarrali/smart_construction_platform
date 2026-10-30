"""Generate the permission coverage report from the code itself.

    python scripts/permission_inventory.py [--json out.json] [--markdown out.md]

Run from `backend/` with the repository root as the parent directory. Nothing
here is hand-maintained: every row comes from `app.core.permission_catalogue`,
`app.core.role_templates` and a literal search of the sources for the code.

What a row's classification means:

* **enforced+tested** — referenced by backend runtime code (an enforcement
  point), by the web client, and by at least one backend test.
* **backend-only** — enforced and tested on the server, no web-client
  reference. Fine for codes the web client never needs to ask about
  (mobile-only, AI tool layer, background work).
* **untested** — enforced, but no test mentions the code.
* **ui-only** — the web client reads it, no backend code does: the screen
  promises something the server does not check. A defect.
* **unused** — registered and nobody reads it. A defect, or a code to retire.

A literal search can miss a code assembled at runtime; anything classified
`ui-only` or `unused` is investigated by hand before it is called a defect —
see docs/PERMISSION_COVERAGE.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.core.permission_catalogue import CATALOGUE  # noqa: E402
from app.core.role_templates import LEGACY_CONSULTANT_TEMPLATE, TEMPLATES  # noqa: E402

#: Files that *declare* codes rather than check them.
DECLARING = {
    "app/core/permission_catalogue.py",
    "app/core/role_templates.py",
    "app/db/legacy_rbac.py",
    "app/db/rbac_backfill.py",
    "app/db/seed_demo.py",
}


def _sources(root: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    files: dict[str, str] = {}
    if not root.exists():
        return files
    for pattern in patterns:
        for path in root.rglob(pattern):
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                files[path.relative_to(REPO).as_posix()] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    return files


def _hits(code: str, files: dict[str, str]) -> list[str]:
    needle = re.compile(r"""["'`]""" + re.escape(code) + r"""["'`]""")
    found = []
    for name, text in files.items():
        lines = [index + 1 for index, line in enumerate(text.splitlines()) if needle.search(line)]
        if lines:
            found.append(f"{name}:{lines[0]}" + (f" (+{len(lines) - 1})" if len(lines) > 1 else ""))
    return sorted(found)


ROUTE = re.compile(r"""^@(\w+)\.(get|post|put|patch|delete)\(\s*["']([^"']*)""")
DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)")
PREFIX = re.compile(r"""^(\w+)\s*=\s*APIRouter\(.*?prefix\s*=\s*["']([^"']*)""")


def _operations(code: str, files: dict[str, str]) -> list[str]:
    """Where the check runs: `METHOD /path (function)` in a router, else `module.function`.

    Each literal hit is attributed to the top-level function containing it;
    for a router function, every route decorator on it is listed with the
    router's prefix. A hit in a helper is attributed to the helper — the
    callers of that helper are not chased, so read those rows as "checked in
    this helper", not as "every endpoint using it".
    """
    needle = re.compile(r"""["'`]""" + re.escape(code) + r"""["'`]""")
    found: set[str] = set()
    for name, text in files.items():
        lines = text.splitlines()
        prefixes = {m.group(1): m.group(2) for m in map(PREFIX.match, lines) if m}
        # constants such as `VIEW = "site_report.view"` make the constant the needle too
        consts = [m.group(1) for m in re.finditer(
            r"""^([A-Z_]+)\s*=\s*["']""" + re.escape(code) + r"""["']""", text, re.M)]
        pattern = needle if not consts else re.compile(
            needle.pattern + "|" + "|".join(r"\b" + c + r"\b" for c in consts))
        for index, line in enumerate(lines):
            code_part = line.split("#", 1)[0]
            if not pattern.search(code_part) or re.match(r"^[A-Z_]+\s*=", line):
                continue
            start = index
            while start >= 0 and not DEF.match(lines[start]):
                start -= 1
            module = name.removeprefix("backend/app/").removesuffix(".py").replace("/", ".")
            if start < 0:
                found.add(f"{module} (module-level table)")
                continue
            function = DEF.match(lines[start]).group(1)
            routes, cursor = [], start - 1
            while cursor >= 0 and lines[cursor].startswith("@"):
                match = ROUTE.match(lines[cursor])
                if match:
                    routes.append(f"{match.group(2).upper()} {prefixes.get(match.group(1), '')}{match.group(3)}")
                cursor -= 1
            if routes:
                found.update(f"{route} ({function})" for route in routes)
            else:
                found.add(f"{module}.{function}")
    return sorted(found)


def _ifc_verb_operations(code: str, files: dict[str, str]) -> list[str]:
    """IFC endpoints name a verb (`can_ifc(..., "COMPARE")`); `ifc_policy` maps it to the code."""
    from app.services.ifc_policy import IFC_VERB_PERMISSION

    verbs = [verb for verb, mapped in IFC_VERB_PERMISSION.items() if mapped == code]
    found: list[str] = []
    for verb in verbs:
        api = {k: v for k, v in files.items() if k.startswith("backend/app/api/")}
        found += [f"{op} [IFC verb {verb}]" for op in _operations(verb, api)]
    return found


def build() -> list[dict]:
    backend = _sources(BACKEND / "app", ("*.py",))
    runtime = {k: v for k, v in backend.items()
               if k.removeprefix("backend/") not in DECLARING}
    tests = _sources(BACKEND / "tests", ("*.py",))
    web = _sources(REPO / "frontend" / "src", ("*.ts", "*.tsx"))
    web_runtime = {k: v for k, v in web.items() if ".test." not in k}
    web_tests = {k: v for k, v in web.items() if ".test." in k}

    templates = [*TEMPLATES, LEGACY_CONSULTANT_TEMPLATE]
    rows = []
    for item in CATALOGUE:
        enforcement = _hits(item.code, runtime)
        frontend = _hits(item.code, web_runtime)
        backend_tests = _hits(item.code, tests)
        frontend_tests = _hits(item.code, web_tests)
        if enforcement and backend_tests and frontend:
            status = "enforced+tested"
        elif enforcement and backend_tests:
            status = "backend-only"
        elif enforcement:
            status = "untested"
        elif frontend:
            status = "ui-only"
        else:
            status = "unused"
        scope = ("platform" if not item.project_scoped
                 else "project-record" if item.registry else "project")
        rows.append({
            "code": item.code,
            "group": item.group,
            "label": item.label,
            "description": item.description,
            "scope": scope,
            "admin_locked": item.admin_locked,
            "office_only": item.office_only,
            "never_external": item.never_external,
            "default_roles": sorted(t.code for t in templates if item.code in t.permissions()),
            # Every catalogue code can be granted or denied per person; the
            # never-external wall and the admin lock bound what an override does.
            "user_override": (
                "grant/deny"
                + ("; deny refused on the office administrator" if item.admin_locked else "")
                + ("; grant refused for external participants" if item.never_external else "")
            ),
            "backend_enforcement": enforcement,
            "operations": sorted(set(_operations(item.code, runtime)) | set(_ifc_verb_operations(item.code, runtime))),
            "frontend": frontend,
            "backend_tests": backend_tests,
            "frontend_tests": frontend_tests,
            "status": status,
        })
    return rows


def markdown(rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    out = [
        "| Code | Scope | Default roles | Backend | Web | Tests | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        first = lambda values: (values[0] + (f" +{len(values) - 1}" if len(values) > 1 else "")) if values else "—"  # noqa: E731
        out.append(
            f"| `{row['code']}` | {row['scope']} | {len(row['default_roles'])} | "
            f"{first(row['backend_enforcement'])} | {first(row['frontend'])} | "
            f"{len(row['backend_tests'])} backend / {len(row['frontend_tests'])} web | {row['status']} |"
        )
    summary = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    return f"{len(rows)} permissions — {summary}\n\n" + "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--markdown")
    args = parser.parse_args()
    rows = build()
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown(rows), encoding="utf-8")
    if not (args.json or args.markdown):
        print(markdown(rows))


if __name__ == "__main__":
    main()
