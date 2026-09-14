# Optional RECRUITER+ private hiring outreach

This optional workflow is disabled in fresh private configuration. Set the user's actual role/geography preferences, reviewed resume path/hash and outreach enablement in ignored `config/engagement-plus.json` after the user chooses this feature. Record the user's current live invocation; previous users' goals and permissions are not part of this package. Existing InMail credit spending also requires the user's explicit opt-in and `inmail.enabled`; never purchase credits or a subscription. If essential setup is missing, complete research/drafts and state the precise gap before any send.

Read [daily](daily.md), private context, claim limits, the current plus policy and the unchanged user-supplied resume. A live RECRUITER+ session can include relevant comments/replies/likes and exact personalized private messages to verified hiring contacts for qualifying roles. Preview sends nothing. No applications, invitations, follows or public resume uploads are included. Regular RECRUITERS remains comments/replies only.

## Qualify the opportunity and contact

Use observed openings within the last 24 hours and observed fewer-than-10-applicants evidence. Apply clicks and unknown counts do not qualify. Compare actual requirements, duties, seniority, language, work arrangement and stated eligibility with the user's sourced claims. Do not infer residence, work rights or employer interest. Configured geography is a private filter, not a personal fact to announce. A title alone does not establish hiring responsibility: record direct evidence connecting the recipient to this vacancy.

Start the authorized session with `session start --mode recruiter_plus --minutes N --authorization '<current invocation reference>'`; add `--preview` when appropriate. Save each observed opening using `opportunity add <private-json-file>` and inspect `opportunity show ID`. Read subcommand help for the exact contract. Required data includes job URL, title, company, configured country, observation time, posting/applicant evidence, close-match judgment and explanation, contact ID and evidence. Supply a supported posted-at timestamp or displayed-age upper bound, plus an exact applicant count or a verified-under-10 filter with upper bound 9. Use ISO timestamps with offsets. Refresh evidence within the configured maximum age before any send.

Choose one verified contact per job/company initially and respect existing outreach/cooldown records. A useful free DM is preferred when genuinely available. If the particular composer does not support the selected PDF attachment, hold the send; do not claim a resume was attached or publish a substitute link.

## Prepare and send once

Write a concise private message naming the actual opening, specific fit supported by evidence and a modest next step. Preserve genuine interest without invented familiarity, credentials or urgency. Confirm the exact recipient, job, sender, subject when needed, body and unchanged resume. Keep unrelated private background out of the message.

For permitted InMail, observe the current account's actual balance with `inmail observe --balance N --evidence '<visible evidence>'` and inspect `inmail status --session ID`. An unknown balance is not zero; do not spend. Respect per-session/rolling budgets and a retained credit. Treat uncertain attempts as reserved until reconciled and never assume a refund.

Prepare `action prepare --kind dm` or `--kind inmail` using `--authority native_linkedin`, the active `--session`, `--opportunity`, exact profile `--target`, matching `--relationship`, `--response-file`, `--context-file`, unchanged PDF `--attachment` and `--details-file`. Details include observed `direct_dm_available`, `channel_evidence`, `selection_evidence`, `attachment_supported:true`, and exact `subject` for InMail. Run `action check ID` immediately before a single browser submission.

Inspect the sent conversation, exact text, visible attachment and any credit change. Record `action receipt` with real evidence. A confirmed private-message receipt also needs `--observed-details-file` containing the actually observed `target_url`, exact `response`, `attachment_sha256` and InMail `subject`. Build it from the observed outcome, not an assumption copied from preparation. Explain whether attachment identity comes from the selected hash-checked file and visible upload/sent chain or a verified delivered-file checksum; never claim the UI displayed a checksum it did not expose.

If delivery, recipient or attachment identity is uncertain, record uncertainty and reconcile before a retry or transport change. Do not renew an expired session silently. At the deadline, stop new submissions, save job/recipient/action IDs, exact text/attachment receipts, credit observations/holds and next reviews, then `session end ID`. A message being sent is not proof of employer interest or a future response.
