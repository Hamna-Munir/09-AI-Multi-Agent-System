# Day 58 — Agent Roles and Structured Communication

**Objective:** Make agents pass results to each other in a defined, validated format, and build a Research Agent → Analyst Agent workflow.

---

## 📖 Theory

### Why communication is the hard part

Day 57 gave each agent its own job. The moment two agents work on one task, a new question appears: **what exactly does one hand to the next?** If the handoff is loose text, the next agent has to guess what matters, details get lost, and a small mistake early on is passed along as if it were fact. Most multi-agent bugs live at the handoffs, not inside the agents.

### Role instructions

A role instruction is the agent's system prompt. A good one is short and has four parts:

```
Role:        You are the Research Agent.
Goal:        Find external factors that could explain the business question.
Rules:       Every factor must have a source URL. If search is unavailable, say so. Never invent sources.
Output:      Return ONLY JSON matching the ResearchResult schema.
```

The prompt tells the model what to do. It does not *force* it. Anything that must hold (a tool restriction, a required field) should also be enforced in code, as on Day 57.

### Structured outputs

Instead of free text, each agent returns **data with a fixed shape** (JSON). Reasons:

- The next agent can rely on named fields instead of parsing prose.
- Missing or wrong-shaped output is caught immediately, not three steps later.
- A Critic (Day 61) can check each claim against its evidence, because claims and evidence are separate fields.

How it works with an LLM: show the model the schema, ask for JSON only, strip any code fences (as in Weeks 7 and 8), then **validate**. If your provider offers JSON mode or structured outputs for your model, you can switch it on; check its documentation, because support varies by model.

### Pydantic schemas

Pydantic (v2 here) lets you describe the shape once and get validation for free:

| Pydantic feature | Use in this project |
|---|---|
| `BaseModel` | Defines a message shape (`ResearchResult`, `AnalysisResult`, ...) |
| `Field(min_length=1)` | "At least one source", "at least one piece of evidence" |
| `Literal[...]` | Limits a value to allowed options (`"ok"` / `"unavailable"`) |
| `model_validator` | Rules across fields ("status ok needs at least one factor") |
| `model_validate_json()` | Parse and validate the LLM's JSON in one step |
| `ValidationError` | Raised on bad shape; catch it instead of crashing |
| `model_json_schema()` | Produces the schema you can show the LLM |

### Shared state

A single object the whole workflow reads and writes: the question, each agent's output, and a log. A simple rule keeps it safe: **each agent writes only its own slot** (the Research Agent writes `research`, the Analyst writes `analysis`) and may read what earlier agents wrote. Day 60 goes deeper (agent-specific context, history).

### Task handoffs

A handoff is a typed message from one agent to another:

| Field | Meaning |
|---|---|
| `from_agent` / `to_agent` | Who sent it and who it is for |
| `task` | What the receiver should do with it |
| `payload` | The validated result being passed |

A handoff contains the **result and its limits** (status, sources, notes). It does not contain the sender's whole conversation or hidden reasoning.

### Why Research → Analyst makes sense

At first it seems odd that the Analyst comes after the Research Agent. Here is the dependency that makes it real:

1. The Research Agent finds **external factors** that might explain the question, each with a source.
2. External factors are **hypotheses, not facts about this company** (same principle as Week 8).
3. The Analyst takes each factor and **tests it against the company's own data**, returning `supported`, `contradicted`, or `not_testable`.

Example: the Research Agent returns "summer heat raises demand for cooling products". The Analyst checks the fan product's sales and reports what the data shows. The Analyst's output now depends on what research handed over, which is the point of a handoff.

### The failure path is part of the design

If search is unavailable, the Research Agent returns `status: "unavailable"` with no factors. The Analyst must still work: it runs its internal analysis and records in `limitations` that no external factors were tested. A handoff that only works on the happy path is not finished.

### Common design rule: no claim without evidence

Schemas can enforce it directly. A `Finding` needs at least one evidence item; an `ExternalFactor` needs at least one source URL. An agent that cannot supply them fails validation instead of producing a confident but unsupported answer.

---

## 💻 Coding Exercise

Define the schemas in `src/schemas.py`. This version was run and behaves as described in the comments:

```python
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError, model_validator

class ExternalFactor(BaseModel):
    claim: str
    source_urls: List[str] = Field(min_length=1)      # no source, no factor
    testable_with: Optional[str] = None               # which internal data could test it

class ResearchResult(BaseModel):
    status: Literal["ok", "unavailable"]
    factors: List[ExternalFactor] = []
    note: Optional[str] = None

    @model_validator(mode="after")
    def status_matches_content(self):
        if self.status == "ok" and not self.factors:
            raise ValueError("status 'ok' needs at least one factor")
        if self.status == "unavailable" and self.factors:
            raise ValueError("status 'unavailable' must not contain factors")
        return self

class Handoff(BaseModel):
    from_agent: str
    to_agent: str
    task: str
    payload: ResearchResult

class Finding(BaseModel):
    statement: str
    evidence: List[str] = Field(min_length=1)         # no claim without evidence

class FactorCheck(BaseModel):
    claim: str
    verdict: Literal["supported", "contradicted", "not_testable"]
    evidence: List[str] = []

class AnalysisResult(BaseModel):
    findings: List[Finding]
    factor_checks: List[FactorCheck] = []
    limitations: List[str] = []

class SharedState(BaseModel):
    question: str
    research: Optional[ResearchResult] = None         # written only by the Research Agent
    analysis: Optional[AnalysisResult] = None         # written only by the Analyst Agent
    log: List[str] = []
```

What was checked when running it:

| Check | Result |
|---|---|
| A good `ResearchResult` survives `model_dump_json()` → `model_validate_json()` unchanged | yes |
| An `ExternalFactor` with no source URL | rejected |
| `status="ok"` with no factors, or `status="unavailable"` with factors | rejected |
| Malformed LLM output (missing field, or not JSON at all) | raises `ValidationError`, catchable |
| A `Finding` with no evidence | rejected |
| Payload after a `Handoff` equals what the sender produced | yes |
| `ResearchResult.model_json_schema()` | available to show the LLM |

The two agents themselves (LLM + real tools returning these schemas) are the exercise to build.

---

## 🛠 Mini Project

**Research Agent → Analyst Agent workflow**

Build the flow:

```
SharedState(question)
      ↓
Research Agent  → writes state.research (ResearchResult)
      ↓  Handoff(from=research, to=analyst, payload=state.research)
Analyst Agent   → tests each factor against the database → writes state.analysis (AnalysisResult)
```

Test all of these, and only claim what passes:

1. **Happy path** (search mocked to return results): the Analyst's `factor_checks` has one entry per factor it received.
2. **Handoff integrity:** what the Analyst received equals what the Research Agent produced, with no field lost.
3. **The handoff matters:** change the research input and show that the Analyst's output changes. If the output is identical either way, nothing is really being handed over.
4. **Unavailable path** (no `TAVILY_API_KEY`): research returns `status="unavailable"`, the Analyst still produces findings, and `limitations` says no external factors were tested.
5. **Malformed output:** feed the parser invalid JSON. It must raise a handled `ValidationError` (retry once, or fail with a clear message), not crash silently.
6. **No evidence, no finding:** an Analyst finding with empty evidence is rejected.

Numbers in `evidence` must come from tool results, never from the LLM.

---

## 🧠 Quiz

1. Why is a typed handoff better than passing the previous agent's whole answer as text?
2. What does `Field(min_length=1)` on `source_urls` protect against?
3. Why must the unavailable-research case be part of the schema design, not an afterthought?
4. Why are external factors treated as hypotheses for the Analyst to test, instead of facts?
5. Test 3 above shows the Analyst's output changes when the research changes. What would it mean if it did not?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| `ValidationError` on LLM output | Model returned prose, code fences, or a missing field | Strip fences, show the schema in the prompt, retry once, then fail clearly |
| Agent output looks fine but a field is silently empty | Optional field with no rule | Add `min_length`, a `model_validator`, or make the field required |
| Handoff loses information | Only a text summary was passed | Pass the validated object (`payload`), not a paraphrase |
| An agent overwrites another agent's work in shared state | No rule on who writes what | Each agent writes only its own slot |
| Workflow breaks when search is off | Only the happy path was designed | Add `status="unavailable"` and a test for it |
| Agent "agrees" with whatever it received | Input treated as true | Make the receiver test claims against its own evidence |
| Claiming the workflow works after one demo run | No tests of failure cases | List the six tests above and report which actually passed |

---

## ✅ Checklist

- [ ] Role instruction written for each agent (role, goal, rules, output)
- [ ] `src/schemas.py` built and validated with good and bad inputs
- [ ] Research Agent returns a validated `ResearchResult`
- [ ] Analyst Agent receives a `Handoff` and returns a validated `AnalysisResult`
- [ ] Handoff integrity and "handoff matters" tests pass
- [ ] Unavailable-research path tested
- [ ] Malformed-output path tested
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 58: Structured communication + Research to Analyst workflow"
git push
```

---

## 🧠 Skill Learned

Structured agent communication + schema-validated handoffs
