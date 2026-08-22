"""No CI workflow may gate on a hardcoded calendar date.

The supply-chain job once carried a `npm audit` exception that switched itself off by
comparing `$(date -u +%F)` against a literal expiry. That shape rots silently in both
directions: before the date it suppresses real findings, and after it the job fails for a
reason that has nothing to do with the advisory that is actually present. It also carried an
`overrides` pin that froze a package AT a flagged version, which the expiry date hid.

The replacement is a plain hard gate, and this guard keeps it plain: a workflow may not read
the current date and compare it against a literal, and may not compare a literal date at all.
Time-based leniency belongs in an issue with an owner, not in a shell conditional nobody
re-reads.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _ROOT / ".github" / "workflows"

# A hardcoded calendar date, e.g. 2026-08-06.
_DATE_LITERAL = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A read of the CURRENT date: `date -u +%F`, `$(date +%s)`, `date --utc`, ...
_CURRENT_DATE_READ = re.compile(r"\$\(\s*date\b|\bdate\s+(?:-|\+)")
# A literal date standing on either side of a shell/expression comparison.
_DATE_COMPARISON = re.compile(
    r"(?:[<>=!]=?|-(?:lt|le|gt|ge|eq|ne))\s*\"?'?\d{4}-\d{2}-\d{2}"
    r"|\d{4}-\d{2}-\d{2}\"?'?\s*(?:[<>=!]=?|-(?:lt|le|gt|ge|eq|ne))\b"
)


def _workflow_files() -> list[Path]:
    if not _WORKFLOWS.is_dir():
        return []
    return sorted(p for p in _WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})


def test_the_workflow_directory_is_where_this_guard_thinks_it_is() -> None:
    """A guard that silently scans nothing is worse than no guard."""
    assert _workflow_files(), f"no workflow files found under {_WORKFLOWS}"


def test_no_workflow_gates_on_a_hardcoded_date() -> None:
    offenders: list[str] = []
    for path in _workflow_files():
        text = path.read_text(encoding="utf-8")
        reads_now = bool(_CURRENT_DATE_READ.search(text))
        for number, line in enumerate(text.splitlines(), start=1):
            has_literal = bool(_DATE_LITERAL.search(line))
            if _DATE_COMPARISON.search(line) or (has_literal and reads_now):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, (
        "these workflow lines gate on a hardcoded calendar date, which is a check that "
        "changes verdict with the wall clock instead of with the evidence:\n" + "\n".join(offenders)
    )
