---
name: clarifying-intent
description: Use when the user presents a vague request, idea, or problem and you need to understand intent, constraints, and success criteria before proposing solutions or taking action.
---

# Clarifying Intent

## Overview

Most wasted effort comes from solving the wrong problem. This skill slows you down just enough to make sure you understand the real question before answering it.

**Core principle:** Understand first, act second. No solution before shared understanding.

## When to Use

Use when the user says something like:
- "我想做点什么..." / "I want to do something..."
- "帮我看看这个" / "Take a look at this"
- "这个不对" / "This isn't right"
- "能不能优化一下" / "Can you optimize this?"
- "给我一些建议" / "Give me some advice"
- Any request where the goal, scope, or success criteria are unclear

**Also use when:**
- The user jumps straight to a solution ("帮我写个脚本"), but the underlying problem is unclear
- Multiple interpretations are possible
- You find yourself guessing what "good" looks like

## When Not to Use

- The request is already specific and actionable ("把文件 A 第 3 行改成 x").
- The user explicitly says "直接做" / "just do it" and the risk of misunderstanding is low.
- You are in the middle of executing an already-approved plan.

## The Process

### Step 1: Read Context

Quickly check relevant project files, recent changes, or prior conversation if they exist. Don't spend more than a minute here — the goal is to avoid asking what you could already know.

### Step 2: Ask One Clarifying Question at a Time

- Ask **one** question per message.
- Prefer multiple-choice questions when possible.
- Start broad, then narrow.

Good questions explore:
- **Why:** What is the real goal behind this request?
- **Who:** Who is this for? Who will judge success?
- **What does success look like:** How will the user know this is done well?
- **Constraints:** What is fixed, limited, or off-limits?
- **Scope:** Is this a one-off or a reusable pattern? Big or small?
- **Urgency/depth:** Quick answer or deep analysis?

### Step 3: Restate Understanding

Once you have enough information, summarize back to the user in 2-3 sentences:

> "So what I understand is: you want [X], because [Y], with [Z] as the main constraint. Is that right?"

Wait for confirmation or correction before proceeding.

### Step 4: Explore Options

If the user hasn't already chosen a direction, propose 2-3 different approaches with trade-offs. Lead with your recommendation and explain why.

### Step 5: Converge on a Shared Direction

Get explicit agreement on which option to pursue, or confirm that the user is still exploring.

### Step 6: Output a Shared Summary and Ask What Comes Next

End the clarification phase with a concise summary:

- **Intent:** What the user actually wants
- **Goal:** What success looks like
- **Constraints:** What limits or rules apply
- **Chosen direction:** What was agreed upon (if any)
- **Open questions:** What is still unclear

Then ask the user what they want to do next:

> "Based on this, what would you like me to do next? (continue, search, analyze, implement, or something else)"

**Do not assume the next step.** This skill does not force a transition to planning, coding, or any other skill. Let the user decide.

## Question Framework

If you don't know what to ask, use these in order:

1. **What problem are you trying to solve?** (not "what do you want me to build?")
2. **What would make this useful or successful?**
3. **What constraints do I need to respect?**
4. **How deep should I go?** (quick answer vs. thorough analysis)
5. **Is there anything you have already ruled out?**

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Asking 3 questions at once | One question per message |
| Proposing solutions before understanding the problem | Ask "why" first |
| Guessing the user's intent | Restate and confirm |
| Forcing a next step (writing-plans, coding, etc.) | End with "what would you like to do next?" |
| Accepting vague success criteria | Ask "how will you know this is done well?" |
| Skipping context reading | Spend 30 seconds checking what you already know |

## Quick Reference

```
Context → Question → Restate → Options → Converge → Summary + Ask next
```

- One question at a time
- Restate before solving
- Never force the next step
- Let the user choose what happens after clarification

## Red Flags — Stop and Clarify

- You feel tempted to answer immediately
- The user is describing a solution, not a problem
- You can think of more than one interpretation
- The success criteria are missing or vague
- You don't know who the output is for

When any of these appear, use this skill.
