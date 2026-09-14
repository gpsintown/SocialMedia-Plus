# Contributing

Use Python 3.11 or newer. The Python runtime needs no third-party package.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/release-check.py
```

Tests must use temporary workspace roots. Never run fixtures, sample posts or
test contacts against your daily workspace database. Any changed queue behavior
needs tests for duplicate requests, expiry and uncertain execution.

The dashboard ships a production build. To change it, use Node.js 22.12 or newer:

```sh
cd ui
npm ci --ignore-scripts
npm run build
```

Commit both source and rebuilt `ui/dist`. Keep package lockfiles. Runtime user
data and host-specific configuration must stay out of commits. Run the release
scanner after rebuilding; don't add real account data as test fixtures.

Document host capability differences honestly. A saved prompt or local queue
file is not a running scheduled listener. No feature may add an independent LLM
API dependency without changing the documented product contract.
