# Social Media Plus

A local LinkedIn editorial and relationship workspace for **Codex / ChatGPT
desktop Work** and **Claude Desktop / Cowork**. Clone a folder, open it with your
desktop agent, and work through a dashboard or ordinary chat commands.

Your selected desktop model does the reasoning. Python stores records in SQLite;
the dashboard writes requests for your agent to process. No separate LLM API key,
PostgreSQL server, Postiz service or Docker installation is needed.

## What it helps with

- Build a private profile and writing voice from information you choose to supply.
- Prepare a week of sourced LinkedIn posts, articles and carousel briefs, with
  assets produced using available host tools.
- Review drafts through five editorial lenses and preserve useful disagreement.
- Organize observed connections, followers, conversations and follow-ups.
- Run contextual engagement sessions through an authorized browser-capable agent.
- Record exact content versions, approvals, scheduling receipts and uncertain
  attempts so a restart does not cause duplicate submissions.
- Import LinkedIn exports and analyze available metrics without inventing data.

**Available:** local dashboard, SQLite records, command queue, private credential
settings, local MCP server, profile templates and portable agent workflows.
**Host-dependent:** research, images/PDFs, browser actions and scheduled queue
pickup require the appropriate tools and permissions in your desktop session.
**Planned:** direct LinkedIn OAuth/API publishing and analytics adapters;
Instagram, YouTube and additional platform integrations.

Saving developer credentials does **not** connect your LinkedIn account. This
release uses your authorized browser session for LinkedIn actions. The dashboard
provides configuration storage for future API adapters, with setup instructions
that distinguish basic products from restricted access.

## Start here

1. Install Python **3.11+** and an appropriate desktop agent. See
   [prerequisites](docs/prerequisites.md) for host, browser and OS limits. A
   compiled dashboard is included; Node is only needed to edit the UI.
2. Clone or download this repository to a permanent folder. Open that **same
   folder** as a local project or grant Cowork access to it. GitHub Desktop can
   clone the repository; it does not execute the agent workflows.
3. In the project chat, send:

   ```text
   Read AGENTS.md and SOCIAL_MEDIA_PLUS.md in this folder. SMP INSTALL
   ```

   If the host does not read project instruction files automatically, attach or
   explicitly reference them. Follow [Codex setup](docs/codex-setup.md) or
   [Claude setup](docs/claude-setup.md).
4. The agent initializes your private workspace and starts the local dashboard.
   It also configures a scheduled queue listener **when that host exposes the
   required capability**, then verifies a harmless STATUS request. Otherwise it
   gives you the exact manual listener setup or `SMP RUN QUEUE` fallback.
5. Open [the local dashboard](http://127.0.0.1:4010). Select LinkedIn to save your
   developer-app settings to ignored `.env.local`. Follow the
   [step-by-step LinkedIn guide](docs/linkedin-setup.md) if you want to prepare API
   credentials; they are not required for browser-based drafting and engagement.
6. Add your own profile, writing samples and preferences to the private files
   initialized under `profile/`. A résumé is optional unless you enable a
   workflow that specifically needs it.

For terminal setup from the cloned folder:

```sh
python3 scripts/smp-install.py --root . --host codex
python3 scripts/smp-start.py --root .
```

Use `--host claude` for Claude. The terminal installer initializes files and
generates host setup material; it cannot create a desktop scheduled task by
itself. Read [listener setup](docs/listener.md) to finish the host step.

## Daily use

Weekly preparation:

```text
SMP START
SMP WEEK <Monday date>
SMP SCHEDULE <the same Monday date>
```

Send SCHEDULE after reviewing the finished batch. It authorizes the exact
completed content, assets, destination and times presented to you.

For daily conversations, use `SMP ENGAGE 30 preview` to draft a shortlist or
`SMP ENGAGE 30` to authorize contextual comments and replies for that session.
See the [command guide](SOCIAL_MEDIA_PLUS.md) for focused modes and optional
outreach. Installation grants no standing publishing or outreach permission.

Dashboard buttons create durable requests. The Runs screen reports whether a
request is queued, executing, complete or needs reconciliation. A queued request
is not evidence of an external action. Scheduled listeners are host-managed
polling, not an operating-system file watcher that can run an AI model on its own.
Keep the required computer and desktop app running for local scheduled tasks.

## What is in the folder

| Location | Purpose |
| --- | --- |
| `src/`, `scripts/` | Standard-library Python records, local HTTP server, installer and MCP |
| `ui/src/`, `ui/dist/` | Editable React dashboard and ready-to-run build |
| `.agents/skills/` | Codex-compatible skills and common workflow entry points |
| `.claude/skills/`, `.claude/agents/` | Claude skill copies and council role definitions |
| `templates/` | Blank profile and configuration defaults |
| `workflows/`, `docs/` | Operational workflows and sourced setup guides |
| `tests/` | Tests using isolated temporary workspaces |
| `profile/`, `data/`, `runtime/` | Created on install; private and ignored by Git |

The [architecture guide](docs/architecture.md) explains how dashboard requests,
the file notification, SQLite, MCP and desktop agents fit together.

## Share a clean copy

Publish a clean source export, not your populated daily workspace or its history:

```sh
python3 scripts/release-check.py
python3 scripts/build-release.py --output ../social-media-plus-source.zip
```

The ZIP is assembled from a public file allowlist and includes a SHA-256 manifest.
It excludes databases, résumés, profile files, `.env.local`, private settings,
host/task IDs, exports and installed dependencies. The scanner checks common
credential patterns; it is not a guarantee that arbitrary text contains no
personal information. Review the extracted files before pushing them to GitHub.

Only `.env.example` belongs in Git. Never commit a populated `.env.local`, even
if a tutorial elsewhere suggests doing so. See [security](SECURITY.md),
[contributing](CONTRIBUTING.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

MIT licensed, with separate preserved notices for included third-party material.
Independent community project; not affiliated with LinkedIn, OpenAI or Anthropic.
