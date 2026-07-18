"""
CareerPilot AI — ATS Resume Scoring Agent
==========================================

This is the "AI agent" for the assignment. It is NOT a single prompt-in,
text-out call. It runs a 4-step autonomous pipeline every time it is
invoked, with no manual steps in between:

    1. PARSE     (LLM)   -> turn a messy job description into a structured spec
    2. MATCH     (code)  -> deterministically score the resume against that spec
    3. GENERATE  (LLM)   -> write concrete fixes + rewritten bullets for the gaps
    4. SELF-REVIEW (LLM) -> re-check its own suggestions before returning them

Step 2 is deliberately NOT an LLM call. Match scores need to be reproducible
(same inputs -> same score every time), so keyword matching is done in plain
Python. The LLM is used for the two things it's actually good at: turning
unstructured text into structure, and writing tailored, well-worded advice.

Run this file directly for a quick CLI test without starting the API:
    python agent.py
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic

MODEL = os.environ.get("CAREERPILOT_MODEL", "claude-haiku-4-5-20251001")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _client() -> Anthropic:
    # Anthropic() reads ANTHROPIC_API_KEY from the environment automatically.
    return Anthropic()


def _extract_json(text: str) -> dict[str, Any]:
    """Claude sometimes wraps JSON in ```json fences even when asked not to.
    Strip those defensively before parsing."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _call_json(client: Anthropic, system: str, user: str, max_tokens: int = 1024) -> dict[str, Any]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(block.text for block in resp.content if block.type == "text")
    try:
        return _extract_json(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Agent step returned non-JSON output: {raw[:300]}") from exc


def _normalize(word: str) -> str:
    return re.sub(r"[^a-z0-9+.# ]", "", word.lower()).strip()


def _keyword_present(keyword: str, resume_text: str) -> bool:
    """Word-boundary-ish match so 'R' doesn't match every word containing r."""
    kw = _normalize(keyword)
    if not kw:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
    return re.search(pattern, resume_text.lower()) is not None


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    match_score: int
    matched_must_have: list[str] = field(default_factory=list)
    missing_must_have: list[str] = field(default_factory=list)
    matched_nice_to_have: list[str] = field(default_factory=list)
    missing_nice_to_have: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    rewritten_bullets: list[dict[str, str]] = field(default_factory=list)
    reviewer_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

class CareerPilotAgent:
    """Runs the full PARSE -> MATCH -> GENERATE -> SELF-REVIEW pipeline."""

    def __init__(self, client: Anthropic | None = None):
        self.client = client or _client()

    # Step 1 ------------------------------------------------------------
    def parse_job_description(self, jd_text: str) -> dict[str, Any]:
        system = (
            "You are a technical recruiter's assistant. Extract a structured "
            "requirements spec from a job description. Respond with ONLY raw JSON, "
            "no markdown fences, no commentary. Schema: "
            '{"must_have_keywords": [string], "nice_to_have_keywords": [string], '
            '"expected_sections": [string]}. '
            "must_have_keywords: 6-12 hard skills/tools/technologies explicitly required. "
            "nice_to_have_keywords: 4-8 bonus skills mentioned as preferred/a plus. "
            "expected_sections: resume sections this role would expect to see, from "
            "this fixed vocabulary only: Projects, Experience, Skills, Education, "
            "Certifications, Achievements."
        )
        return _call_json(self.client, system, jd_text, max_tokens=700)

    # Step 2 ------------------------------------------------------------
    def match_resume(self, resume_text: str, spec: dict[str, Any]) -> dict[str, Any]:
        must = spec.get("must_have_keywords", [])
        nice = spec.get("nice_to_have_keywords", [])
        expected_sections = spec.get("expected_sections", [])

        matched_must = [k for k in must if _keyword_present(k, resume_text)]
        missing_must = [k for k in must if k not in matched_must]
        matched_nice = [k for k in nice if _keyword_present(k, resume_text)]
        missing_nice = [k for k in nice if k not in matched_nice]

        missing_sections = [
            s for s in expected_sections
            if not re.search(re.escape(s), resume_text, re.IGNORECASE)
        ]

        # Deterministic score: must-haves matter far more than nice-to-haves.
        must_ratio = len(matched_must) / len(must) if must else 1.0
        nice_ratio = len(matched_nice) / len(nice) if nice else 1.0
        section_penalty = 5 * len(missing_sections)
        score = round(must_ratio * 70 + nice_ratio * 30) - section_penalty
        score = max(0, min(100, score))

        return {
            "match_score": score,
            "matched_must_have": matched_must,
            "missing_must_have": missing_must,
            "matched_nice_to_have": matched_nice,
            "missing_nice_to_have": missing_nice,
            "missing_sections": missing_sections,
        }

    # Step 3 ------------------------------------------------------------
    def generate_suggestions(
        self, resume_text: str, jd_text: str, match: dict[str, Any]
    ) -> dict[str, Any]:
        system = (
            "You are an ATS resume coach. You'll be given a resume, a job description, "
            "and a computed keyword-gap analysis. Write concrete, specific fixes -- "
            "never generic advice like 'add more keywords'. "
            "Respond with ONLY raw JSON, no markdown fences. Schema: "
            '{"suggestions": [string], "rewritten_bullets": '
            '[{"original": string, "improved": string}]}. '
            "suggestions: 3-6 short, specific action items referencing the ACTUAL "
            "missing keywords/sections given below. "
            "rewritten_bullets: pick 2-3 existing weak bullet points from the resume "
            "text and rewrite them to naturally include missing must-have keywords "
            "where truthful and plausible, using strong action verbs and metrics."
        )
        user = json.dumps(
            {
                "resume_text": resume_text,
                "job_description": jd_text,
                "missing_must_have": match["missing_must_have"],
                "missing_nice_to_have": match["missing_nice_to_have"],
                "missing_sections": match["missing_sections"],
            }
        )
        return _call_json(self.client, system, user, max_tokens=1200)

    # Step 4 ------------------------------------------------------------
    def self_review(
        self, resume_text: str, generated: dict[str, Any]
    ) -> dict[str, Any]:
        system = (
            "You are a strict editor reviewing another AI's resume suggestions "
            "before they're shown to a student. Remove or fix any suggestion that: "
            "(a) references a skill/bullet that doesn't actually appear in the resume, "
            "(b) is vague filler advice, or (c) fabricates an achievement/metric not "
            "implied by the original resume. Respond with ONLY raw JSON, no fences. "
            "Schema: {\"suggestions\": [string], "
            '"rewritten_bullets": [{"original": string, "improved": string}], '
            '"reviewer_notes": string}. '
            "reviewer_notes: one short sentence on what you removed or fixed, or "
            "\"No issues found.\" if nothing needed changing."
        )
        user = json.dumps({"resume_text": resume_text, "draft": generated})
        return _call_json(self.client, system, user, max_tokens=1200)

    # Orchestration -------------------------------------------------------
    def run(self, resume_text: str, jd_text: str) -> AgentResult:
        spec = self.parse_job_description(jd_text)
        match = self.match_resume(resume_text, spec)
        draft = self.generate_suggestions(resume_text, jd_text, match)
        final = self.self_review(resume_text, draft)

        return AgentResult(
            match_score=match["match_score"],
            matched_must_have=match["matched_must_have"],
            missing_must_have=match["missing_must_have"],
            matched_nice_to_have=match["matched_nice_to_have"],
            missing_nice_to_have=match["missing_nice_to_have"],
            missing_sections=match["missing_sections"],
            suggestions=final.get("suggestions", []),
            rewritten_bullets=final.get("rewritten_bullets", []),
            reviewer_notes=final.get("reviewer_notes", ""),
        )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_resume = """
    Arif — B.Tech IT Student
    Skills: C, Python, Java, basic SQL
    Projects: Built an Android app that converts sign language gestures to voice
    output for deaf users. Built a resume builder tool.
    Education: B.Tech in Information Technology, 2024-2028.
    """
    sample_jd = """
    We're hiring a Data Analyst intern. Required: Python, SQL, Excel, data
    visualization (Power BI or Tableau). Nice to have: statistics background,
    Git, machine learning exposure. Looking for candidates with a Projects
    section and a Certifications section.
    """

    agent = CareerPilotAgent()
    result = agent.run(sample_resume, sample_jd)
    print(json.dumps(result.to_dict(), indent=2))
