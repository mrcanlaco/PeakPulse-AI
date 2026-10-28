"""Create a local paper proposal from audited candidate/state/filter JSON."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dao_vang.fibo_short.paper_rules_v406 import plan_paper_entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = plan_paper_entry(payload["candidate"], payload["state"], payload["filters"], now=payload["now"])
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["status"])


if __name__ == "__main__":
    main()
