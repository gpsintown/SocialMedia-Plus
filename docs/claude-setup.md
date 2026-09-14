# Claude Desktop / Cowork setup

Connect Claude Desktop / Cowork to this local folder so it can read your profile, process dashboard requests and use available browser tools for LinkedIn work. Verify that the session can reach the included local MCP server. Claude Code is an alternative when your Cowork session lacks the required local access.

## 1. Check the execution environment

Open Claude Desktop, select Cowork if available to your account, and connect the clone folder. Ask Claude to identify whether its shell, local MCP tools, and browser operate on the machine that holds this folder. Cowork's capabilities and execution modes depend on the installed version and account configuration. [Cowork getting started](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)

Current Anthropic documentation distinguishes cloud sessions from local desktop sessions. Local code execution can run inside a VM, while local MCP servers run on the device; cloud sessions do not run local MCP servers. Device access depends on the connected desktop app. This package requires a verified route to its persistent local files and local runtime. [Cowork architecture](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview)

Send this message, replacing the path:

```text
Read CLAUDE.md and SOCIAL_MEDIA_PLUS.md in /absolute/path/to/social-media-plus.
SMP INSTALL
Use that folder as the local operating workspace. Verify local file, command,
MCP and browser access. Start the dashboard on the computer that owns the
folder, and set up a local dashboard queue listener if your available native
scheduler can access it. Use STATUS to verify. Report unsupported steps.
```

## 2. Prepare the local runtime

Run these on the computer containing the clone, either through a verified local tool or its ordinary terminal:

```sh
cd /absolute/path/to/social-media-plus
python3 scripts/smp-install.py --root /absolute/path/to/social-media-plus --host claude
python3 scripts/smp-start.py --root /absolute/path/to/social-media-plus
python3 scripts/smp-start.py --root /absolute/path/to/social-media-plus --check
```

The installer generates MCP settings and a listener prompt under `runtime/install/`. With no observed session ID it chooses `manual-local` for manual pickup. A host exposing its actual session ID may bind that ID using `--thread-id`. Never manufacture a Claude conversation ID.

Open [the dashboard](http://127.0.0.1:4010) in your desktop browser. If it only opens inside a VM, the local installation is not yet verified. Keep the server on the machine that owns the clone; do not expose it through a public tunnel to compensate.

## 3. Connect the local MCP server

Read `runtime/install/claude-mcp.json`. Add or merge its `social-media-plus` entry using the local MCP configuration interface supported by your Claude Desktop version. Preserve existing entries. Restart or reconnect, then verify the SMP tools appear and a status read works. The generated file is a configuration snippet, not a signed or installable desktop-extension bundle. Anthropic documents local MCP status in Desktop's Developer settings and connector list. [Local MCP setup and status](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)

If your Cowork mode cannot load this local server, use a supported local Claude Code session or manual CLI workflow. A remote MCP connector cannot reach a private stdio process simply by entering `127.0.0.1` as a URL.

## 4. Load portable skills and agents

For Cowork, have Claude explicitly read `CLAUDE.md`, the `.agents/skills/smp-copilot/SKILL.md` entry point, and its linked workflow from the connected folder. This direct-file route does not depend on a slash-command picker.

The `.claude/skills` and `.claude/agents` copies support **Claude Code** conventions. Do not assume Cowork automatically discovers them. Cowork uses enabled account skills/plugins; its local and cloud skill behavior differs from Claude Code. This repository does not ship a Cowork plugin installer. [Skills and Cowork behavior](https://code.claude.com/docs/en/skills)

When the current host can delegate, it can use the included council role files with a shared evidence packet. Otherwise perform a labelled sequential review. Native custom-agent discovery in Claude Code uses `.claude/agents`; copying those files does not guarantee equivalent Cowork runtime behavior. [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)

## 5. Set up dashboard request pickup

Have Claude read `runtime/install/listener-prompt.md` and [listener.md](listener.md). Use a native scheduler only if its next run can reach the same local folder, tools, and queue. Save the actual scheduler receipt and verify pickup with a harmless **Status** request.

Claude's scheduling UI can create recurring tasks; its documentation says tasks requiring local files or apps run locally. Availability and cadence are controlled by the host. A general cloud schedule is not proof of local folder access. If the available cadence is longer than a request's validity, use manual pickup for that request. [Cowork scheduled tasks](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-claude-cowork)

When no compatible local scheduler is available, keep the generated prompt and type `SMP RUN QUEUE` in the active local session after clicking a dashboard operation. This is the supported manual fallback; the installer cannot make Cowork wake up by writing a file.

## Claude Code alternative

Start Claude Code in the exact clone and let it read `CLAUDE.md`. Register the generated local MCP command, using your actual Python executable:

```sh
claude mcp add --transport stdio social-media-plus -- python3 /absolute/path/to/social-media-plus/scripts/smp-mcp.py --root /absolute/path/to/social-media-plus
claude mcp list
```

Check `/mcp` in the session and complete any host trust prompts. A configured server is not necessarily a connected server. [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)

The same `SMP START`, `SMP WEEK`, and manual `SMP RUN QUEUE` workflow applies. Claude Code scheduling is separate from Cowork scheduling; do not silently substitute a daemon, paid API service, or remote routine for the user's selected host.
