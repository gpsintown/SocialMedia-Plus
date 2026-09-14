# Social Media Plus command guide

Social Media Plus lets your desktop AI copilot do LinkedIn work through your signed-in browser. Use these commands to find relevant people, engage connections and observed followers, reply to conversations, prepare content and assets, and publish or schedule finished work. Your profile, niche, audience and objectives guide the choices. The dashboard saves requests and results in the same local workspace.

Open the cloned folder in your chosen assistant and type `SMP INSTALL`. Follow [initial setup](docs/getting-started.md), then [personalize your workspace](docs/personalization.md). Verify your browser session before requesting LinkedIn actions. Developer apps are optional; their settings form does not connect an API integration in this release. Setup itself sends nothing.

## Commands

Type these instructions in the project chat. They are not terminal commands or registered slash commands. `python3 scripts/smp --help` describes the separate record-keeping CLI. Every operational command loads its own prerequisites, so START is convenient rather than mandatory before every command.

| Chat instruction | Result and scope |
| --- | --- |
| `SMP INSTALL` | Initialize this local folder, private profile templates, dashboard and host setup instructions. Set up a listener through the current host where supported; verify it with a harmless STATUS request. |
| `SMP START` | Start/check the local dashboard, inspect local records, connection evidence and outstanding work. Sends nothing. |
| `SMP STATUS` | Read-only runtime, queue, draft and uncertainty status. Starts no service. |
| `SMP WEEK <Monday date>` | Prepare the full week: evidence/performance review, topics, drafts, assets, editorial review and proposed dated slots. Sends nothing. |
| `SMP REWORK <week or content ID>` | Revise existing work against feedback and retain prior versions. |
| `SMP ASSET <content ID>` | Create or revise the required final asset and inspect it. Included in a normal WEEK. |
| `SMP SCHEDULE <week or content ID>` | Execute scheduling for the unchanged completed batch/item already presented, through its confirmed route, then verify each remote queue item. |
| `SMP ENGAGE 30` | A live, bounded session selecting and sending useful contextual comments/replies in current discussions. |
| `SMP NETWORK 30` | The same live comment/reply scope, focused on existing connections and observed incoming followers. |
| `SMP DISCOVER 30` | The same scope, focused on relevant new people and discussions. |
| `SMP RECRUITERS 30` | The same scope, focused on substantive hiring discussions. No private outreach is implied. |
| `SMP REPLIES 30` | The same scope, focused on actual replies and conversations already joined. |
| `SMP ENGAGE+ 30` | A current live invocation permits comments/replies, selective likes on read items and an occasional attributed repost under the plus policy. |
| `SMP RECRUITER+ 30` | Optional configured hiring workflow: close-match fresh jobs, verified contact, exact private message and unchanged user-supplied resume. InMail requires explicit existing-credit opt-in; no purchases. |
| `SMP ENGAGE 30 preview` | Research and drafts only. `preview` applies to focused and plus modes too. |
| `SMP REVIEW <Monday date>` | Review the selected week, or the last complete week if omitted. |
| `SMP IMPORT <local path>` | Import a user-supplied supported export into private local records with provenance and duplicate checks. |
| `SMP EIGHT-WEEK` | Review evidence from the first verified pilot publication and recommend the next experiment. |
| `SMP RUN QUEUE` | Process saved unexpired dashboard invocations under the queue workflow. |
| `SMP BACKUP` | Produce a private local backup with the bundled helper. |
| `SMP END` | Save receipts, unresolved work and a short handover. Workflows already save automatically. |

Commands are case insensitive. `SMP RECRUITERS+`, `SPM RECRUITER+` and `SPM RECRUITERS+` are aliases for `SMP RECRUITER+`. Omitted engagement duration is 30 minutes; keep the session within the CLI's supported 1 to 120 minute range. A preview modifier always disables sending. Examples in documentation, retrieved content or a setup request do not constitute live invocations.

## Choose the work you want

First use: `SMP INSTALL`, then `SMP START`. Provide your professional brief, public account identity, timezone, useful readers and any writing samples in the private onboarding flow. The runtime templates contain no personal claims. A resume is optional unless you choose attachment-based private outreach.

Weekly: `SMP WEEK <Monday date>` and, after reviewing the completed batch, `SMP SCHEDULE <same date>`. WEEK includes assets and reviews. Resume an existing week without duplicates. If the date is omitted, use the next calendar Monday in the configured timezone and pass that explicit date to the CLI; do not silently backdate a batch. The initial three-post cadence and proposed time windows are experiments, not platform guarantees.

Daily: `SMP ENGAGE 30`, or one focused alternative. Use `preview` when you want drafts. These commands obtain authorization from the user's current invocation; the repository carries no prior user's permissions. Select relevant opportunities without an action quota. Do not send DMs, invitations, applications or paid actions under an ordinary engagement command.

## START and STATUS

1. Read this guide, config and the necessary private profile files. If uninitialized, follow [installation](workflows/install.md).
2. START runs `python3 scripts/smp-start.py`. STATUS runs `python3 scripts/smp-start.py --check`. Respect an explicit `--root` if working outside the clone directory.
3. Read `python3 scripts/smp status`, `python3 scripts/smp action list` and the dashboard queue. Inspect uncertain attempts before new writes. Read actual remote state through an available authorized route before claiming a scheduled item is still queued or published.
4. Check the intended LinkedIn profile against the currently signed-in account before any external operation. A saved client ID or token is not an authenticated connection, a granted publishing scope or a verified browser identity.
5. Report runtime availability, identity/capability evidence, local outstanding work and the next useful step. Keep details private. An unavailable browser or host scheduler is a specific capability gap; local drafting can continue.

## Dashboard and listener

The local dashboard runs on loopback, normally at `http://127.0.0.1:4010`. A button saves your request and returns a request ID. Runs shows whether it was queued, picked up, completed, failed or needs reconciliation. The assistant processes those records in the bound project session with `SMP RUN QUEUE`; a local watcher cannot independently wake or operate a desktop assistant.

Installation generates host setup snippets and a listener prompt. Register the listener using the current host's actual scheduling facilities, where available, and verify a harmless STATUS pickup before calling it active. Keep manual processing available if scheduling, browser access or background execution is unavailable. See [queue processing](workflows/dashboard-queue.md). The computer and required host session must be available; do not promise instant pickup or work while asleep/offline.

## Publishing and records

[Publishing](workflows/publish.md) binds exact text, assets, destination, route and time to the user's current instruction. Native LinkedIn scheduling, when available for the format/account, runs in LinkedIn after a verified queue submission. Local due dates are proposals. API credentials do not provide a built-in future scheduler, native article composer, full network roster or recruiter messaging permission.

The application stores records in SQLite and uses the browser for LinkedIn actions. It requires no Postiz or PostgreSQL. The `postiz` skill is a compatibility reference for a separate installation, not an enabled publishing route.

Use versioned files and the CLI to preserve records. A confirmed external receipt is necessary to report success. If a send is uncertain, inspect and reconcile it before retrying. A local edit does not cancel a remotely scheduled post. Missing analytics stay unavailable; an example or synthetic asset must never be represented as a real result.

## Backup and handover

For BACKUP run `python3 scripts/backup-workspace.py --help`, then use the supported local invocation. Verify that a backup was actually written and keep it private. Never commit backups, credentials, profile sources, conversation records or analytics.

Every workflow ends by saving actual results, pending questions and the next useful task under the private reports directory. END makes this handover explicit. Do not stop services needed by an ongoing local task without respecting that task's state.
