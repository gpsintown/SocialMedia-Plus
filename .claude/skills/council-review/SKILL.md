---
name: council-review
description: "Apply distinct evidence-first editorial reasoning methods to a substantial draft or strategy within the shared SMP council."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
  upstream: "ngmeyer/skills"
---

# Reasoned editorial review

Use [the shared council workflow](../../../workflows/council.md) and the role files in `.agents/council/`. Decompose substantive claims, inspect available support and missing assumptions, compare actual voice samples, read as an unfamiliar audience, strengthen a reasonable counterargument and examine plausible communication consequences.

Keep reviewers' first judgments separate and include the precise passage/evidence behind each proposed edit. A useful reviewer can find a strength to preserve or no material concern. Do not invent objections, calibrated probabilities or consensus scores. Evidence can defeat a majority.

Use supported agents with the user's selected host model. If only sequential review is available, state that. When invoked with `smp-council` or `llm-council`, contribute to the same existing first-pass packet and synthesis; do not duplicate the process. Recommendations never authorize publishing.

## Attribution

Adapted from the MIT-licensed council-review skill in [ngmeyer/skills](https://github.com/ngmeyer/skills), revision `701dfb8bd2ffe22f6aeccc310b6eea3b20462bf1`. The upstream notice is preserved in `LICENSE`. This distribution uses host-neutral project roles and does not require upstream model commands or setup hooks.


## Shared context and host

Before strategy, public writing, language edits, replies or review, read the private `profile/context.md`, `profile/voice.md`, `profile/editorial-policy.md` and relevant `profile/claims.json` records. Never treat templates as personal evidence. Use the user's selected Codex or Claude host model and exposed tools. The local CLI stores records; it is not a remote publisher or LLM. Current user instructions determine authorization, and no previous user's permission is included.
