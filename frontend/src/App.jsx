import React, { useState } from "react";
import ScoreGauge from "./components/ScoreGauge.jsx";
import KeywordChips from "./components/KeywordChips.jsx";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SAMPLE_RESUME = `Arif — B.Tech IT Student
Skills: C, Python, Java, basic SQL
Projects: Built an Android app that converts sign language gestures to voice output
for deaf users. Built a resume builder tool for classmates.
Education: B.Tech in Information Technology, 2024-2028.`;

const SAMPLE_JD = `We're hiring a Data Analyst intern. Required: Python, SQL, Excel, data
visualization (Power BI or Tableau). Nice to have: statistics background, Git,
machine learning exposure. Looking for candidates with a Projects section and a
Certifications section.`;

export default function App() {
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [status, setStatus] = useState("idle"); // idle | running | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const runAgent = async () => {
    setStatus("running");
    setError("");
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText, job_description: jdText }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      const data = await res.json();
      setResult(data);
      setStatus("done");
    } catch (err) {
      setError(err.message || "Something went wrong.");
      setStatus("error");
    }
  };

  const loadSample = () => {
    setResumeText(SAMPLE_RESUME);
    setJdText(SAMPLE_JD);
  };

  const canRun = resumeText.trim().length >= 20 && jdText.trim().length >= 20 && status !== "running";

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__eyebrow">IBM SkillsBuild · Autonomous Agent</div>
        <h1 className="app__title">CareerPilot AI</h1>
        <p className="app__subtitle">
          Feed it a resume and a job description. It parses the requirements, scores
          the match, and drafts fixes — no manual review steps in between.
        </p>
      </header>

      <main className="layout">
        <section className="panel panel--input">
          <div className="panel__header">
            <span className="panel__index">01</span>
            <h2>Load the inputs</h2>
          </div>

          <label className="field-label" htmlFor="resume">
            Resume (plain text)
          </label>
          <textarea
            id="resume"
            className="field-textarea"
            placeholder="Paste your resume text here..."
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            rows={10}
          />

          <label className="field-label" htmlFor="jd">
            Target job description
          </label>
          <textarea
            id="jd"
            className="field-textarea"
            placeholder="Paste the job description you're applying to..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={8}
          />

          <div className="panel__actions">
            <button className="btn btn--ghost" type="button" onClick={loadSample}>
              Load sample data
            </button>
            <button className="btn btn--primary" type="button" disabled={!canRun} onClick={runAgent}>
              {status === "running" ? "Running agent…" : "Run CareerPilot Agent"}
            </button>
          </div>

          {status === "running" && (
            <ol className="pipeline-status">
              <li>Parsing job description into a requirements spec…</li>
              <li>Matching resume keywords deterministically…</li>
              <li>Drafting suggestions and rewritten bullets…</li>
              <li>Self-reviewing output before returning it…</li>
            </ol>
          )}

          {status === "error" && <p className="error-text">{error}</p>}
        </section>

        <section className="panel panel--results">
          <div className="panel__header">
            <span className="panel__index">02</span>
            <h2>Agent output</h2>
          </div>

          {!result && status !== "running" && (
            <div className="empty-state">
              Run the agent to see a match score, keyword gaps, and rewritten bullet
              points here.
            </div>
          )}

          {result && (
            <div className="results">
              <ScoreGauge score={result.match_score} />

              <KeywordChips label="Matched must-haves" items={result.matched_must_have} tone="good" />
              <KeywordChips label="Missing must-haves" items={result.missing_must_have} tone="bad" />
              <KeywordChips label="Matched nice-to-haves" items={result.matched_nice_to_have} tone="good" />
              <KeywordChips label="Missing nice-to-haves" items={result.missing_nice_to_have} tone="bad" />

              {result.missing_sections.length > 0 && (
                <div className="chip-strip">
                  <div className="chip-strip__label">Missing sections</div>
                  <div className="chip-strip__row">
                    {result.missing_sections.map((s) => (
                      <span key={s} className="chip chip--bad">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {result.suggestions.length > 0 && (
                <div className="suggestions">
                  <h3>Fix these next</h3>
                  <ul>
                    {result.suggestions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.rewritten_bullets.length > 0 && (
                <div className="bullets">
                  <h3>Rewritten bullets</h3>
                  {result.rewritten_bullets.map((b, i) => (
                    <div className="bullet-card" key={i}>
                      <div className="bullet-card__original">{b.original}</div>
                      <div className="bullet-card__arrow">→</div>
                      <div className="bullet-card__improved">{b.improved}</div>
                    </div>
                  ))}
                </div>
              )}

              {result.reviewer_notes && (
                <p className="reviewer-notes">Self-review note: {result.reviewer_notes}</p>
              )}
            </div>
          )}
        </section>
      </main>

      <footer className="app__footer">
        DUO DYNAMICS — CareerPilot AI · Agent: Parse → Match → Generate → Self-review
      </footer>
    </div>
  );
}
