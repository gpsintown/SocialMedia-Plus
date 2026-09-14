---
name: smp-copilot
description: "Operate the local Social Media Plus LinkedIn workspace: installation, profile, weekly writing, review, engagement, publishing and analysis."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
---

# Social Media Plus copilot

Resolve the project root from this skill (`../../..`). Read `AGENTS.md`, `SOCIAL_MEDIA_PLUS.md`, private settings and the command contract. If initialization is needed, route to `smp-install`; otherwise inspect `python3 scripts/smp status` and unresolved actions. Use only the actual current CLI options from `--help`.

| Intent | Skill or workflow |
| --- | --- |
| Install, host setup, listener | `smp-install`, [install](../../../workflows/install.md) |
| Personal brief, resume, writing samples | [Profile](../../../workflows/profile.md) |
| Full week or revisions/assets | `smp-weekly`; use `content-strategy`, `social`, `linkedin-content` |
| Meaningful draft or strategy critique | `smp-council` |
| Daily comments/replies or preview | `smp-daily` |
| Plus engagement / optional hiring outreach | [ENGAGE+](../../../workflows/engage-plus.md) / [RECRUITER+](../../../workflows/recruiter-plus.md) |
| Exact named publishing/scheduling instruction | `smp-publish` |
| Import, performance review, experiments | `smp-analyze` |
| Eight-week review | [Pilot review](../../../workflows/eight-week.md) |
| Dashboard requests | [Queue](../../../workflows/dashboard-queue.md) |
| User asks about Postiz compatibility | `postiz` reference only |

Reuse completed work, the user's edits and valid exact-item authorization. WEEK prepares and presents; SCHEDULE is a separate instruction for a finished batch. Live session commands have only their documented scope. Complete the concrete artifact before asking for any missing final instruction. A configured route/tool is not proof of an external action.

Finish by saving actual artifacts and receipts, uncertainties and the next useful step. Keep profile, sources, generated registration files and reports private. State precise tool/host limitations and continue independent local work where possible.


## Shared context and host

Before strategy, public writing, language edits, replies or review, read the private `profile/context.md`, `profile/voice.md`, `profile/editorial-policy.md` and relevant `profile/claims.json` records. Never treat templates as personal evidence. Use the user's selected Codex or Claude host model and exposed tools. The local CLI stores records; it is not a remote publisher or LLM. Current user instructions determine authorization, and no previous user's permission is included.
