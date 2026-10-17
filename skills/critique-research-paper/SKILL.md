---
name: critique-research-paper
description: Critically review research papers, preprints, technical reports, benchmark papers, and agent/system papers to identify inflated claims, weak novelty, unfair evaluations, missing controls, reproducibility gaps, and hidden assumptions. Use when the user asks to read a paper with skepticism, distinguish real contributions from repackaging or hype, diagnose why a paper is flawed, design stronger methods/evaluations, convert a weak paper into better research directions, or extract lessons from a failed/problematic paper.
---

# Critique Research Paper

## Purpose

Use this skill to turn paper reading from passive summary into disciplined research judgment. The goal is not to be negative by default; the goal is to determine whether the paper's claims are earned, identify exactly where the evidence fails, and convert the failure into better research design.

## Core Principles

1. Separate claim, mechanism, evidence, and rhetoric. Do not let impressive terminology substitute for a precise contribution.
2. Steelman before attacking. First state the strongest plausible version of the paper's contribution, then audit whether the paper actually proves it.
3. Compare against the right counterfactual. Ask what would happen with the same model, tools, budget, prompts, workflow, and domain tuning in a strong baseline.
4. Treat evaluation as part of the method. Baseline choice, compute budget, data access, tool access, leakage controls, metrics, and statistical uncertainty are not details; they determine whether the result means anything.
5. Diagnose before prescribing. Name the failure mode precisely, then propose the smallest stronger experiment, ablation, or redesign that would resolve it.
6. Extract insight from weak work. If the paper is flawed, identify the real unsolved problem it points toward and suggest a cleaner research direction.
7. Calibrate confidence. Distinguish confirmed defects, likely defects, missing evidence, and taste-level concerns.

## Default Workflow

1. Build a paper map.
   - Identify the stated problem, main claims, proposed method/framework, experiments, conclusions, and claimed novelty.
   - If possible, extract exact section/table/figure references from the paper.

2. Audit novelty.
   - Translate new terms into older concepts or known patterns.
   - Check whether the paper cites and fairly positions the closest prior work.
   - Flag "renaming as innovation" only when the mechanism is substantially already known and the paper does not clearly explain the delta.

3. Audit method and framework design.
   - Identify the actual technical unit of contribution: algorithm, architecture, harness, dataset, prompt/workflow, benchmark, tooling, or system integration.
   - Check whether components are specified precisely enough to reimplement.
   - Check whether the framework is being credited for gains that may come from benchmark-specific agents, hand-tuned prompts, extra tools, caching, or test-time compute.

4. Audit evaluation.
   - Baselines: Are they strong, current, task-relevant, and configured competently?
   - Fairness: Are model, tools, prompts, workflow depth, search budget, parallelism, time, tokens, and retry policies comparable?
   - Metrics: Do they measure the paper's claimed capability, or only a proxy?
   - Ablations: Are all core design choices isolated?
   - Statistics: Are there multiple runs, confidence intervals, variance, or significance tests where stochasticity matters?
   - Leakage: Could benchmark solutions, cached knowledge, web retrieval, training contamination, or post-hoc prompt tuning leak task-specific information?
   - Scope: Does the benchmark support the conclusion, or does the paper overgeneralize?

5. Audit reproducibility.
   - Look for code, prompts, configs, logs/trajectories, model versions, seeds, temperature, hardware, costs, tool versions, and benchmark splits.
   - Treat "we log trajectories" as insufficient unless the logs needed to verify the reported results are released or described.

6. Convert critique into better research.
   - For each major flaw, propose a concrete fix: stronger baseline, fairer budget, ablation, new metric, blinded evaluation, preregistered protocol, release artifact, or redesigned architecture.
   - When possible, give a minimal viable experiment and an ideal rigorous experiment.

7. Extract deeper insight.
   - Ask what important problem remains after stripping away the paper's hype.
   - Suggest research questions that would still matter if this paper's main claim failed.

## Red Flags To Actively Check

- Novelty by naming: new labels for ReAct loops, self-critique, planner-executor, multi-agent roles, memory, tool registries, or YAML configuration without a clear technical delta.
- Framework/method confounding: a general framework is evaluated through heavily customized per-benchmark pipelines.
- Weak baseline theater: comparison against an easy or poorly matched baseline while ignoring stronger systems.
- Unequal test-time compute: more agents, more retries, more search, more sampling, or more tool calls without cost-normalized results.
- SOTA overclaiming: tiny margins without confidence intervals, single-run results, or missing strong baselines.
- Missing ablations: no component-level evidence for the named contribution.
- Benchmark laundering: results on QA/retrieval/engineering benchmarks used to claim broad scientific discovery capability.
- Reproducibility by assertion: claims of auditability without released configs, prompts, logs, seeds, and exact versions.
- Leakage risk: use of web search, cached "past insights", public leaderboard tasks, or benchmark-specific knowledge without controls.
- Narrow limitations: limitations section admits only peripheral issues while ignoring evaluation and evidence weaknesses.

## Redesign Checklist

When proposing improvements, make the redesign testable.

- Problem formulation: Replace broad slogans with a falsifiable research question and a target capability.
- Framework design: Define the real unit of contribution, the abstraction boundary, required APIs, interchangeable components, and what should transfer across tasks without retuning.
- Evaluation protocol: Use strong task-relevant baselines, equalize test-time compute, report cost-quality tradeoffs, include human or expert references when useful, and preregister comparison rules when benchmark tuning is likely.
- Ablation plan: Isolate each claimed mechanism with remove-one-component, swap-component, and port-to-another-framework tests.
- Generalization test: Evaluate on unseen domains, new benchmark splits, or held-out tasks that were not used to design prompts/workflows.
- Reproducibility package: Require exact prompts, configs, model versions, tool versions, seeds, logs/trajectories, hardware, wall-clock time, token counts, and per-instance results.
- Claim rewrite: Downgrade the conclusion until it is exactly supported by the evidence.

## Output Modes

Use the user's requested depth. If unspecified, produce a concise but substantive review.

### Quick Triage

Use for early screening.

```markdown
**Verdict**
One paragraph on whether the paper's central claim is credible.

**Main Issues**
- [Severity] Issue: evidence and why it matters.

**What Would Fix It**
- Concrete experiment, ablation, or rewrite.

**Research Value**
What can still be learned from the paper.
```

### Full Critical Review

Use when the user asks for careful reading or review.

```markdown
**Verdict**
Calibrated overall assessment.

**Claim-Evidence Audit**
| Claim | Evidence Offered | Gap | Severity | How To Fix |
|---|---|---|---|---|

**Core Problems**
Ordered by severity. Include section/table/figure references where available.

**Evaluation Redesign**
Stronger baselines, fairness controls, metrics, ablations, budgets, and reproducibility artifacts.

**Method Redesign**
How to reformulate the framework/method so the contribution becomes real and testable.

**Deeper Research Opportunities**
Important unresolved questions exposed by the paper's weaknesses.

**What To Learn**
Useful ideas, engineering patterns, or cautionary lessons worth carrying forward.
```

### Research Direction Memo

Use when the user wants to turn a flawed paper into future work.

```markdown
**Real Problem**
The non-hype version of the problem.

**Why Existing Evidence Fails**
Concise diagnosis.

**Better Research Questions**
3-6 questions, each with why it matters.

**Proposed Study**
Framework, evaluation protocol, baselines, ablations, expected failure modes.

**Minimum Convincing Result**
What evidence would make the claim believable.
```

## Severity Scale

- P0: Fatal to the central claim.
- P1: Seriously weakens the main contribution or conclusion.
- P2: Important but fixable limitation.
- P3: Presentation, positioning, or minor methodological concern.

## Interaction Guidance

- If the paper is not available locally or in the prompt, ask for the PDF/link/title only when it cannot be discovered safely.
- If the user has domain expertise or an initial critique, incorporate it explicitly and test it against the paper.
- Match the user's language unless they request otherwise.
- Prefer precise criticism over broad dismissal. Say "the paper does not establish X because..." rather than "this is bad".
- Give authors a path to make the work stronger. Every major criticism should have a corresponding fix or deciding experiment.
- Avoid generic praise. If noting strengths, connect them to concrete reusable lessons.
- For current publication status, benchmarks, code availability, or external claims, verify with current sources when needed.
