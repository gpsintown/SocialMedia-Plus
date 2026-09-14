# 🚀 Initial setup

Set up Social Media Plus so your desktop AI can run LinkedIn workflows from your local folder. You will start the dashboard, connect the local tools, add your profile and verify browser access. The copilot uses that context to find relevant discussions, write content and carry out the actions you request. No separate LLM API key, PostgreSQL or Docker is required.

## 1. Check the requirements

Install Python **3.11+**, Git (or GitHub Desktop), and a desktop agent that can access your local folder and run commands. Read [prerequisites](prerequisites.md) for supported host capabilities and platform limits. The built dashboard is included; Node is only needed for UI development.

Choose the appropriate instructions: [Codex setup](codex-setup.md) or [Claude Desktop / Cowork setup](claude-setup.md). Capabilities differ by host, account and session. GitHub Desktop manages the repository; it does not run the AI workflows.

## 2. Clone and open the folder

```sh
git clone https://github.com/gpsintown/SocialMedia-Plus.git
cd SocialMedia-Plus
```

Choose a permanent local location. Open this same folder in your desktop agent, or grant Cowork access to it. All sessions should use this folder so they share the same records.

## 3. Install through your project chat

```text
Read AGENTS.md and SOCIAL_MEDIA_PLUS.md in this folder. SMP INSTALL
```

If your host does not automatically read project instructions, attach or explicitly reference those files. Installation initializes private configuration and profile files, starts the dashboard, and prepares the host's MCP/skill setup. Follow any host-specific registration or restart steps it reports.

For terminal initialization instead:

```sh
python3 scripts/smp-install.py --root . --host codex
python3 scripts/smp-start.py --root .
```

Use `--host claude` for Claude. Terminal initialization cannot create a desktop scheduled task by itself; complete the [host setup](codex-setup.md) or [Claude setup](claude-setup.md) and listener step below.

## 4. Verify dashboard request pickup

Open [the local dashboard](http://127.0.0.1:4010). The installation chat attempts to configure a scheduled listener when the host supports it. Verify that a harmless STATUS request is actually picked up and completed, following [listener setup](listener.md).

If scheduled pickup is unavailable, send `SMP RUN QUEUE` in the project chat. A queued request means it is waiting, not that an action has happened. Local scheduling requires the computer and necessary desktop app to remain available.

## 5. Personalize your workspace

Follow [personalization](personalization.md) to set your objectives, audience, evidence, writing style, privacy boundaries and cadence. Start with a short brief and a few samples of your own writing. A résumé is optional unless you choose a workflow that needs one.

## 6. Verify your LinkedIn browser session

Open LinkedIn in your own signed-in Chrome session. Ask the copilot to use its supported browser tool to verify the account without sending anything. A successful check means it can reach the intended profile; it does not grant permission to publish or contact people.

You can skip developer configuration for browser work. To prepare future API settings, open **LinkedIn setup** in the dashboard and follow the [two-app LinkedIn developer guide](linkedin-setup.md). It explains products, permissions and restricted-access requirements. Saving credentials writes ignored `.env.local`; it does **not** complete OAuth or connect an API publishing adapter in this release. Developer credentials are not required for browser-based drafting and engagement.

## 7. Start with a preview

```text
SMP START
SMP ENGAGE 30 preview
```

Preview lets you check whether the selected discussions and proposed replies fit your objectives. It sends no comments. For weekly content, use `SMP WEEK <Monday date>`, review the finished batch, then use `SMP SCHEDULE <the same Monday date>` when you want to authorize that exact batch.

Read the [full command guide](../SOCIAL_MEDIA_PLUS.md) and [command map](../config/chat-commands.json). A live engagement command authorizes its documented session actions; installing the project does not grant standing publishing or outreach permission.

## Returning later

Open the same folder and send `SMP START`. If necessary, restart the dashboard with `python3 scripts/smp-start.py --root .`. Check Runs and listener status before retrying a request whose outcome is uncertain.

Keep private files out of Git. See [security](../SECURITY.md) and the README's [sharing instructions](../README.md#-privacy-and-sharing).
