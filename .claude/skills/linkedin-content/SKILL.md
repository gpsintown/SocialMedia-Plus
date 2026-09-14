---
name: linkedin-content
description: "Draft a LinkedIn post, PDF carousel or native article from a chosen brief and verified evidence while preserving the current user\u2019s voice."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
  upstream: "sarveshtalele/linkedin-content-skill"
---

# LinkedIn composer

Read the selected brief, actual user samples, claim limits, recent related posts and editorial policy. Choose structure to suit the point rather than forcing hook/list/call-to-action/hashtag patterns. Retain sources and distinguish public copy from private evidence questions.

- Text/image post: develop one point with enough context and a useful payoff. An image should explain something or serve the user's intended expression.
- PDF document: write a clear page sequence, useful caption/title and alt text. Create the actual PDF with available artifact tools, render every page and inspect order, clipping and mobile legibility.
- Native article: separate title, summary, body, references and cover brief. Use transitions and examples rather than padding. Publishing later requires the current account/editor's real capabilities.
- Calendar: use `smp-weekly`, which registers actual drafts/assets and proposed slots.

Never convert another writer's anecdote, an example metric or an AI interpretation into the user's experience. Keep estimates and attribution. Use substantial council review when useful, apply Humanizer, then compare the revised facts and meaning with sources.

Register text/version changes and final asset provenance with the CLI. Preserve specific user feedback separately from measured performance. Return complete reviewable writing; a publication request routes to `smp-publish`.

## Attribution

Adapted from the MIT-licensed generate-post skill in [sarveshtalele/linkedin-content-skill](https://github.com/sarveshtalele/linkedin-content-skill), revision `7a1f7478dfd4ea56c1f43069ba4ad8abee8bf033`. `LICENSE` retains the upstream notice. The portable runtime uses the host's selected model and the local SMP record CLI, not upstream Python/LLM scripts.


## Shared context and host

Before strategy, public writing, language edits, replies or review, read the private `profile/context.md`, `profile/voice.md`, `profile/editorial-policy.md` and relevant `profile/claims.json` records. Never treat templates as personal evidence. Use the user's selected Codex or Claude host model and exposed tools. The local CLI stores records; it is not a remote publisher or LLM. Current user instructions determine authorization, and no previous user's permission is included.
