# Day 62 — Integrate the Complete System

**Objective:** Combine the specialised agents, tools, orchestration, shared state, Critic and error handling into one working AI Business Intelligence Team that produces a single, honest report.

---

## 📖 Theory

### Why integration is its own day

Days 57-61 built the parts: roles, handoffs, an orchestrator, shared state, a Critic with recovery. Each part can work alone and the whole can still fail, because most bugs live **at the seams**: a field one component produces and the next one does not expect, a failure that one layer hides from the next, a rule that made sense on its own day and is wrong once everything is connected. Integration is where those are found.

### The integrated flow

```
User request
     ↓
route()  ─── unclear? ──► ask the user to clarify (no agent is called)
     ↓
build_plan()  → tasks with dependencies
     ↓
Wave 1:  Research Agent  ‖  Analyst Agent (internal analysis)
Wave 2:  Analyst Agent (test external factors against our data)
Wave 3:  Strategy Agent (draft recommendations)
     ↓
Orchestrator writes results into the shared state   (the ONLY writer)
     ↓
Critic review  ⇄  Strategy revision      (loop with stopping conditions)
     ↓
Report assembled from the state by code
     ↓
Report + verification status + limitations + run log
```

Note that the Critic loop sits **after** the task graph. On Day 59 the Critic was drawn as a task in the graph, but a review-and-revise loop repeats an unknown number of times, which a fixed graph cannot express.

### Interface contracts

Every component makes a promise about what it takes in, what it hands back, and what it does when something goes wrong. Write these down; they are what you test.

| Component | Takes | Returns | On failure |
|---|---|---|---|
| `route` | the question | list of steps, or `[]` | `[]` means "ask the user" |
| Research Agent | the task | factors with sources, or `status: unavailable` | unavailable is a normal outcome, a crash is `failed` |
| Analyst (internal) | the task | evidence + findings, each finding citing evidence | `failed` → no report is possible |
| Analyst (test factors) | research output | a verdict per factor | `skipped` if research crashed |
| Strategy Agent | findings (+ factor checks if available) | recommendations citing finding IDs | `failed` → report without recommendations |
| Critic | the draft + evidence | `Review` | revision loop stops by its limits |
| `run_team` | question, agents | status + report + limitations + run log | always returns a report, never a stack trace |

### What integration changed in the earlier designs

Putting it together exposed rules from earlier days that were too simple:

1. **Optional dependencies.** On Day 59 a task was skipped whenever a dependency failed. Here that would be wrong: if research crashes, the factor test is skipped, and a Strategy task that *required* the factor test would be skipped too, throwing away a perfectly good internal analysis. So a task now has `depends_on` (hard: skip if it failed) and `optional` (use it if it succeeded, otherwise carry on).
2. **Different requests need different plans.** "What market trends affect backpacks?" needs only research. "What are our top products?" needs only the Analyst. The orchestrator must not demand internal analysis for a research-only request. (The first version I wrote did, and answered a research-only question with "insufficient evidence". The scenarios below caught it.)
3. **A status vocabulary.** The result must say what it is, not just "done":

| Status | Meaning |
|---|---|
| `verified` | The Critic approved the recommendations |
| `not_fully_verified` | The loop gave up with unresolved issues; they are listed |
| `partial` | Recommendations were requested but the Strategy step did not complete |
| `findings_only` | Only findings or external factors were requested |
| `insufficient_evidence` | Nothing reliable to report |
| `needs_clarification` | The request was unclear; no agent was called |

4. **The call budget is shared by parallel threads**, so the counter needs a lock. Otherwise two agents can pass the check at the same moment and overshoot the limit.

### Degraded modes: say what is missing

| Situation | What the system does | What the report says |
|---|---|---|
| Research unavailable (no key) | Continues with internal data | "External research unavailable" |
| Research crashes | Skips the factor test, still runs Strategy | The failure, and "factors were not tested" |
| Analyst fails | Stops; no recommendations | "Insufficient evidence" |
| Critic cannot be satisfied | Returns the draft marked unverified | Status `not_fully_verified` + the unresolved issues |
| Call budget exhausted | Stops further calls | That the budget ran out, and what did not complete |
| Unclear request | Asks the user | A clarifying question |

### Report generation

The report structure is built **by code from the shared state**, not written freely by an LLM. Every finding line carries its evidence IDs, every recommendation carries the finding IDs it rests on, and the status and limitations are always printed. The only LLM-written text is the recommendations themselves, and those pass through the Critic. If you later add an LLM pass to make the prose smoother, it must not add facts, and the Critic must check its output again.

### Validate at the boundaries

The code below passes plain dicts between agents to keep it short. In the real build, validate each agent's output with the Day 58 schemas **as soon as it arrives**, so a malformed output fails at the seam, with a clear message, not three steps later.

### Testing an integrated system

| Level | What it proves | Uses LLM? |
|---|---|---|
| **Contract tests** | Each component honours its interface | No |
| **Integration tests with stand-in agents** | The wiring: order, state, critic loop, degraded modes, budget | No (fast, free, repeatable) |
| **Failure injection** | Every degraded mode in the table above | No |
| **A few real runs** | The real agents behave sensibly on real questions | Yes (use sparingly on a free tier) |

Stand-in agents prove the **orchestration** works. They do **not** prove the real LLM agents write good findings or recommendations. Keep those two claims separate.

### The UI

Streamlit front end (`src/app.py`): a question box, the report, a visible **verification status**, and an expandable "run details" panel (plan, each agent's status, the call log, Critic issues). This is the same transparency idea as Week 8. Catch every error at the boundary and show a readable message, never a traceback. If you render HTML with `st.markdown`, keep each fragment on one line, as you found in Weeks 7 and 8.

---

## 💻 Coding Exercise

Build the integrated `src/orchestrator.py`. It reuses, unchanged, the pieces from Days 60 and 61: `RunState` (with `Evidence`, `Finding`, `Recommendation`), `Issue` / `Review`, `check_numbers`, `check_urls`, and `revise_until_approved`. What changes or is new is below. This code was run against stand-in agents:

```python
# ---- Day 59: plan, waves, executor (now with OPTIONAL dependencies) ----
@dataclass
class Task:
    id: str
    agent: str
    depends_on: List[str] = field(default_factory=list)   # hard: if one fails, this task is skipped
    optional: List[str] = field(default_factory=list)     # soft: used if it succeeded, otherwise ignored

def waves(tasks: List[Task]) -> List[List[Task]]:
    done, remaining, out = set(), {t.id: t for t in tasks}, []
    while remaining:
        ready = [t for t in remaining.values() if all(d in done for d in t.depends_on + t.optional)]
        if not ready:
            raise ValueError("cycle or missing dependency in plan")
        out.append(ready)
        done |= {t.id for t in ready}
        for t in ready:
            del remaining[t.id]
    return out

def run_plan(tasks: List[Task], agents: Dict[str, Callable], parallel: bool = True) -> Dict[str, dict]:
    results: Dict[str, dict] = {}

    def run_one(task: Task) -> dict:
        failed = [d for d in task.depends_on if results[d]["status"] != "ok"]
        if failed:
            return {"status": "skipped", "reason": f"dependency failed: {failed}"}
        inputs = {d: results[d]["output"] for d in task.depends_on + task.optional
                  if results[d]["status"] == "ok"}
        try:
            return {"status": "ok", "output": agents[task.agent](inputs)}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    for wave in waves(tasks):
        if parallel and len(wave) > 1:
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                for t, r in zip(wave, pool.map(run_one, wave)):
                    results[t.id] = r
        else:
            for t in wave:
                results[t.id] = run_one(t)
    return results

def route(question: str) -> List[str]:
    q = question.lower()
    wants_external = any(w in q for w in ("market", "competitor", "industry", "external", "trend", "outside"))
    wants_internal = any(w in q for w in ("our ", "revenue", "sales", "customer", "product", "region", "orders"))
    wants_recs = any(w in q for w in ("recommend", "what should", "next step", "advice"))
    if not (wants_external or wants_internal or wants_recs):
        return []
    steps: List[str] = []
    if wants_external:
        steps.append("research")
    if wants_internal or not wants_external:
        steps.append("analyst")
    if wants_recs:
        steps.append("strategy")
    if "strategy" in steps:
        steps.append("critic")
    return steps

def build_plan(steps: List[str]) -> List[Task]:
    tasks: List[Task] = []
    if "research" in steps:
        tasks.append(Task("research", "research"))
    if "analyst" in steps:
        tasks.append(Task("internal", "analyst"))
        if "research" in steps:
            tasks.append(Task("test", "analyst", depends_on=["research"]))
    if "strategy" in steps and any(t.id == "internal" for t in tasks):
        tasks.append(Task("strategy", "strategy", depends_on=["internal"],
                          optional=[t.id for t in tasks if t.id == "test"]))
    return tasks


# ---- Day 62: the integrated run ----
class BudgetExceeded(Exception):
    pass

def run_team(question: str, agents: Dict[str, Callable], revise: Callable,
             max_agent_calls: int = 12, max_revisions: int = 2) -> dict:
    log = {"calls": [], "revisions": 0}
    lock = threading.Lock()

    def counted(name: str, fn: Callable) -> Callable:
        def wrapper(*args):
            with lock:                                   # the counter is shared by parallel threads
                if len(log["calls"]) >= max_agent_calls:
                    raise BudgetExceeded("agent call budget exhausted")
                log["calls"].append(name)
            return fn(*args)
        return wrapper

    steps = route(question)
    if not steps:
        return {"status": "needs_clarification", "limitations": [], "log": log,
                "report": "I could not tell what to analyse. Do you want your own sales data analysed, "
                          "market research, or recommendations?"}

    state, limitations, checks = RunState(question), [], []
    results = run_plan(build_plan(steps), {n: counted(n, f) for n, f in agents.items()})

    # --- the orchestrator is the ONLY writer of the shared state ---
    if "analyst" in steps:
        internal = results["internal"]
        if internal["status"] != "ok":
            limitations.append(f"Internal analysis unavailable: {internal.get('error') or internal.get('reason')}")
            return {"status": "insufficient_evidence", "limitations": limitations, "log": log,
                    "report": "Insufficient evidence to answer from the available business data."}
        for e in internal["output"]["evidence"]:
            state.add_evidence(Evidence(**e))
        for f in internal["output"]["findings"]:
            state.add_finding(Finding(**f))

    allowed_urls: Set[str] = set()
    research = results.get("research")
    if research:
        if research["status"] != "ok":
            limitations.append(f"External research failed: {research.get('error')}")
        elif research["output"]["status"] != "ok":
            limitations.append(f"External research unavailable: {research['output'].get('note')}")
        else:
            state.research_factors = research["output"]["factors"]
            allowed_urls = {u for f in state.research_factors for u in f["source_urls"]}
    test = results.get("test")
    if test and test["status"] == "ok":
        checks = test["output"]["factor_checks"]
    elif research:
        limitations.append("External factors were not tested against the company data.")

    if not state.findings and not state.research_factors:
        return {"status": "insufficient_evidence", "limitations": limitations, "log": log,
                "report": "Insufficient evidence to answer from the available data."}

    status = "partial" if "strategy" in steps else "findings_only"
    draft_result = None
    strategy = results.get("strategy")
    if strategy and strategy["status"] == "ok":
        evidence_texts = [e.detail for e in state.evidence.values()]

        def review_fn(draft: dict) -> Review:
            issues = check_numbers(draft["text"], evidence_texts) + check_urls(draft["text"], allowed_urls)
            for r in draft["recommendations"]:
                bad = [i for i in r["based_on"] if i not in state.findings]
                if bad:
                    issues.append(Issue(ref="recommendation", kind="unsupported_claim",
                                        detail=f"cites unknown findings {bad}", severity="blocking"))
            return Review(approved=not any(i.severity == "blocking" for i in issues), issues=issues)

        def revise_fn(draft: dict, issues: List[Issue]) -> dict:
            log["revisions"] += 1
            return counted("revise", revise)(draft, issues)

        draft_result = revise_until_approved(strategy["output"], review_fn, revise_fn, max_revisions)
        if draft_result["status"] == "approved":
            status = "verified"
            for r in draft_result["draft"]["recommendations"]:
                state.add_recommendation(Recommendation(**r))
        else:
            status = "not_fully_verified"
            limitations += [f"Unresolved: {i.detail}" for i in draft_result["issues"] if i.severity == "blocking"]
    elif strategy:
        limitations.append(f"Strategy step did not complete: {strategy.get('error') or strategy.get('reason')}")

    return {"status": status, "limitations": limitations, "log": log,
            "report": assemble_report(state, checks, status, limitations, log, draft_result)}

def assemble_report(state: RunState, checks: list, status: str, limitations: list, log: dict, draft_result) -> str:
    label = {"verified": "verified by the Critic",
             "not_fully_verified": "NOT fully verified (see limitations)",
             "partial": "partial (no recommendations produced)",
             "findings_only": "findings only (no recommendations requested)"}[status]
    lines = [f"# Business Intelligence Report", f"**Question:** {state.question}",
             f"**Verification status:** {label}", "", "## Findings"]
    lines += [f"- {f.id} ({', '.join(f.evidence_ids)}): {f.statement}" for f in state.findings.values()]
    if checks:
        lines += ["", "## External factors tested"]
        lines += [f"- {c['claim']} -> {c['verdict']}" for c in checks]
    elif state.research_factors:
        lines += ["", "## External factors (not tested against company data)"]
        lines += [f"- {f['claim']} (source: {', '.join(f['source_urls'])})" for f in state.research_factors]
    if state.recommendations:
        lines += ["", "## Recommendations"]
        lines += [f"- {r.text} (based on {', '.join(r.based_on)})" for r in state.recommendations]
    elif draft_result and status == "not_fully_verified":
        lines += ["", "## Draft recommendations (unverified)"]
        lines += [f"- {r['text']}" for r in draft_result["draft"]["recommendations"]]
    lines += ["", "## Limitations"] + ([f"- {l}" for l in limitations] or ["- None recorded"])
    lines += ["", f"_Run log: {len(log['calls'])} agent calls, {log['revisions']} revision(s)._"]
    return "\n".join(lines)
```

The stand-in agents returned plain dicts (research factors, evidence and findings, a strategy draft). One thing to fix in the real build: the stand-in Analyst tells its two tasks apart by checking whether research input exists. That is fragile. Pass an explicit `task` name instead.

**What was checked** (16 checks, all passed, using stand-in agents):

| Scenario | Result |
|---|---|
| Happy path | `verified`; 4 agent calls; research and the internal analysis start first, then the factor test, then Strategy |
| Report content | Tested factor shown, recommendation cites `F1`, limitations "None recorded" |
| Research unavailable | Still `verified`; limitation printed in the report |
| Research crashes | Strategy still runs (optional dependency); failure and "not tested" both disclosed |
| Analyst fails | `insufficient_evidence`; Strategy and revisions never called |
| Draft with an invented number (`45%`) | Caught, revised once, then `verified`; `45%` is not in the final report |
| Reviser cannot fix it | `not_fully_verified` after 1 revision (stuck detected); the issue is listed; draft labelled unverified |
| Unclear request ("hello") | `needs_clarification`; zero agent calls |
| Budget of 2 calls | Exactly 2 calls made; `partial`; budget exhaustion disclosed |
| Analyst-only request | `findings_only`; one call; no recommendations section |
| Research-only request | `findings_only`; one call; factors shown as "not tested against company data" |
| Research-only with research unavailable | `insufficient_evidence` |
| 30 repeated runs | Always `verified` with 4 calls |

**What this does not prove:** the real LLM agents, real tool calls, real latency or cost, or the LLM judgment part of the Critic. The 30-run check is a consistency check, not a proof that the lock is correct.

---

## 🛠 Mini Project

**Complete AI Business Intelligence Team**

1. **Wire the real agents** into `run_team`: Research (Tavily), Analyst (Week 8 database tools), Strategy, Critic (code checks + LLM judgment). Copy the Week 8 `business.db` into `data/`.
2. **Validate every agent output** with the Day 58 schemas at the handoff.
3. **Re-run all 16 scenarios** above, now with the real agents where possible, and keep the stand-in version as a fast regression test in `tests/`.
4. **Run these requests** and read the whole report each time:
   - "Analyze this business, identify its biggest problems, research the market, and recommend what it should do next."
   - "What are our top products in June?"
   - "What market trends affect backpacks?"
   - "Why did our revenue drop?" (check the report says total revenue rose 7.6% and that the decline is local)
5. **Inject failures on purpose:** no search key, a crashing tool, a malformed LLM output, an invented number in a draft.
6. **Build the Streamlit page** with the status badge and the run-details panel.
7. **Record the real numbers:** agent calls, LLM calls and wall-clock time per run. Day 63 needs them.
8. **Write down what is only stand-in tested.** Do not claim the real agents collaborate correctly beyond the runs you actually did.

---

## 🧠 Quiz

1. Why do most multi-agent bugs appear only after integration?
2. A research crash would have caused Strategy to be skipped under the Day 59 rule. What change prevents that, and what does the report then say?
3. Why does the Critic loop sit after the task graph and not inside it?
4. Why is the call counter protected by a lock?
5. What can stand-in agents prove, and what can they not prove?
6. Why is the report assembled by code from the state instead of being written freely by an LLM?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Whole run fails because one optional step failed | Every dependency treated as required | Separate `depends_on` from `optional` |
| Research-only request answered with "insufficient evidence" | Orchestrator demands internal analysis for every request | Require it only when the plan includes the Analyst |
| Report says "verified" after the loop gave up | No status vocabulary | Return and print an explicit status and the unresolved issues |
| Call budget overshot in parallel waves | Unlocked shared counter | Guard the counter with a lock |
| A task cannot tell which job it was given | Behaviour inferred from the inputs | Pass an explicit `task` name |
| A traceback shown to the user | Errors not caught at the boundary | Catch at `run_team` and the UI; show a readable message |
| Everything "works" but only with stand-in agents | No real runs | Do the real runs, and report which results come from which |
| HTML printed as text in Streamlit | Indented multi-line HTML in `st.markdown` | Keep each HTML fragment on one line |
| Secrets in the repo | `.env` committed | Keep `.env` and `.streamlit/secrets.toml` in `.gitignore` |

---

## ✅ Checklist

- [ ] Integrated flow and interface contracts understood
- [ ] `run_team` built with optional dependencies and a call budget (with a lock)
- [ ] Status vocabulary implemented and shown in the report
- [ ] Report assembled from the shared state, with limitations and a run log
- [ ] Every agent output validated at the handoff
- [ ] The 16 stand-in scenarios pass as automated tests
- [ ] Real-agent runs done on the four example requests
- [ ] Failure injection done
- [ ] Streamlit page built (status badge + run details)
- [ ] Real calls and timings recorded for Day 63
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 62: Integrated AI Business Intelligence Team"
git push
```

---

## 🧠 Skill Learned

Multi-agent system integration (orchestration, shared state, verification and graceful degradation working together)
