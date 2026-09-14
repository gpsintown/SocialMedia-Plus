---
name: postiz
description: "Explain the optional external Postiz compatibility boundary; this portable distribution does not install or depend on Postiz."
metadata:
  version: "1.0.0"
  project: "social-media-plus"
---

# Optional Postiz compatibility reference

The runnable package uses local SQLite and the user's selected desktop assistant. It contains no Postiz source, database stack, Docker service, scheduler transport or credentials. PostgreSQL is not required. This entry preserves a discoverable skill name for users asking about their own separately installed scheduler; it is not an active integration.

If the user asks about using an external Postiz installation, explain the need to verify that separate project's current requirements, license, authentication, supported formats and available MCP/API capabilities. No Postiz publishing command in an older example should be run against this package. The `postiz` authority value retained in the record schema is compatibility metadata, not an installed writer.

Do not silently install a scheduler, transfer native LinkedIn items, copy credentials or add a second queue. An eventual integration would need its own selected transport, explicit current user instruction for exact content and verified external receipts. Local scheduling workers would also need a reliable running machine at delivery time.

Continue the current task through this package's available native/manual route. See [publishing](../../../workflows/publish.md) for exact approval and uncertainty rules. No Postiz upstream code, prompt text or AGPL payload is redistributed here.
