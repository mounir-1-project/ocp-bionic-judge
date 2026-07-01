#!/bin/bash
# Run this script from the ocp-bionic-judge directory to initialize the git repo.
# It respects .gitignore — .env, venv/, *.db, mlruns/ etc. are NOT committed.
set -e

git init
git config user.email "mounir.sanbouli.43@edu.uiz.ac.ma"
git config user.name "mkj"
git branch -m main

# Safety: untrack venv/ if it was accidentally staged
git rm -r --cached venv/ 2>/dev/null || true

# Add all tracked files (respects .gitignore)
git add -A

# Verify .env is NOT staged
if git diff --cached --name-only | grep -q "^\.env$"; then
    echo "ERROR: .env is about to be committed. Aborting."
    echo "Make sure .env is listed in .gitignore and run: git rm --cached .env"
    exit 1
fi

git commit -m "feat: initial project structure — OCP Bionic Judge Agent v1.0"
echo "✓ Git repository initialized with first commit."
echo "  Remember: never commit .env or venv/ — they stay local only."
