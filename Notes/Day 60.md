# Day 60 — Shared Memory, State and Context

**Objective:** Give the workflow a shared memory, decide what each agent is allowed to see, and build a workflow where every agent uses the findings produced earlier.

---

## 📖 Theory

### Why state matters

An LLM remembers nothing between calls. Every call sees only what you put in the prompt. So in a multi-agent system, "memory" means **the data you store and choose to pass in.** Two questions decide almost everything on this day:

1. **What do we store?** (shared state)
2. **What does each agent get to see?** (agent-specific context)

### Kinds of memory

| Kind | Lifetime | Example | In this project |
|---|---|---|---|
| **Working memory (run state)** | One run / one question | Findings, evidence, task statuses | **Yes, built today** |
| **Conversation / session memory** | One chat | Earlier questions and answers | Optional, see below |
| **Long-term memory** | Across sessions | Saved reports, preferences | Not in scope |

Week 8's Business Agent was stateless: one question in, one report out. Day 60 adds working memory shared by the agents inside one run.

### Shared task state (the "blackboard")

One structured object for the run. It holds:

- the question and the plan
- each task's status (`ok` / `failed` / `skipped`) and output
- **evidence** (the exact numbers and sources)
- **findings** (claims, each pointing to its evidence)
- **recommendations** (each pointing to the findings it relies on)

Rules that keep it safe:

- **The orchestrator is the only writer.** Agents return results; the orchestrator stores them. In Day 59 several agents run at the same time, and many writers touching one object is how data gets overwritten or lost.
- **Add, do not overwrite.** A revision becomes a new entry, so the history of what changed stays visible (the Critic needs this on Day 61).
- **Stable IDs** (`E1`, `F1`, ...) so one piece of data can be referred to unambiguously.

### Intermediate results and citations

Giving every piece of evidence and every finding an ID makes "uses earlier findings" something you can **check**, not just hope for:

```
Evidence E1, E2, E3   (exact numbers from the database / sources from the web)
        ↑ cited by
Finding F1, F2        (each must cite at least one evidence ID)
        ↑ cited by
Recommendation        (must cite at least one finding ID)
```

The state refuses a finding that cites unknown evidence, and a recommendation that cites an unknown finding. Without this, the Strategy Agent can write a recommendation that is not based on anything the Analyst produced, and nobody would notice.

### Agent-specific context

The principle is **least context**: each agent sees only what its task needs.

| Agent | Sees | Does not see |
|---|---|---|
| Research | the question | internal data, findings |
| Analyst | the question + research factors | recommendations |
| Strategy | the question + findings + their evidence | raw tool output |
| Critic | findings + evidence + recommendations | the writer's reasoning or prompt |

Why bother:

- **Focus.** Irrelevant text distracts the model.
- **Cost.** Each call re-sends its whole context, so a smaller context is cheaper and faster.
- **Independence.** A Critic that reads the writer's reasoning tends to be persuaded by it. A Critic that sees only the claims and the evidence checks them on their merits.
- A view reflects **what exists at that moment.** On Day 59's plan, the internal analysis runs at the same time as research, so its research factors are still empty when it starts.

### Conversation history

For follow-up questions ("now drill into KPK") a chat needs session memory. If you add it, store a **short summary of each earlier report and its finding IDs**, not the full transcript. This keeps the context small and avoids carrying old, possibly outdated numbers into a new run. It is optional for this project.

### Context management

Raw tool output can be huge (hundreds of rows) and cannot simply be pasted into every prompt. Options:

| Technique | Watch out for |
|---|---|
| **Select** only the evidence the task needs | Selecting the wrong subset hides the real cause |
| **Truncate** to a budget | Silently dropped data looks like "no data". Record what was dropped. |
| **Summarise** long text | Summaries can change or lose numbers. Keep exact figures in evidence, and summarise only prose. |
| **Reference by ID** instead of repeating | The reader must still be able to look the ID up |

A budget is usually in tokens. Characters are only a rough stand-in (about 4 characters per token for English text is a common approximation, not a rule).

### Debuggability

Save the final state of each run (for example as JSON). Then you can see exactly what each agent saw and produced, which is the only way to investigate a bad answer later. Run logs contain business data, so keep them out of Git (add the folder to `.gitignore`).

---

## 💻 Coding Exercise

Build `src/state.py`. This version was run, with the sample evidence taken from the Week 8 business dataset:

```python
from typing import Dict, List, Literal
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    id: str
    source: Literal["database", "web"]
    detail: str                                   # the exact number / quote, never paraphrased away

class Finding(BaseModel):
    id: str
    statement: str
    evidence_ids: List[str] = Field(min_length=1)  # no finding without evidence
    produced_by: str

class Recommendation(BaseModel):
    text: str
    based_on: List[str] = Field(min_length=1)      # finding ids this recommendation cites

class RunState:
    # which parts of the state each agent is allowed to see
    VIEWS = {
        "research":  ["question"],
        "analyst":   ["question", "research_factors"],
        "strategy":  ["question", "findings", "evidence"],
        "critic":    ["findings", "evidence", "recommendations"],   # not the writer's reasoning
    }

    def __init__(self, question: str):
        self.question = question
        self.research_factors: List[str] = []
        self.evidence: Dict[str, Evidence] = {}
        self.findings: Dict[str, Finding] = {}
        self.recommendations: List[Recommendation] = []

    def add_evidence(self, e: Evidence):
        if e.id in self.evidence:
            raise ValueError(f"duplicate evidence id {e.id}")
        self.evidence[e.id] = e

    def add_finding(self, f: Finding):
        if f.id in self.findings:
            raise ValueError(f"duplicate finding id {f.id}")
        missing = [i for i in f.evidence_ids if i not in self.evidence]
        if missing:
            raise ValueError(f"finding {f.id} cites unknown evidence {missing}")
        self.findings[f.id] = f

    def add_recommendation(self, r: Recommendation):
        missing = [i for i in r.based_on if i not in self.findings]
        if missing:
            raise ValueError(f"recommendation cites unknown findings {missing}")
        self.recommendations.append(r)

    def view_for(self, agent: str) -> dict:
        data = {
            "question": self.question,
            "research_factors": self.research_factors,
            "findings": {k: v.model_dump() for k, v in self.findings.items()},
            "evidence": {k: v.model_dump() for k, v in self.evidence.items()},
            "recommendations": [r.model_dump() for r in self.recommendations],
        }
        return {k: data[k] for k in self.VIEWS[agent]}

def fit_to_budget(items: List[str], max_chars: int):
    """Keep items in order until the budget is used; report how many were dropped."""
    kept, used = [], 0
    for it in items:
        if used + len(it) > max_chars:
            break
        kept.append(it)
        used += len(it)
    return kept, len(items) - len(kept)
```

Sample content used when running it:

```
E1  database  UrbanTote avg unit price 3,465 -> 2,384 (-31.2%)
E2  database  UrbanTote orders 17 -> 17 (May -> June)
E3  database  Total revenue 862,971 -> 928,630 (+7.6%)
F1  "UrbanTote decline is price-driven"      cites E1, E2
F2  "Total revenue did not decline"          cites E3
R   "Review the June UrbanTote discount before raising acquisition spend"   cites F1
```

What was checked:

| Check | Result |
|---|---|
| A valid state with evidence, findings and a recommendation | builds |
| A finding citing unknown evidence (`E9`) | rejected |
| A recommendation citing an unknown finding (`F7`) | rejected |
| A duplicate finding ID | rejected |
| Context views | Research sees 1 field (48 chars), Analyst 2 (113), Strategy 3 (613), Critic 3 (687) |
| Critic sees recommendations; Analyst does not | yes / no |
| Budget of 500 chars over 100 rows | kept 13, dropped 87 |

Two honest limits of what was run: `fit_to_budget` keeps items **in order** and drops the rest, so it does not rank by relevance, and it counts characters, not tokens.

The real workflow, with real agents reading and writing this state, is the exercise to build.

---

## 🛠 Mini Project

**A workflow where each agent uses earlier findings**

Flow: Analyst writes evidence and findings → Strategy reads findings and writes recommendations that cite them → Critic reads findings, evidence and recommendations.

Test these, and only claim what passes:

1. **Citations exist:** every recommendation cites at least one finding ID, and every finding cites evidence IDs, all valid.
2. **Earlier findings really matter:** remove `F1` from the state and re-run Strategy. Its recommendations must change (or be unable to cite `F1`). If nothing changes, Strategy is ignoring the findings.
3. **Integrity:** the three bad inputs above (unknown evidence, unknown finding, duplicate ID) are rejected.
4. **Context views:** for each agent, assert it does not receive fields outside its view, and log the size of each agent's context.
5. **Budget:** feed an oversized tool result; check it is cut to the budget and that the cut is recorded in the report's limitations, not hidden.
6. **State dump:** each run saves its final state as JSON, and you can read from it exactly what the Critic saw.
7. **Parallel safety:** run the parallel wave many times (for example 50) and check the state is identical each time, with the orchestrator as the only writer.

---

## 🧠 Quiz

1. An LLM "remembers" nothing between calls. What does memory actually mean in this system?
2. Why does the orchestrator, and not each agent, write to the shared state?
3. What do IDs and citations let you check that plain text would not?
4. Why should the Critic not see the Strategy Agent's reasoning?
5. A tool returns 700 rows and you truncate it to fit the budget. What must you also do, and why?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Every agent gets the whole state | No per-agent views | Define a view per agent and enforce it in code |
| Recommendations not based on any finding | No citation rule | Require `based_on` and validate the IDs exist |
| Numbers changed between agents | Findings were summarised in prose | Keep exact numbers in evidence and cite them by ID |
| Truncated data looks like "no data" | Silent truncation | Record what was dropped in the limitations |
| State overwritten in a parallel wave | Several agents writing at once | Only the orchestrator writes; agents return results |
| Context grows with every step | Whole history passed along | Pass IDs and summaries, not the whole history |
| Cannot explain a bad answer later | Nothing was saved | Dump the run state to JSON, and keep that folder out of Git |
| "Uses earlier findings" claimed without proof | Never tested what happens when findings change | Run test 2 above |

---

## ✅ Checklist

- [ ] Working vs. session vs. long-term memory understood
- [ ] `src/state.py` built (evidence, findings, recommendations, IDs)
- [ ] Citation integrity enforced and tested
- [ ] Per-agent context views enforced and tested
- [ ] Budget handling records what was truncated
- [ ] "Earlier findings matter" test passes
- [ ] Run state saved as JSON, and the folder ignored by Git
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 60: Shared run state, citations and per-agent context"
git push
```

---

## 🧠 Skill Learned

Shared state + context management for multi-agent workflows
