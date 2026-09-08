#!/usr/bin/env bash
set -euo pipefail

# Publish committed marketing assets only; never force push or include worktree data.
cd "$(git rev-parse --show-toplevel)"
if [[ "$(git remote get-url origin)" != "https://github.com/Hippop/code-ontology.git" ]]; then
  echo "Refusing to publish: origin is not the expected Code Ontology repository." >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Publish from main after reviewing and committing website changes." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain -- website)" ]]; then
  echo "Commit website changes before publishing; uncommitted assets are not published." >&2
  exit 1
fi
python3 scripts/check_website.py
node --check website/app.js
site_revision=$(git subtree split --prefix=website HEAD)
git push origin HEAD:refs/heads/main
git push origin "$site_revision:refs/heads/gh-pages"
echo "Published committed website assets. Check the Pages build before announcing the URL."
