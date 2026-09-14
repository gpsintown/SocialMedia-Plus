# Publish or schedule an exact completed item

Use this workflow for a concrete publish instruction or `SMP SCHEDULE <week or content ID>`. Read the exact `content show` record, final assets, current identity/route, private editorial policy and unresolved actions. The repository contains no standing publication authorization. A SCHEDULE instruction covers only the unchanged finished batch already presented, with its destination, text, assets, route and slots.

## Freeze and authorize

Complete missing reviewable details first. Use `content route ID --authority native_linkedin`, `official_api` or `user_manual` only for the verified available route. Selecting a route records intent; it does not create that integration. Postiz is not part of this distribution's supported execution. A global configuration change does not move existing items. A route change or material revision invalidates prior fingerprints and cannot silently override an active remote schedule.

Record the actual instruction using `content approve ID --by '<actual authorizing user>' --evidence '<actual instruction reference>'` after content, assets and slots are final. Read `content check ID` and action history. If all details are already covered, use that authorization without asking again. If a material decision remains, complete the rest of the artifact and request only the concrete missing instruction.

Prepare a local action with `action prepare --kind schedule` or `--kind publish`, the exact `--content ID` and matching authority. Read the returned record/handoff and run `action check ID`. The CLI stores records only; it does not publish. One item has one active scheduling authority.

## Execute only an available route

For native LinkedIn, reuse the user's currently authorized browser session through exposed host tools. Verify sender, destination, exact text/assets and the current format-specific composer. Inspect the final preview and schedule date/timezone. Feed posts and native articles may have different editors and scheduling support. Do not substitute one format's control or API endpoint for another.

For a separately verified official-API integration, inspect current supported scopes, tool schema and format support. The packaged OAuth/setup checker is not automatically a content publisher or future scheduler. Use the native/manual route where an API writer is absent. A connected app does not authorize unrequested drafts, uploads or posts.

Submit the requested action once, then inspect the actual remote queue item or published content. Verify identity, content/assets and intended time. Record `action receipt ACTION_ID --state confirmed --evidence '<actual observation>' --remote-url '<observed URL>'` or a verified `--remote-id` with matching evidence. A local planned slot, button click, token, HTTP success or opaque tool message is insufficient when the item itself remains unverified. Distinguish scheduled from published.

## Reconcile changes and uncertainty

If a submission is ambiguous, record `action receipt ... --state uncertain` with what actually happened. Inspect the existing remote queue/recent content and use `action reconcile` only after new evidence resolves it. Do not retry through another transport merely because the first errored.

A requested edit/cancellation must address the actual remotely queued version through its active authority. Verify the resulting remote state before revising/reapproving/requeuing locally. A local content edit never cancels an old scheduled item. After delivery time, verify publication with `action publication SCHEDULE_ACTION_ID` and the real published URL/evidence; the passage of time is not a receipt.

Return exact confirmed outcomes, times/timezones and usable URLs or remote queue references. Save remaining uncertainty and the next reconciliation step privately. If the route/tool is unavailable, deliver a complete manual handoff and state that execution remains pending.
