"""Test-quality indicators from a ``scripts/mutation.py`` kill matrix.

Run with ``uv run python scripts/mutation_report.py OUT`` on a results directory; writes
``OUT/tests.md`` and prints a summary. Indicators follow the mutation-testing literature (see
``docs/plans/mutation-pilot.md``); they are review prompts, never targets or deletion lists:

- Kill provenance: how mutants died (assertion, crash only, collection, timeout, only by tests
  that do not run the line). Crash and collection kills count as kills but say little about
  assertions.
- Dominator mutants: killed mutants grouped by their exact set of killing tests; a group is a
  dominator when no other group's set is a strict subset of its own. Each dominator is one test
  requirement (counted per module); a dominator whose only killer is one test makes that test
  load-bearing.
- Per test, over the killed mutants whose lines it runs: how many it kills by assertion and how
  many only by crashing. A test that runs many killable mutants and kills none by assertion
  is a reading prompt: a narrow-purpose test, a negative-outcome test (expects nothing), or an
  oracle computed by the code under test. (A share over dominators would mostly measure how
  specialised a test is: dominators have a median of one killer but many covering tests.)
- Pseudo-tested functions: the body-removal mutant survives although tests run the body; listed
  with the tests that reached it without noticing.

Killer sets are complete only for runs with ``--full``: with test selection, a test that relies
on state another test computed (memoisation, singletons) is not credited, so unique kills and
dominators can be wrong.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BODY = "body/ReturnNone"


def provenance(record: dict) -> str:
    if record["status"] == "timeout":
        return "timeout"
    killers = record.get("killers", {})
    tests = {t: k for t, k in killers.items() if not t.startswith("collect:")}
    covering = set(record.get("covering", ()))
    if not tests:
        return "collection only" if killers else "unknown"
    if covering.isdisjoint(tests):
        return "only tests not running the line"
    if any(k == "assert" for t, k in tests.items() if t in covering):
        return "assertion"
    return "crash only"


def dominators(killed: list[dict]) -> dict[frozenset[str], list[dict]]:
    groups: dict[frozenset[str], list[dict]] = defaultdict(list)
    for record in killed:
        tests = frozenset(t for t in record["killers"] if not t.startswith("collect:"))
        if tests:
            groups[tests].append(record)
    sets = sorted(groups, key=len)
    return {tests: groups[tests] for tests in sets if not any(other < tests for other in sets)}


def indicators(records: list[dict]) -> dict:
    ran = [r for r in records if r["status"] in {"killed", "survived", "timeout"}]
    mutants = [r for r in ran if r["operator"] != BODY]
    killed = [r for r in mutants if r["status"] == "killed"]
    dominant = dominators(killed)
    per_test: dict[str, Counter[str]] = defaultdict(Counter)
    for r in killed:
        for test in r.get("covering", ()):
            counts = per_test[test]
            counts["covered"] += 1
            kind = r["killers"].get(test)
            counts["asserted"] += kind == "assert"
            counts["crashed"] += kind == "error"
    for tests in dominant:
        if len(tests) == 1:
            per_test[next(iter(tests))]["unique"] += 1
    bodies = [r for r in ran if r["operator"] == BODY]
    modules: dict[str, Counter[str]] = defaultdict(Counter)
    for r in mutants:
        modules[r["module"]][r["status"]] += 1
    for group in dominant.values():
        for module in {r["module"] for r in group}:
            modules[module]["dominators"] += 1
    return {
        "mutants": len(mutants),
        "provenance": Counter(provenance(r) for r in mutants if r["status"] != "survived"),
        "dominators": len(dominant),
        "killed": len(killed),
        "per_test": per_test,
        "modules": modules,
        "bodies": len(bodies),
        "pseudo_tested": sorted(
            (r for r in bodies if r["status"] == "survived" and r.get("covering")),
            key=lambda r: (r["module"], r["start"]),
        ),
    }


def render(result: dict) -> str:
    per_test = result["per_test"]
    out = [
        "# Test-quality indicators",
        "",
        (
            f"{result['mutants']} operator mutants ran to a verdict; {result['killed']} killed, "
            f"forming {result['dominators']} dominator groups (test requirements)."
        ),
        "",
        "## Kill provenance",
        "",
        "| How it died | Mutants |",
        "| --- | ---: |",
        *(f"| {kind} | {n} |" for kind, n in result["provenance"].most_common()),
        "",
        "## Modules",
        "",
        "| Module | Killed | Survived | Timeout | Dominators |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for module, c in sorted(result["modules"].items(), key=lambda kv: -kv[1]["survived"]):
        out.append(
            f"| `{module}` | {c['killed']} | {c['survived']} | {c['timeout']} | {c['dominators']} |"
        )
    silent = sorted(
        (t for t, c in per_test.items() if c["covered"] >= 20 and c["asserted"] == 0),
        key=lambda t: -per_test[t]["covered"],
    )
    out += [
        "",
        f"## Run ≥ 20 killed mutants, kill none by assertion ({len(silent)}; read them)",
        "",
        "| Test | Runs | Crash kills | Unique |",
        "| --- | ---: | ---: | ---: |",
    ]
    for test in silent:
        c = per_test[test]
        out.append(f"| `{test}` | {c['covered']} | {c['crashed']} | {c['unique']} |")
    out += [
        "",
        "## Load-bearing (most unique dominators)",
        "",
        "| Test | Unique | Covered |",
        "| --- | ---: | ---: |",
    ]
    for test in sorted(per_test, key=lambda t: -per_test[t]["unique"])[:20]:
        out.append(f"| `{test}` | {per_test[test]['unique']} | {per_test[test]['covered']} |")
    pseudo = result["pseudo_tested"]
    out += [
        "",
        f"## Pseudo-tested functions ({len(pseudo)} of {result['bodies']} body removals survived)",
        "",
    ]
    for r in pseudo:
        reached = r.get("covering", [])
        shown = ", ".join(f"`{t.split('::', 1)[-1]}`" for t in reached[:4])
        more = f" and {len(reached) - 4} more" if len(reached) > 4 else ""
        out.append(f"- `{r['module']}` `{r['function']}` (line {r['start'][0]}): {shown}{more}")
    return "\n".join(out) + "\n"


def main() -> None:
    out = Path(sys.argv[1])
    result = indicators([json.loads(line) for line in (out / "results.jsonl").open()])
    (out / "tests.md").write_text(render(result))
    per_test = result["per_test"]
    print(
        json.dumps(
            {
                "mutants": result["mutants"],
                "killed": result["killed"],
                "dominators": result["dominators"],
                "provenance": result["provenance"],
                "tests_running_a_killed_mutant": len(per_test),
                "run_20_killed_but_no_assertion_kill": sum(
                    1 for c in per_test.values() if c["covered"] >= 20 and c["asserted"] == 0
                ),
                "body_removals": result["bodies"],
                "pseudo_tested": len(result["pseudo_tested"]),
                "report": str(out / "tests.md"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
