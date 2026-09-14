# 🎛️ Make the workspace yours

Your profile guides the work: which people the copilot looks for, which conversations it joins, what it writes and which opportunities it considers. Set your niche, intended audience, objectives, writing style and private boundaries. Installation creates editable, Git-ignored working files from the public [templates](../templates/). You can update them through your project chat or edit them directly.

## 1. Give the agent a starting brief

For example, send this in your project chat, replacing the illustrative details:

```text
Personalize this workspace using only the information I provide.
My focus is helping small product teams improve customer onboarding.
My audience is product leads and customer-success managers.
My objective is useful professional conversations and sharing practical lessons.
My tone is thoughtful, plain-spoken and warm. Use short paragraphs and light humor.
Avoid sales language, automatic questions at the end and unsupported result claims.
Keep employer details and job-search intentions private.
Start with two posts a week. Ask me for my timezone before setting posting times.
Save the brief and show me the changes. Do not publish or contact anyone.
```

The example is a starting point, not an assumed identity. Name the actual topics and outcomes you care about: learning in public, peer relationships, explaining your work, business development or a carefully scoped career objective.

## 2. Know what to personalize

These paths are created locally during installation; the links point to their blank source templates.

| Dimension | Working file | What to add |
| --- | --- | --- |
| Identity, goals and audiences | `profile/profile.json` ([template](../templates/profile/profile.json)) | Your name, account URL, expertise, desired outcomes and intended readers |
| Professional context | `profile/context.md` ([template](../templates/profile/context.md)) | Work you can discuss, relevant experience, exclusions and source references |
| Tone and style | `profile/voice.md` ([template](../templates/profile/voice.md)) | Your writing samples, preferred phrasing, paragraph length, humor and edits |
| Evidence | `profile/claims.json` ([template](../templates/profile/claims.json)) | Claims with sources, caveats and unresolved facts; avoid invented credentials or metrics |
| Editorial boundaries | `profile/editorial-policy.md` ([template](../templates/profile/editorial-policy.md)) | What is public, private, off-limits or requires review |
| Cadence and content mix | `config/settings.json` ([template](../templates/config/settings.json)) | Timezone, audiences, content pillars, weekly frequency and time windows |

Keep JSON valid when editing it directly. Ask the agent to review consistency across the files when you change an objective or boundary.

## 3. Calibrate with your actual writing

Supply two or three samples you wrote and are comfortable sharing with your chosen AI host. Explain what you like about them. Ask for a short draft, then edit the parts that do not sound like you.

Tell the copilot what to change: “use a concrete example before the conclusion,” “less formal,” or “I would never say this phrase.” Ask the agent to save the preference in your voice file. Review [the profile workflow](../workflows/profile.md) for evidence and calibration handling.

A style preference never creates personal experience: a confident tone is not permission to invent a result, anecdote or quotation. Resolve conflicting facts before turning them into public claims.

## 4. Set public and private boundaries

Specify topics, client names, employer information, personal details and career intentions that must stay private. Store sensitive supporting material only in the private locations described by the profile workflow. You do not need to supply a résumé for ordinary content planning.

Local storage does not mean offline AI processing. Information you give your desktop host or browser tools may be processed by their services under your account settings. Share only the context you want those tools to use.

## 5. Test the fit before going live

Ask for a draft or use `SMP ENGAGE 30 preview`. Check both the writing and the selection: are these the people and conversations you want to spend time on? Review accuracy, tone and privacy too. Refine your files as your objectives evolve; the workspace keeps context across sessions.

Use the [command guide](../SOCIAL_MEDIA_PLUS.md) to understand each action's scope. `SMP WEEK` prepares content; `SMP SCHEDULE` authorizes a finished batch. Live engagement commands authorize their documented session actions. Optional outreach needs its own explicit scope and supporting setup; personalization alone authorizes no external action.
