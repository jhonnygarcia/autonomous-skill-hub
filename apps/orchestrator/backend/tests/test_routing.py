"""What's under test here is the DIRECTION of failure, not the parsing.

Routing is an optimization: a survey of an irrelevant repo comes back
`not-touched` and costs one session. Skipping a repo that mattered costs the whole
ticket, and nothing downstream detects it — the analysis looks complete.

So every ambiguous case widens to the full list. There is no path by which a
parsing failure narrows what gets surveyed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import repos_to_survey  # noqa: E402

ALL_LABELS = ["back", "front", "auth"]

CASES = [
    # (text, expected, why)
    ("SONDEAR: back, front", ["back", "front"], "the normal case"),
    ("SONDEAR: BACK ,  Front ", ["back", "front"], "case and spacing don't matter"),
    ("SONDEAR: front, back", ["back", "front"], "normalized to the mounting order"),
    ("SONDEAR: back, back", ["back"], "deduplicated"),
    ("SONDEAR: back", ["back"], "a single one: the runner short-circuits"),
    ("SONDEAR: back, front, auth", ALL_LABELS, "all of them, spelled out"),
    # Everything below widens.
    ("no hay ninguna linea", ALL_LABELS, "absent"),
    ("SONDEAR:", ALL_LABELS, "empty"),
    ("SONDEAR:    ", ALL_LABELS, "only spaces"),
    ("SONDEAR: back, frontend", ALL_LABELS, "one unknown label voids the whole line"),
    ("SONDEAR: ninguno", ALL_LABELS, "all unknown"),
    ("SONDEAR: ,", ALL_LABELS, "separators with nothing between them"),
    ("sondear: back", ALL_LABELS, "the keyword is a literal: lowercase isn't it"),
]


@pytest.mark.parametrize("text,expected,why", CASES)
def test_routing(text, expected, why):
    assert repos_to_survey(text, ALL_LABELS) == expected, why


def test_the_last_line_wins():
    """Anchored on the last match for the same reason as `STAMP_RE`, and it isn't
    theoretical: the skill's body travels through the brief it writes, and its own
    example carries the literal `SONDEAR:`. Reading the first one would make the
    parser find the example instead of the decision."""
    brief = (
        "## Ejemplo del formato\n"
        "SONDEAR: back, front, auth\n"
        "\n"
        "## Enrutado\n"
        "SONDEAR: back\n"
    )
    assert repos_to_survey(brief, ALL_LABELS) == ["back"]


def test_an_unknown_label_does_not_take_the_known_ones_with_it_silently():
    """A partially valid line is the worst case: it looks like a decision and it's a
    typo. Surveying only what it got right would silently drop a repo — so the whole
    line is discarded and everything gets surveyed."""
    assert repos_to_survey("SONDEAR: back, frnot", ALL_LABELS) == ALL_LABELS


def test_no_labels_at_all():
    """A single-repo project never reaches the fan-out, but the function must not
    invent one."""
    assert repos_to_survey("SONDEAR: back", []) == []
