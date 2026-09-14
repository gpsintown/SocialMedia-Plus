# Council roles in Codex and Claude

The council checks a substantial draft before you use it. Five roles examine its factual support, voice, clarity, opposing arguments and likely effect on readers. Each starts with the same saved draft, context and sources; the final review decides which edits the evidence supports. Codex reads the canonical role files in `.agents/council/`; Claude Code has matching project agent definitions in `.claude/agents/`. The same content skills are present under `.agents/skills/` and `.claude/skills/`.

| Host | How to use |
| --- | --- |
| Codex with subagent tools | Pass each canonical role and the identical frozen packet to a separate agent. Use fresh-context waves if needed. |
| Claude Code with project agents | Read the project instructions and invoke the corresponding supported agent tool with the frozen packet. Verify that the current installation discovers the definitions. |
| Claude Desktop or Cowork | Explicitly read the shared folder's `CLAUDE.md`, selected skill and role files. Use independent agents only if the current host actually exposes them; repository files do not grant that capability. |
| Any host without agents | Perform sequential lenses, preserve their reasoning and label the result as one model's review. |

See [the complete workflow](../workflows/council.md). No model, reasoning effort, account identity, session ID or private user context is baked into the roles. Each reviewer receives only the current user's selected evidence.

The MIT-licensed council-review adaptation retains its notice. The privately consulted upstream LLM Council snapshot lacked a redistribution license, so its source text is excluded. The public `llm-council` entry is newly written project instructions for generic peer review; it ships no unlicensed upstream implementation or prompt text. The roles can use the same selected model. Agreement is a review result, not proof that a claim is true.
