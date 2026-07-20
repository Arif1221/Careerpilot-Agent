"""
CareerPilot AI — ATS Resume Scoring Agent
==========================================

Gemini Version
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from google import genai

MODEL = os.environ.get(
    "CAREERPILOT_MODEL",
    "gemini-3.1-flash-lite"
)


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

def _client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not found in environment variables."
        )

    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# JSON Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """
    Gemini sometimes wraps JSON inside markdown or adds explanations.
    This extracts the first valid JSON object.
    """

    text = text.strip()

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        text = text[start:end + 1]

    return json.loads(text)


# ---------------------------------------------------------------------------
# Gemini Call Helper
# ---------------------------------------------------------------------------

def _call_json(
    client,
    system: str,
    user: str,
    max_tokens: int = 1024,
) -> dict[str, Any]:

    prompt = f"""
SYSTEM

{system}

-------------------------

USER

{user}

-------------------------

Return ONLY valid JSON.

Do NOT explain anything.

Do NOT wrap JSON inside markdown.

Output must begin with "{{" and end with "}}".
"""

    try:

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )

        raw = response.text

        return _extract_json(raw)

    except Exception as exc:
        raise RuntimeError(
            f"Gemini request failed:\n{exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Matching Helpers
# ---------------------------------------------------------------------------

def _normalize(word: str) -> str:
    return re.sub(
        r"[^a-z0-9+.# ]",
        "",
        word.lower(),
    ).strip()


def _keyword_present(
    keyword: str,
    resume_text: str,
) -> bool:

    kw = _normalize(keyword)

    if not kw:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(kw)
        + r"(?![a-z0-9])"
    )

    return (
        re.search(
            pattern,
            resume_text.lower(),
        )
        is not None
    )


# ---------------------------------------------------------------------------
# Result Object
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

    def to_dict(self):

        return self.__dict__


# ---------------------------------------------------------------------------
# CareerPilot Agent
# ---------------------------------------------------------------------------

class CareerPilotAgent:

    """
    PARSE
        ↓
    MATCH
        ↓
    GENERATE
        ↓
    SELF REVIEW
    """

    def __init__(self, client=None):

        self.client = client or _client()

    # -------------------------------------------------------
    # STEP 1
    # -------------------------------------------------------

    def parse_job_description(
        self,
        jd_text: str,
    ) -> dict[str, Any]:

        system = (
            "You are a technical recruiter. "
            "Extract ONLY valid JSON. "
            'Schema: {"must_have_keywords":[],"nice_to_have_keywords":[],"expected_sections":[]}. '
            "No markdown."
        )

        return _call_json(
            self.client,
            system,
            jd_text,
            max_tokens=700,
        )
    # -------------------------------------------------------
    # STEP 2
    # -------------------------------------------------------

    def match_resume(
        self,
        resume_text: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:

        must = spec.get("must_have_keywords", [])
        nice = spec.get("nice_to_have_keywords", [])
        expected_sections = spec.get("expected_sections", [])

        matched_must = [
            k for k in must
            if _keyword_present(k, resume_text)
        ]

        missing_must = [
            k for k in must
            if k not in matched_must
        ]

        matched_nice = [
            k for k in nice
            if _keyword_present(k, resume_text)
        ]

        missing_nice = [
            k for k in nice
            if k not in matched_nice
        ]

        missing_sections = [
            s
            for s in expected_sections
            if not re.search(
                re.escape(s),
                resume_text,
                re.IGNORECASE,
            )
        ]

        must_ratio = (
            len(matched_must) / len(must)
            if must else 1.0
        )

        nice_ratio = (
            len(matched_nice) / len(nice)
            if nice else 1.0
        )

        section_penalty = 5 * len(missing_sections)

        score = (
            round(
                must_ratio * 70
                + nice_ratio * 30
            )
            - section_penalty
        )

        score = max(0, min(100, score))

        return {

            "match_score": score,

            "matched_must_have": matched_must,

            "missing_must_have": missing_must,

            "matched_nice_to_have": matched_nice,

            "missing_nice_to_have": missing_nice,

            "missing_sections": missing_sections,
        }

    # -------------------------------------------------------
    # STEP 3
    # -------------------------------------------------------

    def generate_suggestions(
        self,
        resume_text: str,
        jd_text: str,
        match: dict[str, Any],
    ) -> dict[str, Any]:

        system = (
            "You are an ATS Resume Expert.\n"
            "Return ONLY JSON.\n\n"
            'Schema:\n'
            '{'
            '"suggestions":[string],'
            '"rewritten_bullets":['
            '{"original":string,"improved":string}'
            ']'
            '}'
        )

        user = json.dumps(

            {

                "resume_text": resume_text,

                "job_description": jd_text,

                "missing_must_have":
                    match["missing_must_have"],

                "missing_nice_to_have":
                    match["missing_nice_to_have"],

                "missing_sections":
                    match["missing_sections"],

            },

            indent=2,

        )

        return _call_json(

            self.client,

            system,

            user,

            max_tokens=1200,

        )

    # -------------------------------------------------------
    # STEP 4
    # -------------------------------------------------------

    def self_review(

        self,

        resume_text: str,

        generated: dict[str, Any],

    ) -> dict[str, Any]:

        system = (
            "Review the AI output.\n"
            "Remove hallucinations.\n"
            "Return ONLY JSON.\n\n"
            'Schema:{'
            '"suggestions":[string],'
            '"rewritten_bullets":['
            '{"original":string,"improved":string}'
            '],'
            '"reviewer_notes":string'
            '}'
        )

        user = json.dumps(

            {

                "resume_text": resume_text,

                "draft": generated,

            },

            indent=2,

        )

        return _call_json(

            self.client,

            system,

            user,

            max_tokens=1200,

        )

    # -------------------------------------------------------
    # RUN PIPELINE
    # -------------------------------------------------------

    def run(

        self,

        resume_text: str,

        jd_text: str,

    ) -> AgentResult:

        spec = self.parse_job_description(
            jd_text
        )

        match = self.match_resume(
            resume_text,
            spec,
        )

        draft = self.generate_suggestions(
            resume_text,
            jd_text,
            match,
        )

        final = self.self_review(
            resume_text,
            draft,
        )

        return AgentResult(

            match_score=match["match_score"],

            matched_must_have=match[
                "matched_must_have"
            ],

            missing_must_have=match[
                "missing_must_have"
            ],

            matched_nice_to_have=match[
                "matched_nice_to_have"
            ],

            missing_nice_to_have=match[
                "missing_nice_to_have"
            ],

            missing_sections=match[
                "missing_sections"
            ],

            suggestions=final.get(
                "suggestions",
                [],
            ),

            rewritten_bullets=final.get(
                "rewritten_bullets",
                [],
            ),

            reviewer_notes=final.get(
                "reviewer_notes",
                "",
            ),
        )


# -------------------------------------------------------
# CLI TEST
# -------------------------------------------------------

if __name__ == "__main__":

    sample_resume = """
Arif
B.Tech IT Student

Skills:
Python
Java
SQL
Git

Projects:
Android Sign Language Translator

Education:
B.Tech Information Technology
"""

    sample_jd = """
Hiring Data Analyst Intern.

Required:

Python

SQL

Excel

Power BI

Nice to Have:

Git

Machine Learning

Statistics

Need Projects section and Certifications section.
"""

    agent = CareerPilotAgent()

    result = agent.run(
        sample_resume,
        sample_jd,
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=4,
        )
    )
