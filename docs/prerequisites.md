# Prerequisites

Social Media Plus is a local folder application operated by your selected desktop assistant. It keeps the dashboard, drafts, records, and workflow instructions in one clone. LinkedIn is the active platform; other platform cards describe future integrations.

## Required

| Component | Purpose |
| --- | --- |
| A local clone or extracted release folder | The same folder must be available to the dashboard, CLI, MCP server, and assistant. |
| Python 3.11 or newer with SQLite support | Runs the local CLI, dashboard, installer, and MCP server. |
| Codex / ChatGPT desktop with local agent tools, or Claude Desktop with a capable local workflow | Runs the skills and reads/writes the local workspace. See the host-specific guides. |
| A supported browser tool and your own signed-in Chrome session | Required when you explicitly choose authorized LinkedIn browser actions. |
| Internet access and the host's applicable account entitlement | The selected assistant supplies model reasoning and any connected research/browser tools. |

No PostgreSQL, Postiz, Redis, Docker, or separate LLM API key is needed for the core package. SQLite is embedded in Python; there is no database server to install.

## Optional

- Git or GitHub Desktop for cloning and updating. An extracted ZIP also works. GitHub Desktop is a Git client, not the assistant that executes social workflows. [GitHub Desktop documentation](https://docs.github.com/en/desktop/overview/about-github-desktop)
- Node.js and npm only for rebuilding the dashboard source in `ui/`; the release includes its built UI.
- Your own LinkedIn developer applications if you want to prepare API credentials. Their settings can be saved, but this release has no OAuth or API-publishing adapter. Follow [LinkedIn setup](linkedin-setup.md).
- Your own profile, resume, post history, and analytics exports when relevant. Start with the provided blank templates; none of the original operator's material is included.
- Additional host tools for producing PDFs, images, or other assets. The assistant should check available capabilities and use the documented fallback when a tool is missing.

## Check the machine before setup

From a terminal in the release folder:

```sh
python3 --version
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
python3 scripts/smp --help
```

On Windows, use the Python launcher available on your system, such as `py -3`, in place of `python3`. Run the commands on the machine that owns the clone. A shell inside a cloud container or Cowork VM may have different files, Python paths, and loopback networking; successfully starting a server there does not prove your desktop browser can reach it.

## Choose a host

- [Codex / ChatGPT desktop setup](codex-setup.md)
- [Claude Desktop / Cowork setup, with Claude Code fallback](claude-setup.md)

Neither a GitHub Actions runner nor a cloud-only chat can automatically read your computer's private folder and signed-in Chrome session. Keep those resources local and verify access in the actual session. “Local application” describes this package's storage and runtime; it does not mean your assistant's model runs offline.
