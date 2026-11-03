import json, sys
from .builders import BUILDERS, build

def main() -> None:
    names = sys.argv[1:] or ["--help"]
    if names[0] in ("-h", "--help"):
        print("usage: python -m spellbreaker_data <dataset|all> ...\navailable:", ", ".join(BUILDERS)); return
    for n in (list(BUILDERS) if names == ["all"] else names):
        m = build(n)
        print(f"{n}: {m['rows']} rows | {json.dumps(m['stats'], default=str)[:300]}")

main()
