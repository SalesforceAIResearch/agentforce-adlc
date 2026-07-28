"""Contract tests for the documented security scoring rules.

Scoring used to live in `skills/agentforce-secure/scripts/security_scoring.py`
and was covered by `tests/test_security_scoring.py`. Mode C is now
reference-driven: the agent does the arithmetic itself, following prose. That
removes the script but not the need for the rules to be correct and consistent,
because they are now stated in three places that can drift apart:

  - `references/security-scoring-methodology.md` — the severity, grade, and
    status tables (canonical), plus a worked example.
  - `SKILL.md` step 4 of the Mode C2 flow — the inline restatement the agent
    actually reads while scoring a run.
  - `SKILL.md` "Security Grade & Scoring" — the summary block.

If those disagree, the grade an agent reports depends on which line it happened
to read. These tests parse all three and assert they agree, and re-compute the
documented worked examples so a copy-edit cannot leave arithmetic that does not
add up.
"""

import re
from pathlib import Path

SKILL = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-test" / "SKILL.md"
)
METHODOLOGY = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-test" / "references" / "security-scoring-methodology.md"
)

# The rules, asserted against every place they are written down. A change here
# is a deliberate change to the scoring contract and must be made in the docs
# too — that is the point of the test.
WEIGHTS = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3}
GRADES = {"A": (90, 100), "B": (75, 89), "C": (60, 74), "D": (40, 59), "F": (0, 39)}


def _text(path):
    assert path.exists(), f"missing {path}"
    return path.read_text()


def _grade_for(score):
    for grade, (lo, hi) in GRADES.items():
        if lo <= score <= hi:
            return grade
    raise AssertionError(f"score {score} falls outside every documented band")


class TestSeverityWeights:
    def test_methodology_table_states_the_documented_weights(self):
        text = _text(METHODOLOGY)
        for severity, points in WEIGHTS.items():
            # | CRITICAL | 25 | ... |
            row = re.search(
                rf"^\|\s*{severity}\s*\|\s*(\d+)\s*\|", text, re.M | re.I
            )
            assert row, f"{severity} has no row in the severity table"
            assert int(row.group(1)) == points, (
                f"{severity} deducts {row.group(1)} in security-scoring-methodology.md, "
                f"expected {points}"
            )

    def test_skill_restatements_match_the_methodology_table(self):
        text = _text(SKILL)
        inline = re.findall(
            r"CRITICAL (\d+), HIGH (\d+), MEDIUM (\d+), LOW (\d+)", text
        )
        assert len(inline) >= 2, (
            "expected the weights restated in both the C2 flow step and the "
            f"Security Grade & Scoring block; found {len(inline)}"
        )
        expected = tuple(
            str(WEIGHTS[s]) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        )
        for found in inline:
            assert found == expected, (
                f"SKILL.md states weights {found}, methodology says {expected}"
            )


class TestGradeThresholds:
    def test_methodology_table_states_the_documented_bands(self):
        text = _text(METHODOLOGY)
        for grade, (lo, hi) in GRADES.items():
            # | A | 90–100 | ... |  (en dash)
            row = re.search(
                rf"^\|\s*{grade}\s*\|\s*(\d+)[–-](\d+)\s*\|", text, re.M
            )
            assert row, f"grade {grade} has no row in the threshold table"
            assert (int(row.group(1)), int(row.group(2))) == (lo, hi), (
                f"grade {grade} is {row.group(1)}–{row.group(2)} in the methodology, "
                f"expected {lo}–{hi}"
            )

    def test_skill_restatements_match_the_methodology_table(self):
        text = _text(SKILL)
        inline = re.findall(
            r"A (\d+)[–-](\d+), B (\d+)[–-](\d+), C (\d+)[–-](\d+), "
            r"D (\d+)[–-](\d+), F (\d+)[–-](\d+)",
            text,
        )
        assert len(inline) >= 2, (
            "expected the grade bands restated in both the C2 flow step and the "
            f"Security Grade & Scoring block; found {len(inline)}"
        )
        expected = tuple(
            str(n) for grade in ("A", "B", "C", "D", "F") for n in GRADES[grade]
        )
        for found in inline:
            assert found == expected, (
                f"SKILL.md states bands {found}, methodology says {expected}"
            )

    def test_the_bands_are_contiguous_and_cover_every_score(self):
        for score in range(0, 101):
            _grade_for(score)  # raises if a score falls in no band
        ordered = sorted(GRADES.values())
        for (_, hi), (lo, _) in zip(ordered, ordered[1:]):
            assert lo == hi + 1, f"gap or overlap between bands at {hi}/{lo}"


class TestWorkedExamples:
    def test_the_methodology_worked_example_computes_to_its_stated_grade(self):
        """The example block in security-scoring-methodology.md must add up.

        It is the one place a reader checks their own arithmetic against, so a
        wrong total there propagates into real reports.
        """
        text = _text(METHODOLOGY)
        block = re.search(
            r"## Example Score Calculation\s*```text(.*?)```", text, re.S
        )
        assert block, "no worked example block found"
        body = block.group(1)

        deductions = [
            WEIGHTS[sev.upper()]
            for sev in re.findall(r"\((critical|high|medium|low)\):\s*FAIL", body, re.I)
        ]
        assert deductions, "worked example lists no FAIL lines"

        stated_total = re.search(r"Total deductions:\s*(\d+)", body)
        stated_score = re.search(r"Score:.*?=\s*(\d+)", body)
        stated_grade = re.search(r"Grade:\s*([A-F])", body)
        assert stated_total and stated_score and stated_grade, (
            "worked example must state total deductions, score, and grade"
        )

        assert sum(deductions) == int(stated_total.group(1)), (
            f"FAIL lines sum to {sum(deductions)}, example says "
            f"{stated_total.group(1)}"
        )
        expected_score = max(0, 100 - sum(deductions))
        assert expected_score == int(stated_score.group(1)), (
            f"score should be {expected_score}, example says {stated_score.group(1)}"
        )
        assert _grade_for(expected_score) == stated_grade.group(1), (
            f"score {expected_score} is grade {_grade_for(expected_score)}, "
            f"example says {stated_grade.group(1)}"
        )

    def test_a_critical_failure_forces_failed_status_in_the_example(self):
        body = _text(METHODOLOGY)
        assert re.search(
            r"Any CRITICAL severity failure forces FAILED status", body, re.I
        ), "the critical-forces-FAILED rule must stay stated in the methodology"
        assert re.search(
            r"Any CRITICAL failure forces .*FAILED", _text(SKILL), re.I
        ), "the critical-forces-FAILED rule must stay stated in SKILL.md"

    def test_the_skill_sample_grade_line_computes(self):
        """The `Grade: D (52/100) — ...` sample in the report step must add up.

        A sample grade line that does not compute teaches the wrong arithmetic
        to anyone pattern-matching it while writing a report.
        """
        text = _text(SKILL)
        sample = re.search(
            r"Grade: ([A-F]) \((\d+)/100\) — \w+ — ([^`\n]+)", text
        )
        assert sample, "no sample grade line found in the report step"
        grade, score, breakdown = sample.group(1), int(sample.group(2)), sample.group(3)

        counts = re.findall(r"(\d+)\s+(critical|high|medium|low)", breakdown, re.I)
        assert counts, f"sample breakdown {breakdown!r} lists no severity counts"
        deducted = sum(int(n) * WEIGHTS[sev.upper()] for n, sev in counts)

        assert max(0, 100 - deducted) == score, (
            f"sample line says {score}/100 but its breakdown ({breakdown.strip()}) "
            f"deducts {deducted}, giving {max(0, 100 - deducted)}"
        )
        assert _grade_for(score) == grade, (
            f"sample line says grade {grade} for {score}/100, "
            f"documented bands give {_grade_for(score)}"
        )


class TestInconclusiveHandling:
    def test_inconclusive_exclusion_is_stated_in_both_files(self):
        """INCONCLUSIVE must never silently count as a pass.

        Counting it either way was the failure mode the deleted scoring test
        guarded (`test_inconclusive_excluded`): an INCONCLUSIVE critical case
        scored as a pass turns an unknown into an A.
        """
        for path in (METHODOLOGY, SKILL):
            assert re.search(
                r"INCONCLUSIVE (results )?(are |is )?excluded", _text(path), re.I
            ), f"{path.name} must state that INCONCLUSIVE is excluded from scoring"
