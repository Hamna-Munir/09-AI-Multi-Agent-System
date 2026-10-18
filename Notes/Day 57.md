# Day 57 — Multi-Agent Fundamentals

**Objective:** Understand what a multi-agent system is, when it is actually worth using, and build two specialised agents with clearly different responsibilities.

---

## 📖 Theory

### What is an agent? (quick recap)

An agent is an LLM that works toward a goal using **instructions** (its role), **tools** (things it can do), and **state** (what it knows so far). Weeks 5-8 built single agents: an email agent, a meeting agent, a business agent.

### What is a multi-agent system?

A system where **several agents, each with its own role and tools, work on one larger task and pass results to each other.** One more component usually sits on top: an **orchestrator** that decides which agent works when and how their results are combined.

A useful analogy is a small consulting team. A researcher gathers market information, an analyst crunches the company's numbers, a strategist writes recommendations, and a reviewer checks the final report before it goes out. Nobody does everything, and everyone has a different job.

### Single agent vs. multiple agents

| | Single agent | Multi-agent system |
|---|---|---|
| Structure | One LLM + all tools + one long context | Several agents, each with a focused role, tools, and context |
| Strength | Simple, fast, cheap, easy to debug | Specialisation, independent checking, parallel work |
| Weakness | Long prompts and many tools can blur its focus | More LLM calls, slower, more things that can fail |
| Best for | Tasks that fit in one head | Tasks with distinct parts or that need independent verification |

### Specialised roles

A role is defined by four things. If you cannot fill all four in, the agent should not exist:

1. **What it owns** (its one responsibility)
2. **What tools only it may use**
3. **What it produces** (a defined output)
4. **What it must not do**

For this week's project:

| Agent | Owns | Its tools | Must not |
|---|---|---|---|
| Research Agent | External evidence about the market | Web search | Touch the company database |
| Analyst Agent | The company's own numbers | Business database tools | Make claims about the outside world |
| Strategy Agent | Turning findings into recommendations | Reads others' findings | Invent new data |
| Critic Agent | Checking evidence and accuracy | Reads the draft + evidence | Write the report itself |
| Orchestrator | Planning, routing, combining | Shared state | Do specialist work |

### Collaboration

Agents collaborate by passing **results**, not by chatting freely. In a good design each handoff is a defined piece of data ("here are the findings and where they came from"), so the next agent knows exactly what it is receiving. Structured handoffs are Day 58; this day only separates the responsibilities.

### Orchestration

Orchestration is the "who works when" logic. Simple patterns (Day 59 covers them properly):

- **Sequential:** A → B → C
- **Parallel:** A and B at the same time, then combine (works when they do not depend on each other)
- **Routing:** a coordinator picks the right agent for the request

Start with sequential. Add the others only where they clearly help.

### When is multi-agent actually worth it?

Use it when at least one of these is true:

- **The task has distinct parts** that need different tools, context, or instructions.
- **Parts are independent** and can run in parallel.
- **You need independent verification.** A reviewer that did not write the answer is more likely to catch its mistakes than the writer reading its own work.
- **One context would get too crowded.** Giving each agent only what it needs keeps each focused.

Do **not** use it when:

- A single agent with good tools can already do the job.
- The steps are tightly coupled and need to share all context.
- Cost or latency matters more than the extra quality.

### An honest check for this project

Week 8's Business Agent already answered "why did revenue drop?" as one agent. So why split it up? The real reasons here are (1) **verification**: a Critic that did not write the report can check it, and (2) **separation of evidence**: internal numbers and external research are kept apart and labelled, and (3) it is the skill this week is meant to teach. The cost is real: more LLM calls, a slower run, and more places for things to go wrong. Day 63 measures that cost instead of assuming it is worth it.

### Why more agents is not better

Every agent adds LLM calls, latency, and a handoff where information can be lost or distorted. Two agents agreeing does not make an answer correct, and an error made early can be passed along and presented confidently by later agents. Each agent must earn its place.

### Same pattern, new structure

Week 8's single class did classify → plan → tools → analyse → research → report in one place. In Week 9 the same ideas are split by responsibility: the Analyst takes the internal-data part, the Research Agent takes the external part, and recommendations and checking become their own agents.

---

## 💻 Coding Exercise

Build **two specialised agents with different responsibilities**: an **Analyst Agent** and a **Research Agent**.

| | Analyst Agent | Research Agent |
|---|---|---|
| Responsibility | Analyse the company's own business data | Find external market information |
| Allowed tools | Database tools (reuse Week 8's `get_top_products`, `get_product_sales`, `get_regional_trend`) | `search_external_information` only |
| Input | A task, e.g. "What are the top products in June?" | A task, e.g. "What market factors affect backpack sales?" |
| Output | Numeric findings from real tool results | Sources (title + URL + snippet), or an explicit "research unavailable" |
| Must not | Make claims about the outside world | Read the company database |

The core idea is a **tool permission guard**, so a role is enforced by code and not just by the prompt:

```python
from dataclasses import dataclass
from typing import Callable, Dict

@dataclass
class Agent:
    name: str
    role: str                      # one-sentence responsibility
    tools: Dict[str, Callable]     # ONLY these tools may be called

    def use_tool(self, tool_name: str, **kwargs):
        if tool_name not in self.tools:
            raise PermissionError(f"{self.name} is not allowed to use '{tool_name}'")
        return self.tools[tool_name](**kwargs)

analyst = Agent("Analyst", "Analyse the company's own business data",
                {"get_top_products": get_top_products})
researcher = Agent("Researcher", "Find external market information",
                   {"search_external_information": search_external_information})

analyst.use_tool("search_external_information", query="x")   # PermissionError
```

(This guard was run with stand-in tools and behaves as shown. The real agents, with the LLM and the real tools, are the exercise to build.)

Rules for this exercise:

- No communication between the agents yet. Each runs on its own. Handoffs are Day 58.
- The LLM may be used for judgement (writing a search query, summarising), but **numbers must come from tool results**, never from the LLM.
- If the Research Agent has no `TAVILY_API_KEY`, it must say research is unavailable and must not invent sources.

---

## 🛠 Mini Project

**Two-Agent Split**

1. **Paper exercise first.** Take the request: *"Why did our revenue drop, and what is happening in the market?"* Write down which half goes to the Analyst and which to the Research Agent, and what each must hand back.
2. **Run each agent separately** on its half.
3. **Test the boundaries:**
   - Analyst asked to use the search tool → `PermissionError`
   - Research Agent asked to query the database → `PermissionError`
   - Research Agent with no search key → returns "unavailable", no invented sources
4. **Compare with Week 8.** Write two sentences: what did splitting gain, and what did it cost (extra LLM calls, extra code)?

What counts as done: you can show each agent's real output and the three boundary tests actually failing safely. Do not claim the agents "collaborate" yet, because nothing is handed between them until Day 58.

---

## 🧠 Quiz

1. Name the four things that define an agent's role. What does it mean if you cannot fill all four?
2. Give two situations where a single agent is the better choice than a multi-agent system.
3. Why is a Critic that did not write the answer more useful than asking the writer to double-check?
4. What is the difference between enforcing a role in the prompt and enforcing it in code?
5. Two agents give the same answer. Does that prove it is correct? Why or why not?

*(Try answering from memory first, then check the theory section above.)*

---

## 🐞 Common Errors

| Error | Likely Cause | Fix |
|---|---|---|
| Two agents do almost the same thing | Roles not clearly separated | Write each agent's owns / tools / output / must-not before coding; merge agents that overlap |
| Agent uses a tool it should not | Role only described in the prompt | Add a permission check in code (`allowed tools`) |
| LLM invents numbers | Agent allowed to answer without a tool result | Numbers come only from tool results; the LLM writes prose around them |
| Agent invents sources when search is off | No "unavailable" path | Return an explicit unavailable result and say so in the output |
| Handing over the whole chat history | No defined handoff | Pass a structured result (Day 58) |
| Too many agents for a simple task | Splitting for its own sake | Ask "does this agent own something no other agent does?" |
| Claiming "the agents collaborated" without evidence | Nothing was verified | Only claim what you can show: real handoffs, real outputs, real failures |

---

## ✅ Checklist

- [ ] Multi-agent vs. single-agent difference understood
- [ ] Role defined for each agent (owns / tools / output / must not)
- [ ] Analyst Agent built, using real database tool results
- [ ] Research Agent built, with an honest "unavailable" path
- [ ] Tool permission guard tested (both directions)
- [ ] Two-sentence comparison with Week 8 written
- [ ] Git commit made

---

## 📂 GitHub Push

```bash
git add .
git commit -m "Day 57: Multi-agent fundamentals + two specialised agents"
git push
```

---

## 🧠 Skill Learned

Multi-agent fundamentals + specialised agent design
