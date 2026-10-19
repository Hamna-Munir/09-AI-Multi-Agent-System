# Day 61 — Critic Agent, Verification and Recovery

**Objective:** Add a Critic that checks the other agents' work against the evidence and asks for revisions, and make the workflow recover from failures and stop cleanly instead of looping or guessing.

---

## 📖 Theory

### Why a Critic

Agents can sound confident and be wrong: an invented number, a recommendation that no finding supports, a source that does not exist. Two agents agreeing does not fix this, because a second agent reading the first one's answer tends to accept it. A **Critic** is a separate check whose only job is to ask "is this supported by the evidence?"

It is useful for the reason from Day 57: it did not write the answer, and (Day 60) it does not see the writer's reasoning, only the claims and the evidence.

### What the Critic checks

| Check | What it catches | Done by |
|---|---|---|
| **Citations exist** | A recommendation or finding that cites nothing, or cites an ID that does not exist | Code |
| **Numbers are grounded** | A number in the report that appears in no evidence | Code |
| **Sources are real** | A URL that the Research Agent never returned | Code |
| **Claim vs. evidence** | A claim that the cited evidence does not actually support | LLM judgment |
| **Conflicts** | Two findings or sources that disagree | LLM + code |
| **Missing information** | Something the question needs that no agent covered | LLM judgment |

**Put the strict rules in code and keep the LLM for judgment.** Code checks are exact and cheap and never get tired. The LLM check is the only one that can read meaning, but it can be wrong in both directions: it can miss an error or flag a correct claim.

### The review as structured output

The Critic returns data, not prose, so the orchestrator can act on it:

- `approved: bool`
- a list of `Issue`s, each with a `ref` (which finding or recommendation), a `kind`, a `detail`, and a `severity` (`blocking` or `minor`)

A rule enforced in the schema: **a review cannot be approved if it has a blocking issue.**

### The revision loop

```
Strategy writes a draft
        ↓
Critic reviews ──► approved ──► final report
        ↓ blocking issues
Strategy revises (given the issues)
        ↓
Critic reviews again ...
```

A loop needs **stopping conditions**, otherwise it runs forever or burns your quota:

| Stop when | Meaning |
|---|---|
| **Approved** | No blocking issues |
| **Revision limit reached** | Max rounds used (for example 2) |
| **No progress** | The same blocking issues came back unchanged, so another round will not help |
| **Budget exhausted** | Maximum agent calls or time for the run |
| **Unrecoverable failure** | A needed agent failed, so a report cannot honestly be written |

When the loop stops without approval, the report must **say so** and list the unresolved issues. It must not be presented as verified.

### Failure and recovery

Failures come in different kinds and need different responses:

| Failure | Retry? | Response |
|---|---|---|
| Timeout, rate limit, brief network error | **Yes**, with backoff | Wait and try again, a limited number of times |
| Malformed JSON from the LLM | Once, with a repair prompt | Show the error and the schema, then fail clearly |
| Validation or logic error (bad plan, permission denied) | **No** | Retrying cannot fix it; report it |
| An agent is permanently unavailable (no search key) | No | Run in a reduced mode and disclose it |

**Backoff:** wait longer after each failure (for example 1 s, 2 s, 4 s). This avoids hammering a service that is already struggling.

**Watch for double retrying.** The OpenAI Python SDK already retries some errors by itself (2 times by default). If you add your own retry loop on top, one logical call can become many real calls. Decide which layer retries; the SDK lets you set `max_retries` yourself.

### Timeouts

Set a timeout on the actual API call (the client supports a `timeout` setting), not only on the orchestrator's wait. As found on Day 59, a Python thread cannot be cancelled, so waiting with a timeout only stops *waiting*; the call keeps running and keeps costing.

### Conflicting results

Examples: the Research Agent says "demand for backpacks is rising" while the data shows orders flat; or two tools report different totals. Policy:

- **Never average and never silently pick one.** Show both, with their sources.
- **Internal data wins for facts about the company.** External research is context and hypotheses.
- If two *internal* numbers disagree, that is a data problem: flag it as a blocking conflict, and consider re-running that one task once.
- The Day 58 `contradicted` verdict is exactly how an external claim that the data disagrees with is recorded.

### Recovery means degrading honestly

If research is unavailable, the workflow continues with internal data only, and the report states that **no external factors were tested**. If the Analyst fails, there is no evidence, and the correct output is an "insufficient evidence" report (the Week 8 principle), not an invented one.

### The Critic's own limits

An LLM Critic can miss errors, can be too lenient or too harsh, and tends to share blind spots with the model that wrote the draft. So **approval is not proof of truth.** It lowers the chance of unsupported claims; it does not remove it. The final report should still list its limitations, and the code-level checks are the part you can rely on most.

---

## 💻 Coding Exercise

Build `src/agents/critic_agent.py` and the recovery helpers. The pieces below were run; the LLM judgment step was **not** run, because it needs an API key. In the tests it is replaced by a stand-in function.

**1. Review schema**

```python
from typing import List, Literal
from pydantic import BaseModel, model_validator

class Issue(BaseModel):
    ref: str                                               # finding / recommendation id, or "report"
    kind: Literal["unsupported_claim", "number_not_in_evidence",
                  "unknown_source", "conflict", "missing_information"]
    detail: str
    severity: Literal["blocking", "minor"]

class Review(BaseModel):
    approved: bool
    issues: List[Issue] = []

    @model_validator(mode="after")
    def approval_matches_issues(self):
        if self.approved and any(i.severity == "blocking" for i in self.issues):
            raise ValueError("cannot approve a report that has blocking issues")
        return self
```

**2. Deterministic checks**

```python
import re
from typing import Set

NUM = re.compile(r"\d[\d,]*\.?\d*")

def _numbers(text: str) -> Set[float]:
    out = set()
    for tok in NUM.findall(text):
        try:
            out.add(float(tok.rstrip(".,").replace(",", "")))
        except ValueError:
            pass
    return out

def check_numbers(draft: str, evidence_texts: List[str], derived_ok: Set[float] = frozenset()) -> List[Issue]:
    """Numbers in the draft that appear in no evidence. Skips ids (F1), years, and whole numbers under 10."""
    allowed = set().union(*[_numbers(t) for t in evidence_texts]) | set(derived_ok)
    cleaned = re.sub(r"\b[EFR]\d+\b", "", draft)
    issues = []
    for v in sorted(_numbers(cleaned)):
        if (v < 10 and v == int(v)) or 1990 <= v <= 2100:
            continue
        if v not in allowed:
            issues.append(Issue(ref="report", kind="number_not_in_evidence",
                                detail=f"number {v:g} appears in the report but in no evidence",
                                severity="blocking"))
    return issues

URL = re.compile(r"https?://[^\s)\]]+")

def check_urls(draft: str, allowed_urls: Set[str]) -> List[Issue]:
    return [Issue(ref="report", kind="unknown_source",
                  detail=f"{u} was not returned by the Research Agent", severity="blocking")
            for u in URL.findall(draft) if u not in allowed_urls]
```

**3. Revision loop with stopping conditions**

```python
from typing import Callable

def revise_until_approved(draft, review_fn: Callable, revise_fn: Callable, max_revisions: int = 2):
    seen = None
    review = review_fn(draft)
    for round_no in range(max_revisions + 1):
        blocking = sorted((i.ref, i.kind, i.detail) for i in review.issues if i.severity == "blocking")
        if review.approved or not blocking:
            return {"status": "approved", "rounds": round_no, "draft": draft, "issues": review.issues}
        if blocking == seen:                                   # same problems twice: no progress
            return {"status": "stuck", "rounds": round_no, "draft": draft, "issues": review.issues}
        if round_no == max_revisions:
            return {"status": "unresolved", "rounds": round_no, "draft": draft, "issues": review.issues}
        seen = blocking
        draft = revise_fn(draft, review.issues)
        review = review_fn(draft)
```

**4. Retry with backoff** (the `sleep` argument is injected so tests run instantly)

```python
def retry(fn, attempts=3, base_delay=1.0, retry_on=(TimeoutError, ConnectionError), sleep=lambda s: None):
    for n in range(1, attempts + 1):
        try:
            return fn()
        except retry_on:
            if n == attempts:
                raise
            sleep(base_delay * 2 ** (n - 1))
```

(In real use pass `time.sleep` as `sleep`.)

**What was checked**

Evidence used: `UrbanTote avg unit price 3,465 -> 2,384 (-31.2%)`, `UrbanTote orders 17 -> 17`, `Total revenue 862,971 -> 928,630 (+7.6%)`.

| Check | Result |
|---|---|
| Draft whose numbers all come from the evidence | nothing flagged |
| Draft saying "a further 45% drop is expected" | `45` flagged |
| Draft saying revenue "rose 8.4%" | `8.4` flagged |
| A made-up URL not returned by research | flagged |
| `Review(approved=True)` with a blocking issue | rejected by the schema |
| Revision fixes the problem on the first pass | `approved`, 1 revision, 2 reviews |
| Reviser changes nothing, same issue returns | `stuck` after 1 revision, 2 reviews (limit was 3) |
| Issues keep changing | `unresolved` at the limit, 2 revisions, 3 reviews |
| Function fails twice then succeeds | returns `ok` after 3 calls, waits of 1.0 s then 2.0 s |
| Function always fails | raised after 3 attempts |
| `PermissionError` (not retryable) | raised after 1 call |

**Known gaps in the number check (found while testing, not hidden):**

- It **does not check whole numbers under 10**, so a wrong "fell 5%" slips through.
- A **derived number** (for example a difference computed from two evidence values, like `1,081`) is flagged unless your code adds it to `derived_ok`. That is a false alarm by design: compute derived numbers in code and register them.
- It checks that a number appears *somewhere* in the evidence, not that it is attached to the right claim. The LLM judgment step is meant to cover that, and it is not perfect.

The real Critic Agent (these checks plus the LLM judgment step, reading the Day 60 state) is the exercise to build.

---

## 🛠 Mini Project

**A Critic Agent that flags unsupported claims and requests revisions**

Plant the problems on purpose, then check the Critic finds them:

1. **Invented number:** the draft contains a number in no evidence. Expected: blocking `number_not_in_evidence`.
2. **Uncited recommendation:** a recommendation citing no finding, or an unknown ID. Expected: rejected.
3. **Fake source:** a URL the Research Agent never returned. Expected: blocking `unknown_source`.
4. **Overclaim:** "revenue collapsed" when the evidence shows +7.6%. Expected: blocking `unsupported_claim` from the LLM check (this is the one that can legitimately be missed; record how often it is).
5. **Conflict:** one external claim says demand is rising, the data says orders are flat. Expected: both shown, internal data preferred, flagged as a conflict.
6. **Revision works:** Strategy revises using the issue list and the second review approves.
7. **Stopping:** a reviser that cannot fix the issue ends as `stuck` or `unresolved` and the final report **says it is not fully verified.**
8. **Failures:** research unavailable → report discloses it; Analyst fails → "insufficient evidence" report; a transient error is retried with backoff; a non-retryable error is not.
9. **Clean report:** a correct report with no planted problems is approved. A Critic that flags everything is also broken.

Report how many planted problems it caught and how many it missed. Do not claim "the Critic verifies reports" from a single clean run.

---

## 🧠 Quiz

1. Why is "two agents agreed" not evidence that an answer is correct?
2. Why are the number and URL checks done in code instead of asking the LLM?
3. List three stopping conditions for the revision loop. What must the report say when the loop stops without approval?
4. Which failures should be retried and which should not? Give one example of each.
5. The OpenAI SDK retries some errors by default. What goes wrong if you also add your own retry loop?
6. Which fact wins when the company's data and an external article disagree, and why?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Critic approves everything | Prompt too lenient, or it saw the writer's reasoning | Give it only claims and evidence; test with planted errors |
| Critic flags everything | Prompt too strict, or checks too crude | Test with a clean report; tune the checks |
| Revision loop never ends | No stopping conditions | Revision limit, no-progress detection, call budget |
| Same issues returned every round | Reviser ignores the issue list | Pass the issues into the revise prompt; detect "stuck" |
| Retrying a validation error | Retrying everything | Retry only transient errors |
| Many more API calls than expected | SDK retries plus your retries | Decide which layer retries; set `max_retries` deliberately |
| Timeout set but cost still incurred | Thread keeps running after the wait ends | Set the timeout on the API client as well |
| Report presented as verified after the loop gave up | Unresolved issues dropped | Always state unresolved issues in the final report |
| Valid derived numbers flagged | Computed values not in evidence | Compute them in code and add them to `derived_ok` |

---

## ✅ Checklist

- [ ] Why a Critic is needed, and its limits, understood
- [ ] `Review` / `Issue` schema built, with the "no approval with blocking issues" rule
- [ ] Number and URL checks built and tested, gaps written down
- [ ] LLM judgment step built (needs a key; tested with a stand-in)
- [ ] Revision loop with all stopping conditions tested
- [ ] Retry with backoff tested (retryable vs. non-retryable)
- [ ] Planted-error test done, with caught / missed counts reported
- [ ] Failure paths tested (research unavailable, Analyst failed)
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 61: Critic agent, revision loop and failure recovery"
git push
```

---

## 🧠 Skill Learned

Critic/verifier agents + error recovery (retries, stopping conditions, honest degradation)
