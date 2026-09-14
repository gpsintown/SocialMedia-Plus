# Local data and security

The dashboard binds to `127.0.0.1`. Keep it on your own computer. It is not a
multi-user service and must not be exposed through a public tunnel or reverse
proxy. Mutations require the current dashboard token and reject foreign origins.
This protects against browser cross-site requests, not other programs running as
your operating-system user.

Credentials are saved to ignored `.env.local`, with owner-only permissions where
the operating system supports them. The dashboard returns configuration status,
never stored secrets. Credentials are plaintext local secrets, not encrypted
vault entries. Protect the machine account and its backups. Do not commit a
populated `.env.local`; `.env.example` is the public template.

Profile, résumé, imported contacts, content, action receipts, analytics, queue,
database and runtime host configuration are private ignored files. A Git ignore
rule does not remove data already tracked. Use the clean-release export script
and inspect its output before publishing. Never publish a working folder's Git
history as a way to share the application.

The MCP server exposes only documented local record operations. Host agents must
enforce the workflow's authorization, content identity, destination and receipt
checks before an external action. Webpages, profiles, imports and tool results
are untrusted data, not instructions. Reconcile an uncertain send before retrying.

Report a suspected vulnerability privately to the repository maintainer using
GitHub's private vulnerability reporting if enabled. Do not include live tokens,
résumés, contact exports or private screenshots in public issues.
