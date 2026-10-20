# Day 63 — Evaluation and Deployment

**Objective:** Measure whether the multi-agent system actually works (coordination, tool selection, evidence quality, failure recovery, latency, cost), deploy it, and document its limitations honestly.

---

## 📖 Theory

### Why evaluating a multi-agent system is harder

A single answer can look fine while something underneath is wrong: the wrong agent ran, a failure was hidden, a number was invented and then slipped past the Critic, or the run used five times the calls it needed. So you evaluate at two levels:

- **System level:** is the final result correct, honest, and labelled with the right status?
- **Component level:** did the router pick the right agents, did each agent use only its own tools, did the Critic catch what it should?

LLM output also varies from run to run, and a free-tier test set is small. That means conclusions have to be stated carefully.

### What to measure

| Area | Question | Check |
|---|---|---|
| **Coordination** | Did the right agents run, in a valid order, with correct handoffs? | Compare the agents actually called with the expected set; check the call log order |
| **Tool selection** | Did each agent use only its own tools? | Permission errors, call log |
| **Evidence quality** | Is every number and source in the report backed by evidence? | Re-run the number and URL checks on the final report (independently of the Critic) |
| **Honest status** | Does the report say what it is (verified, partial, insufficient evidence)? | Compare the status with the expected one |
| **Failure recovery** | Does it degrade gracefully and say so? | Inject failures and check the status and the limitations text |
| **Latency** | How long does a run take? | Wall-clock time per run |
| **Cost** | How much does a run use? | Number of LLM calls and tokens |
| **Value vs. a single agent** | Is the team better than Week 8's one agent on the same questions? | Run both and compare |

### The evaluation dataset (`evaluation/evaluation.csv`)

Principles:

- **Cover more than the happy path:** normal requests, requests that need only one agent, unclear requests, injected failures, Critic cases, and questions the data cannot answer.
- **Decide the expected result before running**, from the design rules, never by looking at what the system happened to output. Otherwise the dataset just agrees with the system.
- **Every row names what it expects:** the agents that should be called, the final status, text that must (or must not) appear.
- **Add a row for every bug you find**, so it cannot come back unnoticed.
- **Keep failing rows visible.** A dataset tuned until everything passes tells you nothing.

The 16 rows used this week:

| # | Category | Question | Injected failure | Expected agents called | Expected status |
|---|---|---|---|---|---|
| 1 | full investigation | Analyze our sales, research the market, and recommend what to do | none | research, analyst, strategy | `verified` |
| 2 | analyst only | What are our top products in June? | none | analyst | `findings_only` |
| 3 | research only | What market trends affect backpacks? | none | research | `findings_only` |
| 4 | false premise | Why did our revenue drop this month, and what should we do next? | none | analyst, strategy | `verified` |
| 5 | unclear request | hello | none | — | `needs_clarification` |
| 6 | unclear request | Tell me something interesting | none | — | `needs_clarification` |
| 7 | recommendations only | What should we do next? | none | analyst, strategy | `verified` |
| 8 | failure: research unavailable | Analyze our sales, research the market, and recommend what to do | research_unavailable | research, analyst, strategy | `verified` |
| 9 | failure: research crash | Analyze our sales, research the market, and recommend what to do | research_crash | research, analyst, strategy | `verified` |
| 10 | failure: analyst fails | Analyze our sales, research the market, and recommend what to do | analyst_fails | research, analyst | `insufficient_evidence` |
| 11 | critic: fixable invented number | Analyze our sales, research the market, and recommend what to do | invented_number_fixable | research, analyst, strategy | `verified` |
| 12 | critic: unfixable invented number | Analyze our sales, research the market, and recommend what to do | invented_number_unfixable | research, analyst, strategy | `not_fully_verified` |
| 13 | budget exhausted | Analyze our sales, research the market, and recommend what to do | budget_2 | research, analyst | `partial` |
| 14 | research only, research unavailable | What market trends affect backpacks? | research_unavailable | research | `insufficient_evidence` |
| 15 | entity not in the data | Why did our Tokyo store underperform? | none | analyst | `insufficient_evidence` |
| 16 | market research + recommendations | Research the market and recommend what to do | none | research, analyst, strategy | `verified` |

### Deterministic checks vs. judged checks

Most checks above are exact (status, agents called, text present, numbers grounded), and these are the ones to trust. For quality questions such as "are the recommendations specific and useful?", you can ask an LLM to grade with a rubric, but remember that a judge from the same model family shares the writer's blind spots, and its grades are noisy. With only a handful of reports, read them yourself.

### Measuring latency and cost

- **Latency:** wall-clock time per run. Report the **median and the worst case**. With a small sample, a percentile such as p95 means little. Repeat a few rows several times to see how much it varies, because API response times are noisy.
- **Cost on a free tier is not dollars,** it is quota: calls and tokens against rate limits. Count LLM calls and tokens per run.
- **An agent call is not an LLM call.** One agent may make several LLM calls (write a search query, then summarise the results), so the call counts printed by the stand-in agents below are a **lower bound** for real runs.
- Many OpenAI-compatible APIs return a `usage` field with token counts. Check that your provider and model do. If not, estimate from text length and say it is an estimate.

### Is the team worth it? Compare with the single agent

Day 57 promised to measure this. Run the same questions through Week 8's single `BusinessAgent` and through the team, and compare calls, latency, tokens, grounded numbers, honesty on impossible questions, and behaviour under failures. The honest conclusion may be "the team is better at catching unsupported claims on complex questions and not worth it for simple ones". The router already sends a simple request such as "top products" to the Analyst alone (1 agent call), which is the sensible design either way.

### Reading results honestly

- Report **counts** ("15 of 16 rows"), not percentages that suggest precision a small set does not have.
- A failure is a finding, not an embarrassment. Write down what it shows.
- Keep results from **stand-in agents** (orchestration only) separate from results with the **real agents**.
- Do not change the expected values to make a row pass.

### Deployment (Streamlit Community Cloud)

Unlike Week 7 (personal OAuth) this project can be deployed: it uses a synthetic dataset that is committed to the repo, and the only secret is an API key. Checklist:

1. **Run from a clean virtual environment** and install only `requirements.txt`. Every import must be listed (Week 7's `dateparser` failure was exactly this).
2. **Entry point** is `src/app.py`.
3. **Secrets** go in the host's secrets settings, never in the repo (`.env` and `.streamlit/secrets.toml` stay in `.gitignore`). The helper in the Coding Exercise reads the environment first and then Streamlit's secrets. In the Streamlit version I tested (1.66), top-level secrets were also placed in `os.environ` after being read.
4. **Python version:** your Week 7 deployment logs showed a very new Python (3.14). Test the packages in a clean environment, and check the host's advanced settings for choosing a version if something fails to install.
5. **Protect your quota.** A public link lets anyone spend your free-tier key. Options: a simple password gate, a per-session limit on runs, the existing `max_agent_calls` per run, and a low `max_tokens`.
6. **Untrusted text:** the user's question and web search results are untrusted input that ends up in prompts. Tell agents to treat sources as data and to ignore instructions inside them. The Critic's URL and number checks help but do not make this safe. The agents have read-only tools, which limits the damage.
7. **Smoke-test the live URL** after deploying: run three requests, including one with research unavailable, and confirm the status and limitations show correctly.
8. **Do not put real private data** into logs or the deployed dataset.

### Documenting limitations

Write limitations that are **specific and measured**, in the README, not generic disclaimers. Candidates from this week, each with its evidence:

| Limitation | Evidence |
|---|---|
| Router is keyword-based | Rows 15 and 16 below |
| No check that a named entity exists in the data | Row 15: "Tokyo store" gets findings about other things |
| LLM Critic can miss errors; approval is not proof | Critic design (Day 61); measure with planted errors |
| Number check skips whole numbers under 10 and flags derived numbers | Day 61 testing |
| More calls and more latency than one agent | Measured in the baseline comparison |
| Free-tier rate limits cap parallelism and throughput | Observed during real runs |
| Synthetic data, one comparison month | Dataset design |
| Small test set, single run per row | Dataset size |

---

## 💻 Coding Exercise

**1. The evaluation harness.** It reads the dataset, runs every row, and checks status, agents called, call limit, required and forbidden text, and number grounding. It was run against the Day 62 integration with **stand-in agents** (no LLM):

```python
import csv
import statistics
import sys
import time

import core
from core import run_team, check_numbers
from stubs import make_agents, EVID

INJECT = {
    "none": {}, "research_unavailable": {"research": "unavailable"}, "research_crash": {"research": "crash"},
    "analyst_fails": {"analyst_fails": True}, "invented_number_fixable": {"invent_first": True},
    "invented_number_unfixable": {"invent_first": True, "reviser_fixes": False},
    "budget_2": {"max_agent_calls": 2},
}
EVIDENCE_TEXTS = [e["detail"] for e in EVID]

def run_row(row: dict) -> dict:
    kw = dict(INJECT[row["injected_failure"]])
    limit = kw.pop("max_agent_calls", 12)
    agents, revise = make_agents(**kw)
    t0 = time.perf_counter()
    try:
        result = run_team(row["question"], agents, revise, max_agent_calls=limit)
        error = None
    except Exception as e:                      # a crash is a failed test, not a stopped evaluation
        result, error = None, repr(e)
    latency = time.perf_counter() - t0
    if result is None:
        return {"id": row["id"], "pass": False, "reasons": [f"crashed: {error}"], "latency": latency, "calls": 0}

    expected_agents = set(filter(None, row["expected_agents_called"].split(";")))
    called = set(result["log"]["calls"]) - {"revise"}
    report = result["report"]
    checks = {
        "status": result["status"] == row["expected_status"],
        "agents": called == expected_agents,
        "calls<=limit": len(result["log"]["calls"]) <= limit,
        "must_include": all(s in report for s in filter(None, row["must_include"].split(";"))),
        "must_not_include": not any(s in report for s in filter(None, row["must_not_include"].split(";"))),
        # check the findings/recommendations only: the Limitations section may legitimately quote a flagged number
        "grounded": not check_numbers(report.split("## Limitations")[0], EVIDENCE_TEXTS),
    }
    reasons = []
    if not checks["status"]:
        reasons.append(f"status {result['status']!r}, expected {row['expected_status']!r}")
    if not checks["agents"]:
        reasons.append(f"agents called {sorted(called)}, expected {sorted(expected_agents)}")
    for name in ("calls<=limit", "must_include", "must_not_include", "grounded"):
        if not checks[name]:
            reasons.append(f"failed check: {name}")
    return {"id": row["id"], "pass": all(checks.values()), "reasons": reasons,
            "latency": latency, "calls": len(result["log"]["calls"])}

def main(fixed_route: bool):
    if fixed_route:                              # one-line fix: a request for recommendations always needs the analyst
        def fixed(question):
            q = question.lower()
            ext = any(w in q for w in ("market", "competitor", "industry", "external", "trend", "outside"))
            internal = any(w in q for w in ("our ", "revenue", "sales", "customer", "product", "region", "orders"))
            recs = any(w in q for w in ("recommend", "what should", "next step", "advice"))
            if not (ext or internal or recs):
                return []
            steps = (["research"] if ext else []) + (["analyst"] if (internal or recs or not ext) else [])
            if recs:
                steps.append("strategy")
            return steps + (["critic"] if "strategy" in steps else [])
        core.route = fixed

    rows = list(csv.DictReader(open("evaluation.csv")))
    results = [run_row(r) for r in rows]
    for r, res in zip(rows, results):
        print(("PASS" if res["pass"] else "FAIL"), f"{r['id']:>2}", f"{r['category']:36}", "; ".join(res["reasons"]))
    passed = sum(x["pass"] for x in results)
    print(f"\n{passed} of {len(results)} rows passed")
    print(f"agent calls per run: median {statistics.median(x['calls'] for x in results)}, max {max(x['calls'] for x in results)}")
    print(f"latency (stand-in agents, so ~0): median {statistics.median(x['latency'] for x in results)*1000:.1f} ms")

if __name__ == "__main__":
    main(fixed_route="--fixed-route" in sys.argv)
```

**2. The settings helper** for local runs and deployment. Verified in three situations: environment variable set, nothing configured (returns the default, no crash), and a Streamlit secrets file present:

```python
import os

def get_setting(name: str, default: str = "") -> str:
    """Environment first (works locally via .env), then Streamlit secrets (works on Streamlit Cloud)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets[name])
    except Exception:            # no secrets file, or the key is not in it
        return default
```

**3. A usage meter** for the real runs. It was verified with fake usage objects and with a missing `usage`; whether your provider returns real `usage` data is for you to check:

```python
class UsageMeter:
    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, usage):
        self.calls += 1
        if usage is not None:                       # some providers/models may omit usage
            self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
```

Call `meter.add(response.usage)` after each LLM call.

**Results of running the harness (stand-in agents):**

| Version | Rows passed | Failing rows |
|---|---|---|
| Day 62 code as built | 14 of 16 | 15, 16 |
| With a one-line router change | 15 of 16 | 15 |

What the evaluation found:

- **Row 16 (a real gap):** "Research the market and recommend what to do" was routed to research and strategy but not the Analyst. The run ended `partial` with no recommendations and no explanation. Recommendations need the company's own data, so the router should add the Analyst whenever recommendations are requested. The fix is one condition: `if wants_internal or wants_recs or not wants_external`. With it, row 16 passes. This was not caught on Day 62's 16 scenarios, because none of them asked for research plus recommendations without mentioning the company's data.
- **Row 15 (a real gap, not fixed):** "Why did our Tokyo store underperform?" has no matching data, so the correct answer is `insufficient_evidence`. The orchestrator has no check that the thing the question names exists in the data, so it answers with unrelated findings. This is the same limitation noted on Day 55 and it still stands. A possible fix: have the Analyst report which entities in the question it could not find, and make the orchestrator return `insufficient_evidence` when none are found.
- **A bug in the harness itself:** at first, row 12 failed the grounding check. The cause was the check, not the system: the report's Limitations section quotes the flagged number (`45`) when describing the unresolved issue. The grounding check now looks only at the part of the report before the Limitations section.

**What these numbers do and do not mean.** They come from stand-in agents, so they show that the orchestration, routing, statuses and degraded modes behave as designed (and that the dataset can find real gaps). They say nothing about the quality of the real agents' findings or recommendations, about real latency (the printed milliseconds are the stand-ins' and mean nothing), or about real cost. The median of 2 and maximum of 5 agent calls per run are orchestration counts; real runs will make more LLM calls.

---

## 🛠 Mini Project

**Evaluate, deploy and document the AI Business Intelligence Team**

1. **Save the dataset** as `evaluation/evaluation.csv` and the harness under `tests/` as a regression test (stand-in agents). Add rows for anything new you find.
2. **Run with the real agents,** within your free-tier limits. For each row record status, agents called, agent calls, LLM calls, tokens (from the usage meter), and wall-clock time. Run each row once, and repeat three or four rows a few times to see the variation.
3. **Run the baseline:** put the same questions through Week 8's single `BusinessAgent` and fill in a comparison table (calls, tokens, latency, grounded numbers, behaviour on rows 10, 12, 13, 15).
4. **Fix what you can, keep what you cannot.** Apply the row 16 router fix and re-run. Leave row 15 failing, with its explanation, unless you implement the entity check and re-run.
5. **Check evidence quality** on every real report: re-run the number and URL checks outside the Critic, and read the reports yourself.
6. **Deploy** to Streamlit Community Cloud using the checklist, add a password gate or run limit, and smoke-test the live URL with three requests.
7. **Update the README:** mark each day done only if it is tested, replace the Evaluation Plan with the measured results (counts, not percentages), write the specific limitations above with their evidence, add screenshots, and add the live link.
8. **State what was and was not verified** (stand-in results vs. real-agent results).

---

## 🧠 Quiz

1. Why must the expected result be decided before running the evaluation?
2. Why is a count such as "15 of 16" more honest than "94%" for this dataset?
3. Row 12 first failed because of a bug in the harness. What was the bug, and what does that teach about evaluation code?
4. What is the difference between an agent call and an LLM call, and why does it matter when you estimate cost?
5. Why is the number of tokens a better cost measure than the number of agent calls on a free tier?
6. Name three protections for a publicly deployed app that spends your API key.
7. The team passes more rows than the single agent but uses far more calls. How do you decide whether it is worth it?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Every row passes | Expected values were copied from the output | Define expected results from the design, add failure and impossible rows |
| A row fails because of the checker | Harness logic too naive | Investigate before blaming the system (row 12); fix the check |
| Stand-in results presented as the system's quality | Mixed up orchestration tests and real runs | Report them separately and say which is which |
| Latency or cost taken from stand-ins | Stand-ins do not call an LLM | Measure with the real agents and the usage meter |
| Single-run numbers over-interpreted | API variation | Repeat a few rows, report median and worst case |
| Deployment fails on a missing package | `requirements.txt` incomplete | Test in a clean venv before deploying |
| API key missing on the host | Secrets not set, or read the wrong way | Use the settings helper and set the secret in the host's settings |
| Quota gone within a day | Public app without limits | Password gate, per-session limit, `max_agent_calls` |
| Limitations section is generic | Written without evidence | Make each limitation specific and point to the row or measurement |
| README claims things not tested | Status table filled in early | Mark a day done only after its tests pass |

---

## ✅ Checklist

- [ ] Evaluation dimensions understood (coordination, tools, evidence, status, recovery, latency, cost)
- [ ] `evaluation/evaluation.csv` created (16 rows or more) with expected results set in advance
- [ ] Harness runs as a regression test with stand-in agents
- [ ] Real-agent run done, with status, calls, tokens and time recorded
- [ ] Baseline comparison with the single agent done
- [ ] Row 16 router fix applied and re-tested; row 15 explained or fixed
- [ ] Evidence quality checked independently of the Critic
- [ ] Settings helper in use; no secrets in the repo
- [ ] Deployed, protected against quota abuse, and smoke-tested live
- [ ] README updated with measured results, specific limitations, screenshots and live link
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 63: Evaluation dataset, harness, deployment and documented limitations"
git push
```

---

## 🧠 Skill Learned

Multi-agent evaluation (coordination, evidence quality, failure recovery, latency and cost) + deployment and honest documentation of limitationsDay 63.md
