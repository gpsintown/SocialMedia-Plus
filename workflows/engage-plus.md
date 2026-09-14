# ENGAGE+ selective engagement

Read [daily](daily.md), the current private plus policy and the same context/voice/claims. A current explicit `SMP ENGAGE+` invocation adds selective likes on read posts/comments and occasional attributed reposts to comment/reply scope. Preview performs research and drafts only. No private outreach, paid credits, invitations, applications, follows or bulk attention loops are included.

Record the actual invocation using `python3 scripts/smp session start --mode engage_plus --minutes 30 --authorization '<actual current invocation reference>'`, substituting the requested duration and evidence. Use `--preview` for a preview. Never reuse expired session authorization or manufacture another session to continue after the deadline.

Read the particular item and relevant thread. A like needs a specific reason to agree and a check for an existing reaction. A repost needs a useful original perspective and preserved native attribution; use the configured session/rolling limits. Groups are based on observed work, relationship history and discussion relevance. Preserve stable IDs, existing topic notes and cooldowns.

Use `action prepare --kind reaction` with the active `--session`, exact target/context and `--details-file` containing `{"reaction":"like"}`. For a repost use `--kind repost`, exact response text, attribution context and details. Public comments/replies follow the daily ledger. Run `action check` immediately before each one-time submission. Verify the visible result and record a supported receipt; uncertain attempts stay reserved until reconciled.

Save a private report with selection reasons, actual reactions/reposts/comments, receipt IDs and remaining uncertainty. Record only observed responses or conversations; never promise reach, profile attention or reciprocity. End the local session with `session end ID` after preserving all results.
