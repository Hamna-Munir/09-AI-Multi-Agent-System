# Day 59 — Orchestration and Workflow Patterns

**Objective:** Decide who works when. Build an orchestrator that routes a request to the correct agents, in the right order, running independent work in parallel only where it helps.

---

## 📖 Theory

### What orchestration is

Day 57 gave agents roles and Day 58 gave them a way to pass results. Orchestration is the layer that decides **which agents run, in what order, with what input, and what happens when one fails.** Without it you have a set of agents and no workflow.

### The four basic patterns

| Pattern | Shape | Use when |
|---|---|---|
| **Sequential** | A → B → C | Each step needs the previous step's output |
| **Parallel** | A and B at the same time → combine | Steps are independent of each other |
| **Routing** | A router picks which agent(s) handle the request | Different requests need different agents |
| **Coordinator** | One orchestrator plans, delegates and combines | You want one place that controls the whole run |

Real workflows mix them. Start sequential, then add parallelism or routing only where there is a clear reason.

### Dependencies

A task **depends on** another when it needs that task's output. Writing the dependencies down turns the workflow into a graph:

```
research ──► test_factors ──┐
                            ├──► strategy ──► critic
internal_analysis ──────────┘
```

Two rules follow from the graph:

- A task may run only after **all** the tasks it depends on have finished.
- Tasks with no dependency between them are **independent** and may run in parallel.
- A cycle (A needs B, B needs A) is a bug in the plan and must be detected.

### Waves

Grouping tasks into "waves" makes the order easy to execute: a wave is every task whose dependencies are already done. For the graph above:

```
Wave 1: research, internal_analysis      (independent → can run in parallel)
Wave 2: test_factors                     (needs research)
Wave 3: strategy                         (needs internal_analysis + test_factors)
Wave 4: critic                           (needs strategy)
```

### How this connects to Day 58

On Day 58 the Analyst tested external factors handed over by the Research Agent. That needs research first. But the Analyst's **internal** analysis (what changed in our own data) does not need research at all, so it can run at the same time. The same Analyst agent therefore appears in **two tasks** with different instructions. This is **task delegation**: the orchestrator gives an agent a specific task plus only the inputs it needs.

### Parallel execution: what it really buys

Parallel work shortens the run by the length of the shorter task in a wave. In the graph above only wave 1 has two independent tasks, so only wave 1 gains anything. Things to keep in mind:

- It pays off when tasks are slow and independent, such as a web search running beside a database analysis.
- LLM and network calls spend most of their time waiting, so threads are enough; no special framework is needed.
- It does **not** reduce cost. The same number of LLM calls happen, just at the same time.
- Free-tier APIs have rate limits, and parallel calls reach them sooner.
- It makes debugging harder, because logs interleave.

### Routing

A router reads the request and decides which agents are needed:

| Request | Agents |
|---|---|
| "What are our top products in June?" | Analyst |
| "What market trends affect backpacks?" | Research |
| "Why did revenue drop and what should we do next?" | Analyst → Strategy → Critic |
| "Analyze our sales, research the market, and recommend what to do" | Research + Analyst → Strategy → Critic |
| "hello" | none, ask the user to clarify |

Two ways to build a router:

- **Rule-based (start here):** keywords and simple conditions. Fast, free, predictable, and easy to test. Weak on unusual phrasing.
- **LLM-based:** the model classifies the request, as Week 8's classifier did. More flexible, but costs a call and can be wrong in less predictable ways.

Whichever you use, decide what happens when the router is **unsure**. Running every agent costs the most and returns the least focused answer. Guessing silently is worse. A good default is to ask the user to clarify.

### Who is in charge: coordinator patterns

| Style | How it works | Trade-off |
|---|---|---|
| **Central orchestrator** (this project) | One component plans, delegates, collects | Predictable, traceable, testable. It is a single point of failure. |
| **Peer handoffs** | Agents decide for themselves who goes next | Flexible, but hard to predict and test |
| **Hierarchical** | Sub-orchestrators manage groups of agents | Scales to big systems; too much for this project |

In this project the orchestrator is mostly **ordinary deterministic code** (graph + router). The LLM does the specialist work inside the agents. That keeps the control flow testable, which matters because the rule for this week is to claim only what can be verified.

### Failure handling at the orchestrator level

The orchestrator is where a failure is contained. Basic rules (full recovery is Day 61):

- Record every task's outcome: `ok`, `failed`, or `skipped` (with the reason).
- A failure must not crash the whole run. Independent tasks keep going.
- A task whose dependency failed is `skipped`, or runs in a reduced mode if you decide it can.
- Put a **limit on agent calls per run** so a bug cannot loop and burn your quota.
- A **timeout** is needed, but note: a Python thread cannot be cancelled. The timeout only stops *waiting* for the result; the work keeps running in the background.

---

## 💻 Coding Exercise

Build `src/orchestrator.py`: a plan (tasks with dependencies), a router, and an executor.

The executor below was run with stand-in agents (each sleeping 1 second to imitate an LLM or network call):

```python
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List

@dataclass
class Task:
    id: str
    agent: str
    depends_on: List[str] = field(default_factory=list)

def waves(tasks: List[Task]) -> List[List[Task]]:
    """Group tasks into waves: every task in a wave has all its dependencies finished."""
    done, remaining, out = set(), {t.id: t for t in tasks}, []
    while remaining:
        ready = [t for t in remaining.values() if all(d in done for d in t.depends_on)]
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
        inputs = {d: results[d]["output"] for d in task.depends_on}   # only what it needs
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

plan = [
    Task("research",  "research"),
    Task("internal",  "analyst"),
    Task("test",      "analyst",  ["research"]),
    Task("strategy",  "strategy", ["internal", "test"]),
    Task("critic",    "critic",   ["strategy"]),
]
```

And a rule-based router. This revised version returns **no steps** when it cannot tell what the user wants:

```python
def route(question: str) -> List[str]:
    q = question.lower()
    wants_external = any(w in q for w in ("market", "competitor", "industry", "external", "trend", "outside"))
    wants_internal = any(w in q for w in ("our ", "revenue", "sales", "customer", "product", "region", "orders"))
    wants_recs     = any(w in q for w in ("recommend", "what should", "next step", "advice"))
    if not (wants_external or wants_internal or wants_recs):
        return []                                   # unclear: ask the user, do not guess
    steps: List[str] = []
    if wants_external: steps.append("research")
    if wants_internal or not wants_external: steps.append("analyst")
    if wants_recs: steps.append("strategy")
    if "strategy" in steps: steps.append("critic")
    return steps
```

What was checked when running these:

| Check | Result |
|---|---|
| Waves for the plan above | `[research, internal] → [test] → [strategy] → [critic]` |
| 5 tasks of 1 s each, sequential vs parallel | about 5.0 s vs 4.0 s (only wave 1 has two independent tasks) |
| Strategy received only the inputs it depends on | yes (`internal`, `test`) |
| `research` raises an error | `internal` still `ok`; `test`, `strategy`, `critic` are `skipped` with a reason |
| A cycle in the plan (a needs b, b needs a) | detected, raises `ValueError` |
| Timeout of 0.3 s on a 2 s task | the wait stopped at 0.3 s, but the thread kept running and leaving the `with` block still took 2.0 s |
| Router on the five example requests | matches the table above; "hello" → no steps |

The first router version I tried sent "hello" to the Analyst, which is a wasted run on a meaningless request. That is why the revised version returns nothing for unclear input.

The real orchestrator, calling the real agents with the Day 58 schemas, is the exercise to build.

---

## 🛠 Mini Project

**An orchestrator that routes tasks to the correct agents**

Build it so a request goes: router → plan (tasks + dependencies) → executor → results with a status per task.

Test these, and only claim what passes:

1. **Routing table:** each example request maps to the expected agents. "hello" returns no steps and the user is asked to clarify.
2. **Order:** no agent runs before its dependencies finish (record a call log and check it).
3. **Right agent, right task:** the call log shows each agent was invoked only for tasks assigned to it.
4. **Failure isolation:** make research fail; independent tasks still finish, dependent tasks are `skipped` with a reason, and the final result says what is missing.
5. **Parallel vs sequential:** measure both with the real agents and report the real numbers. If parallel saves little, say so.
6. **Cycle and missing dependency:** bad plans are rejected before anything runs.
7. **Call limit:** the run stops cleanly at a maximum number of agent calls.

Do not call the system "working" because a single demo run succeeded. The failure cases are part of the result.

---

## 🧠 Quiz

1. What is the difference between independent tasks and dependent tasks, and which can run in parallel?
2. In the example plan, why does parallel execution only save one second out of five?
3. Why is the Analyst used in two tasks instead of two separate analyst agents?
4. A Python timeout fires after 0.3 s on a 2 s task. Has the task stopped? What does that mean for cost?
5. When would you choose an LLM-based router over a rule-based one, and what is the risk?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Everything runs sequentially "to be safe" | Dependencies were never written down | List each task's `depends_on`, then run independent ones together |
| Parallel run is no faster | Few independent tasks, or the tasks are quick | Measure; keep parallelism only where it helps |
| One failure crashes the whole run | No per-task error handling | Catch errors per task and record `failed` / `skipped` |
| Rate-limit errors when running in parallel | Free-tier limits reached sooner | Cap `max_workers`, or run that wave sequentially |
| Timeout set but the run still hangs | Threads cannot be cancelled | Treat a timeout as "stop waiting", and also limit the work itself |
| Router sends vague requests to agents | No "unclear" outcome | Return no steps and ask the user to clarify |
| Infinite loop of agent calls | No stopping condition | Add a maximum number of agent calls per run |
| Agent receives the whole state | No delegation boundary | Give each task only the inputs it depends on |

---

## ✅ Checklist

- [ ] Sequential, parallel, routing and coordinator patterns understood
- [ ] Plan written as tasks with dependencies, grouped into waves
- [ ] Router built, with an "unclear" outcome
- [ ] Executor records `ok` / `failed` / `skipped` per task
- [ ] Failure isolation tested
- [ ] Parallel vs sequential timing measured with the real agents
- [ ] Cycle detection and call limit tested
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 59: Orchestrator with routing, dependencies and parallel execution"
git push
```

---

## 🧠 Skill Learned

Orchestration + workflow patterns (routing, dependencies, parallel execution)
