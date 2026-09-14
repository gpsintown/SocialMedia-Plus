---
name: social
description: "Choose useful LinkedIn formats, rotation and conversational follow-up from the current user\u2019s sourced context."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
  upstream: "coreyhaines31/marketingskills"
---

# LinkedIn content formats and rotation

Read private context, voice, claims, recent content and audience goals. Select one useful contribution for a particular reader, then choose its form: concise text, explanatory image, readable PDF sequence or a longer native article if the account/tool supports it. Do not assume the user sells a product or writes for founders.

Rotate supported experience, practical explanation and defensible opinion without a forced ratio. A close can be an observation, specific question or relevant invitation. Hashtags, promotional language, exaggerated hooks and calls to action are optional, never mandatory structure. Verify current platform mechanics/limits through primary documentation or actual visible UI when they matter.

Use `linkedin-content` to draft, [weekly](../../../workflows/weekly.md) to assemble a batch and [daily](../../../workflows/daily.md) for authorized conversations. Route publishing through `smp-publish`. Instagram and YouTube are future integrations, not active cross-posting targets.

## Attribution

Adapted from the MIT-licensed social skill in [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills), revision `5b2c0007766c6a1cf1d53fd8fc73e979e0821022`. The upstream notice is preserved in `LICENSE`. Generic upstream marketing patterns have been limited to the current user's evidenced LinkedIn needs.


## Shared context and host

Before strategy, public writing, language edits, replies or review, read the private `profile/context.md`, `profile/voice.md`, `profile/editorial-policy.md` and relevant `profile/claims.json` records. Never treat templates as personal evidence. Use the user's selected Codex or Claude host model and exposed tools. The local CLI stores records; it is not a remote publisher or LLM. Current user instructions determine authorization, and no previous user's permission is included.
