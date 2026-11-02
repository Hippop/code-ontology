# GitHub CI

CI runs on pull requests, pushes to `main`, and manual dispatches. The workflow is
`.github/workflows/ci.yml`. Changes to documentation run the same checks, so the
required status check cannot be left pending by a path filter.

| Check | Environment | Verification |
| --- | --- | --- |
| Backend | Ubuntu 24.04, Python 3.11 and 3.12; Windows 2022, Python 3.12 | Install from `uv.lock`; run all existing unittest regressions |
| Web build | Ubuntu 24.04, Node.js 24 | `npm ci`, TypeScript checks and Vite production build |
| Website checks | Ubuntu 24.04, Python 3.12, Node.js 24 | Static website links/content and JavaScript syntax |
| CI required | Ubuntu 24.04 | Fail unless all three groups succeed, including every backend matrix job |

## Reproduce locally

Run from the repository root with uv 0.12.10:

```bash
uv sync --locked
uv run --locked python scripts/run_ci_tests.py
uv run --no-project --python 3.12 python scripts/check_website.py
node --check website/app.js
```

Run from `web/` with Node.js 24:

```bash
npm ci
npm run build
```

The test runner rejects empty discovery and unhandled background thread
exceptions, in addition to ordinary test failures. Individual modules can be run
with `--pattern test_development_codegen.py`. It does not update expected graph
snapshots. Graph changes need a reviewed baseline update.

The existing tests include simulated Agent/Codex responses and a test Maven
wrapper. Successful CI does not establish real model execution, real Java
compilation, browser interaction or production readiness.

## Permissions and maintenance

- Jobs have `contents: read`, checkout does not persist credentials, and no model
  API credentials are required. External contributions use `pull_request`.
- Actions are pinned to verified release commit SHAs. uv is fixed to 0.12.10;
  application dependencies follow the committed lock files.
- Backend jobs time out after 20 minutes. Failed test logs are uploaded for seven
  days; GitHub job logs also retain setup and installation failures.
- New commits cancel older CI runs for the same PR. Main branch runs are not
  automatically cancelled.
- Configure `CI required` as the required status check after observing a complete
  successful run. Require PRs but allow zero approving reviews for a solo
  maintainer; disallow force pushes and branch deletion.
- CI does not publish packages, push `gh-pages` or deploy the application. The
  existing Pages publishing process remains separate.
