# Codex / ChatGPT desktop setup

Use the desktop agent with access to the folder on this computer. Current OpenAI documentation describes these capabilities under ChatGPT desktop and Work; some installations still expose Codex names. Follow the tools and settings your installed host actually provides. The package does not depend on a specific model name.

## 1. Open the clone

Clone or extract the repository to a folder you choose, then open that exact folder as the desktop project. For the operating workspace, use the saved local checkout. A separate worktree would not contain the same ignored private database, profile, credentials, and queue.

Send this message in that project's chat, replacing the example path:

```text
Read AGENTS.md and SOCIAL_MEDIA_PLUS.md in /absolute/path/to/social-media-plus.
SMP INSTALL
Use this folder as the local operating workspace. Start the dashboard, connect
the included local MCP server, and set up the dashboard queue listener using
the native scheduling tools available in this session. Verify with STATUS.
```

`SMP INSTALL` is a project chat instruction, not a shell executable. The assistant follows the installation workflow and performs the local steps below. It should keep working through setup, while reporting any host capability that is unavailable.

## 2. Prepare and start the runtime

The assistant or a terminal on the machine can run:

```sh
cd /absolute/path/to/social-media-plus
python3 scripts/smp-install.py --root /absolute/path/to/social-media-plus --host codex
python3 scripts/smp-start.py --root /absolute/path/to/social-media-plus
python3 scripts/smp-start.py --root /absolute/path/to/social-media-plus --check
```

Quote paths that contain spaces. Installation creates private local state and generates:

- `runtime/install/codex-mcp.toml`
- `runtime/install/claude-mcp.json`
- `runtime/install/listener-prompt.md`

When the host exposes the current task ID, pass that observed ID with `--thread-id` during installation. An omitted ID uses `manual-local`, which supports manual pickup; it is not an invented host task identity or an unattended dispatch binding.

## 3. Connect the local MCP server

Inspect the generated `codex-mcp.toml`. It contains the Python executable, `scripts/smp-mcp.py`, and the selected absolute root. Use the host's MCP server settings to add that stdio server, or merge its table into the appropriate local Codex configuration without replacing other servers. Restart or reconnect as the host requires, then inspect its connected tools. Codex supports local stdio servers and project-scoped MCP configuration. [Official MCP setup](https://learn.chatgpt.com/docs/extend/mcp)

The optional Codex CLI can register the same command:

```sh
codex mcp add social-media-plus -- python3 /absolute/path/to/social-media-plus/scripts/smp-mcp.py --root /absolute/path/to/social-media-plus
codex mcp list
```

If the desktop's `PATH` differs from your shell, use the absolute Python path from the generated snippet. Adding a configuration entry is only setup; verify a read-only SMP status or queue tool succeeds in the active chat.

## 4. Load the skills and review roles

Codex discovers repository skills under `.agents/skills` from the current working directory through the repository root. Reload the project if needed. If a skill is absent from the picker, explicitly read its `SKILL.md` and follow it; report direct-file use separately from automatic discovery. [Official skill locations](https://learn.chatgpt.com/docs/build-skills)

Start with `smp-copilot`. Reviewer instructions are under `.agents/council`. Use the host's available subagent tool for independent reviews; if it is absent, label the review as sequential. Copying role files does not itself create running agents.

## 5. Register the listener in this chat

Ask the host to follow the generated `runtime/install/listener-prompt.md` and [listener guide](listener.md). The live `SMP INSTALL` request covers creating that bounded queue-checking schedule; installation does not authorize publishing or sending messages.

Use a native recurring follow-up attached to this task when supported. Otherwise use a host-supported local scheduled task in the same operating folder. Inspect and reuse an existing matching listener before creating one. Save the actual schedule ID, selected root, cadence, and verification result locally. Use the host's current model choice.

Local scheduled tasks require the computer and desktop app to be running. Web schedules cannot directly operate a folder on your computer. Select local execution when configuring the listener. [Official scheduled-task behavior](https://learn.chatgpt.com/docs/automations)

If there is no callable scheduling capability, keep the app usable and return the prepared prompt with `SMP RUN QUEUE` as the manual fallback. Do not claim a listener is installed merely because a Markdown file exists.

## 6. Verify and begin

1. Open [the dashboard](http://127.0.0.1:4010), choose LinkedIn, and use **Status** for the first request.
2. Confirm the request is saved, processed once, and shown as completed with its actual result.
3. Use `SMP START` to fill your own profile and preferences from the blank templates.
4. Use `SMP WEEK` for a reviewable content batch. Use `SMP SCHEDULE` only after the finished batch is presented and you intend to authorize its supported publishing route.

The settings form is described in [LinkedIn setup](linkedin-setup.md). Saved developer credentials do not establish OAuth authentication in this release.
