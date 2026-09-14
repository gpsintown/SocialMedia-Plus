---
name: llm-council
description: "Use a shared evidence packet, separated initial judgments and an evidence-weighted synthesis for portable editorial peer review."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
---

# Peer review and synthesis

This is newly written project guidance for generic peer review. It includes no source text, code or prompt from the unlicensed upstream snapshot consulted in the original private project. It requires no downloaded council runtime, fixed model or external provider API.

Follow [the shared workflow](../../../workflows/council.md). Put the actual artifact and the same evidence into a frozen packet. Ask each supported reviewer to reason from that packet before reading another judgment. Preserve the original responses privately. For a consequential disagreement, remove identifying labels, assign neutral response IDs and ask available reviewers to test the reasons and missing evidence.

The synthesizer must say what conclusion follows, which edits address the actual concerns, which objections do not hold and which uncertainty remains. Choose based on evidence and the user's communication goals rather than vote totals. A reviewer count is not an independent verification count, and model agreement is not a measured probability.

Use this as one stage of `smp-council` alongside the five editorial roles, not a second five-agent exercise. If the host has no subagents, perform a clearly labelled sequential review by one model. Save actual review mode and the final version. A review outcome does not grant publishing permission.


## Shared context and host

Before strategy, public writing, language edits, replies or review, read the private `profile/context.md`, `profile/voice.md`, `profile/editorial-policy.md` and relevant `profile/claims.json` records. Never treat templates as personal evidence. Use the user's selected Codex or Claude host model and exposed tools. The local CLI stores records; it is not a remote publisher or LLM. Current user instructions determine authorization, and no previous user's permission is included.
