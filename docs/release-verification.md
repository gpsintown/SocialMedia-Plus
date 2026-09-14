# Release verification

Prepared 14 September 2026, version 0.2.0.

- **113 Python tests passed**, including all local HTTP tests, on macOS with
  Python 3.14. The test suite uses temporary roots and synthetic records.
- Dashboard TypeScript validation and the Vite production build passed. The
  compiled UI is included for startup without Node.js.
- Browser inspection confirmed the blank home page, platform cards, LinkedIn
  settings and Runs screen. A harmless STATUS button request was observed in
  SQLite, picked up manually through the CLI and shown as completed in the UI.
- Separate-root installation and that root's own CLI/MCP subprocess startup were
  tested. Reinstallation preserves private configuration and existing listener
  receipts for the same binding.
- Host-switch and schema-migration tests verify that an old request cannot move
  silently between Codex and Claude, including when both use `manual-local`.
- Release scanning checked the public allowlist against common credential
  patterns and a private denylist of original workspace identifiers and known
  configured secrets. No matching values were included in the public files.
- The public file scanner checks required source files and license notices.
  Tests verify that populated private configuration, profiles, credentials,
  databases and host settings are excluded from an export.
- Both host skill directories contain the same 14 skills. Five council role
  definitions are supplied. Local Markdown links resolve.

The privacy denylist, test logs, test database and browser observations are not
distributed. The source ZIP includes a SHA-256 manifest for its public files.

This verification did not create a scheduled task in a recipient's desktop app,
authenticate a LinkedIn developer app or send social content. A scheduled
listener must be registered and verified on each installation. LinkedIn OAuth,
API publishing and restricted analytics adapters remain planned. The included
GitHub Actions matrix has not been run on GitHub as part of local packaging.
