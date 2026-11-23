"""Unit tests for the CareerPilot agent.

Gemini is never called: the matching step is pure Python, and the LLM steps
use a fake client that returns canned JSON.
"""

import json

import pytest

from agent import (
    AgentResult,
    CareerPilotAgent,
    _extract_json,
    _keyword_present,
    _normalize,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """Mimics genai.Client: client.models.generate_content(...) -> .text"""

    def __init__(self, replies):
        self._replies = list(replies)
        self.prompts = []
        self.models = self

    def generate_content(self, model, contents):
        self.prompts.append(contents)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _FakeResponse(reply)


def agent_with(*replies):
    return CareerPilotAgent(client=FakeClient(replies))


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_strips_markdown_fence(self):
        assert _extract_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}

    def test_ignores_text_around_the_object(self):
        assert _extract_json('Sure! Here it is: {"ok": true} Hope that helps.') == {"ok": True}

    def test_raises_when_there_is_no_json(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("no json here")


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercases_and_trims(self):
        assert _normalize("  Python ") == "python"

    def test_keeps_tech_symbols(self):
        assert _normalize("C++") == "c++"
        assert _normalize("C#") == "c#"
        assert _normalize("Node.js") == "node.js"


class TestKeywordPresent:
    @pytest.mark.parametrize("kw", ["python", "PYTHON", "Python"])
    def test_case_insensitive(self, kw):
        assert _keyword_present(kw, "Skills: Python, SQL")

    def test_whole_word_only(self):
        # "Java" must not match inside "JavaScript"
        assert not _keyword_present("Java", "Skills: JavaScript")
        assert _keyword_present("Java", "Skills: Java, JavaScript")

    def test_symbols(self):
        assert _keyword_present("C++", "Languages: C, C++")
        assert not _keyword_present("C++", "Languages: C")
        assert _keyword_present("Node.js", "Backend: Node.js and Express")

    def test_multi_word(self):
        assert _keyword_present("Power BI", "Tools: Excel, Power BI")

    def test_empty_keyword_is_never_present(self):
        assert not _keyword_present("", "anything")
        assert not _keyword_present("!!!", "anything")

    @pytest.mark.xfail(
        reason="Known bug: _normalize strips '/' and '-', so 'CI/CD' becomes 'cicd' "
        "and no longer matches the resume text.",
        strict=True,
    )
    def test_slash_and_hyphen_keywords(self):
        assert _keyword_present("CI/CD", "Set up CI/CD with GitHub Actions")


# ---------------------------------------------------------------------------
# Scoring (match_resume)
# ---------------------------------------------------------------------------

RESUME = """
Arif
Skills: Python, SQL, Git
Projects: CareerPilot
Education: B.Tech IT
"""


class TestMatchResume:
    def setup_method(self):
        self.agent = CareerPilotAgent(client=FakeClient([]))

    def test_perfect_match_scores_100(self):
        spec = {
            "must_have_keywords": ["Python", "SQL"],
            "nice_to_have_keywords": ["Git"],
            "expected_sections": ["Projects", "Education"],
        }
        m = self.agent.match_resume(RESUME, spec)
        assert m["match_score"] == 100
        assert m["missing_must_have"] == []
        assert m["missing_sections"] == []

    def test_weights_must_have_70_and_nice_to_have_30(self):
        spec = {
            "must_have_keywords": ["Python", "Excel"],       # 1 of 2 -> 35
            "nice_to_have_keywords": ["Git", "Statistics"],  # 1 of 2 -> 15
        }
        m = self.agent.match_resume(RESUME, spec)
        assert m["match_score"] == 50
        assert m["matched_must_have"] == ["Python"]
        assert m["missing_must_have"] == ["Excel"]
        assert m["matched_nice_to_have"] == ["Git"]
        assert m["missing_nice_to_have"] == ["Statistics"]

    def test_each_missing_section_costs_5_points(self):
        spec = {"expected_sections": ["Certifications", "Experience"]}
        m = self.agent.match_resume(RESUME, spec)
        assert m["missing_sections"] == ["Certifications", "Experience"]
        assert m["match_score"] == 90

    def test_score_never_goes_below_zero(self):
        spec = {
            "must_have_keywords": ["Excel"],
            "nice_to_have_keywords": ["Tableau"],
            "expected_sections": [f"Section{i}" for i in range(10)],
        }
        assert self.agent.match_resume(RESUME, spec)["match_score"] == 0

    def test_empty_spec_scores_100(self):
        assert self.agent.match_resume(RESUME, {})["match_score"] == 100

    def test_keeps_original_keyword_spelling(self):
        m = self.agent.match_resume(RESUME, {"must_have_keywords": ["PYTHON"]})
        assert m["matched_must_have"] == ["PYTHON"]


# ---------------------------------------------------------------------------
# Full pipeline with a fake LLM
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_runs_all_four_steps_and_uses_the_reviewed_output(self):
        agent = agent_with(
            json.dumps({"must_have_keywords": ["Python", "Excel"], "nice_to_have_keywords": [], "expected_sections": []}),
            json.dumps({"suggestions": ["draft"], "rewritten_bullets": []}),
            "```json\n"
            + json.dumps({
                "suggestions": ["Add Excel"],
                "rewritten_bullets": [{"original": "Did stuff", "improved": "Built X"}],
                "reviewer_notes": "Removed one invented claim",
            })
            + "\n```",
        )
        result = agent.run(RESUME, "Need Python and Excel")

        assert isinstance(result, AgentResult)
        assert result.match_score == 65  # 1 of 2 must-have (35) + no nice-to-have list (full 30)
        assert result.missing_must_have == ["Excel"]
        # The final answer comes from the self-review step, not the draft
        assert result.suggestions == ["Add Excel"]
        assert result.reviewer_notes == "Removed one invented claim"
        assert result.rewritten_bullets == [{"original": "Did stuff", "improved": "Built X"}]
        assert len(agent.client.prompts) == 3

    def test_missing_keywords_are_sent_to_the_generator(self):
        agent = agent_with(
            json.dumps({"must_have_keywords": ["Excel"]}),
            json.dumps({"suggestions": []}),
            json.dumps({}),
        )
        agent.run(RESUME, "Need Excel")
        assert '"Excel"' in agent.client.prompts[1]

    def test_review_without_optional_fields_gives_empty_defaults(self):
        agent = agent_with(json.dumps({}), json.dumps({}), json.dumps({}))
        result = agent.run(RESUME, "Anything")
        assert result.suggestions == []
        assert result.rewritten_bullets == []
        assert result.reviewer_notes == ""

    def test_llm_failure_becomes_runtime_error(self):
        agent = agent_with(ConnectionError("network down"))
        with pytest.raises(RuntimeError, match="Gemini request failed"):
            agent.run(RESUME, "Anything")

    def test_invalid_json_from_llm_becomes_runtime_error(self):
        agent = agent_with("I cannot help with that.")
        with pytest.raises(RuntimeError):
            agent.run(RESUME, "Anything")
