# Install in a local assistant workspace

This workflow is invoked by `SMP INSTALL`. Read the repository README for prerequisites and the current host setup documents. Use the clone folder selected by the user. Resolve its absolute path before running commands; keep the application and its private records together. Do not initialize the original author's workspace or copy any existing private data.

## Local setup

1. Confirm Python and a supported local execution environment. The assistant needs permission to read/write the clone folder. A cloud-only session without that folder cannot start its host's desktop application or local listener.
2. Read `python3 scripts/smp-install.py --help`. From the clone run `python3 scripts/smp-install.py --root . --host codex` or use `--host claude` for a Claude host. Use `--thread-id` only with an actual observed host session identifier. Do not invent an ID or copy one from a tutorial.
3. The installer initializes private local SQLite state, copies missing defaults from `templates/config/` to ignored `config/`, copies missing `templates/profile/` to ignored `profile/`, and generates registration snippets under ignored `runtime/install/`. It must not overwrite existing user files. `.env.local` contains actual local settings; only the placeholder `.env.example` belongs in Git.
4. Run `python3 scripts/smp-start.py --root .` using the same root as the installer. Open the local dashboard returned by startup, normally `http://127.0.0.1:4010`. For browser work, verify access to the intended signed-in LinkedIn account through the host's available browser tools without sending anything. Configure developer-app values only if the user chooses optional future API setup, following the LinkedIn setup guide. Browser workflows do not require those credentials. Never paste tokens into a public issue, chat log or committed file. Saving environment variables is not an OAuth grant or successful publishing test.
5. Follow [profile onboarding](profile.md). Ask for the small professional brief needed for the selected task, intended public account and IANA timezone. Keep actual values in ignored configuration/profile files. Do not require a resume for ordinary drafting.

## Host connection and listener

Use the current host's actual tool/settings interface. The generated `runtime/install/codex-mcp.toml` and `runtime/install/claude-mcp.json` are examples for registration, not evidence that the host loaded the server. Review paths and merge the relevant block without overwriting unrelated server settings. Confirm the local MCP server's read-only queue/status tools are exposed. A missing MCP picker entry can fall back to the CLI for local records.

Read the generated `runtime/install/listener-prompt.md` and [queue workflow](dashboard-queue.md). A current `SMP INSTALL` invocation requests scheduled pickup as part of setup. Configure that scope through the host's native scheduling feature when available; an explicit request for manual mode overrides this default. Bind it to this exact local workspace/session. Keep notifications quiet while unchanged; report meaningful completion, failure or required user action. Do not put secrets in the saved scheduling prompt. Scheduled pickup processes only later saved user invocations; installing it does not create permission to send social content.

Codex and Claude capabilities differ by product, version, plan and session. Project files do not automatically grant filesystem, browser or background execution capabilities. Claude Code project skill/agent conventions do not imply Cowork auto-discovery. In Cowork, explicitly read the shared folder's `CLAUDE.md` and workflow when necessary; use only installation mechanisms the current host actually supports. GitHub Desktop can clone this folder but does not run assistant actions.

Verify the listener with one harmless dashboard STATUS request: record its request ID, observe pickup in the selected host/session, inspect the completed private report and queue receipt. Set the local listener verification status only from that observed result. A local queue file changing, registration snippet existing, scheduled-task creation response or MCP ping alone does not prove pickup. If the host cannot register or execute a schedule, report manual mode honestly; `SMP RUN QUEUE` in an active local session remains usable. Do not invent a cron/CLI bridge that invokes an unavailable host.

## Finish

Run `python3 scripts/smp-start.py --check` and `python3 scripts/smp doctor`. Report which pieces are verified: local runtime, configured identity, exposed MCP tools, browser capability and listener pickup. Separate configured from authenticated and verified. The setup ends with an operational local dashboard and concrete instructions for any account/host steps that genuinely require the user.
