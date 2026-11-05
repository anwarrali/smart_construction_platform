"""Run only against an explicitly designated disposable database.

Usage: PHASE2A_EVAL_ISOLATED=1 DATABASE_URL=... SECRET_KEY=... python
scripts/evaluate_phase2a.py --output /tmp/phase2a-evaluation.json
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("PHASE2A_EVAL_ISOLATED") != "1" or not os.environ.get("DATABASE_URL"):
        parser.error("Set PHASE2A_EVAL_ISOLATED=1 and a disposable DATABASE_URL")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    xml_path = args.output.with_suffix(".xml")
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
               "tests/test_phase2a_evaluation.py", "tests/test_phase2a_correctness.py",
               "tests/test_phase2a_integration.py", f"--junitxml={xml_path}"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                               env={**os.environ, "OPENAI_API_KEY": "", "PUSH_ENABLED": "false",
                                    "JOB_RUNNER_EMBEDDED": "false"}, capture_output=True, text=True)
    args.output.with_suffix(".log").write_text(completed.stdout + completed.stderr)
    cases = []
    if xml_path.exists():
        for item in ET.parse(xml_path).iter("testcase"):
            status = "passed"
            for tag in ("failure", "error", "skipped"):
                if item.find(tag) is not None:
                    status = tag
            cases.append({"test": item.get("name"), "status": status,
                          "seconds": float(item.get("time", "0"))})
    args.output.write_text(json.dumps({"dataset_version": 1,
        "scope": "Synthetic mechanism baseline; no real model/retrieval/engineering accuracy claim",
        "exit_code": completed.returncode, "cases": cases,
        "counts": {s: sum(c["status"] == s for c in cases)
                   for s in ("passed", "failure", "error", "skipped")}}, indent=2))
    print(args.output.read_text())
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
