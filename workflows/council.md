# Editorial council

Use this for a meaningful draft or strategy decision. `smp-council` is the entry point; `council-review` and `llm-council` contribute to this single process. Do not run duplicate councils on the same version. Use the user's selected host model and available agents; no external provider API or hardcoded model is needed.

## Freeze one packet

Save a private packet under `content/reviews/` containing the exact draft/version/hash, intended reader, desired outcome, current brief, relevant source excerpts/links, shared `profile/context.md`, `profile/voice.md`, editorial limits and task-relevant `profile/claims.json` records. Label facts, user preferences, interpretations and unknowns. Include optional private excerpts only when necessary for this task and preserve their source/limits. Every first reviewer receives the same packet plus its role. They must not receive other reviewers' answers or the drafter's favored verdict.

## Five first passes

Use these roles from `.agents/council/`; Claude Code also has equivalent `.claude/agents/` files:

| Role | Task |
| --- | --- |
| Skeptical practitioner | Check technical/factual claims, attribution and the most plausible failure case. |
| Voice editor | Compare actual writing samples and edits; preserve personality and honest uncertainty. |
| Busy reader | Explain the main point in their own words and find what an unfamiliar reader cannot follow. |
| Fair contrarian | Present the strongest evidence-based counterargument and its boundary conditions. |
| Relationship/reputation reviewer | Check plausible misunderstanding, disclosure and how the particular audience may receive it. |

Spawn distinct first passes with fresh contexts when the host supports them. If concurrency is limited, use bounded waves with unchanged packets. Do not leak earlier results to later first passes. One reviewer cannot impersonate five independent agents. If no subagents are exposed, perform sequential passes in the active session and label the output “Sequential five-lens review by one model; not independent peer review.” Role diversity alone is not model diversity.

Each first reviewer returns its main finding, precise passage or evidence, why it matters, the smallest useful edit, a defensible strength to preserve and any remaining uncertainty. Findings need support. A reviewer should be willing to say no material concern rather than invent a problem to fill a template.

## Challenge and synthesis

For substantial or disputed work, remove role/author labels from first-pass responses and assign neutral IDs. Have available reviewers challenge the evidence and tradeoffs, including at least the strongest dissent; preserve the ID mapping privately. Anonymous review reduces some cues but does not guarantee independence or eliminate shared model errors. Scale this step to the task and state if skipped.

The synthesizer weighs reasons and source quality, not votes or self-rated confidence. Produce the revised draft or explicit strategy decision, explain accepted/rejected material edits, preserve a supported personal perspective and strongest unresolved dissent. Recheck the revised version for introduced factual changes and use Humanizer without erasing meaning. A final critic can inspect a consequential unresolved issue.

Save first passes, any challenge responses, the synthesis, final version/hash and actual review mode. Council approval is editorial evidence, never publishing permission, a claim of objective truth or a calibrated probability of correctness.
