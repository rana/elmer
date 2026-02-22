Draft a commit message from the current changes, then stage, commit, and sync with the remote. This combines `/commit-message` and `/commit-sync` into a single workflow.

## Steps

1. Run `git status` (never use `-uall`) to see untracked and modified files. If there are no changes, inform the user and stop.
2. Run `git diff` to see unstaged changes, and `git diff --cached` to see staged changes.
3. Run `git log --oneline -10` to see recent commit message style.
4. Do NOT commit files that likely contain secrets (`.env`, `credentials.json`, etc.). Warn the user if any are present.
5. Analyze all changes and draft a concise commit message:
   - Summarize the nature of the changes (new feature, enhancement, bug fix, refactor, docs, test, etc.).
   - Use the imperative mood (e.g., "Add", "Fix", "Update", "Remove").
   - Keep the subject line under 72 characters.
   - Add a body with bullet points if the changes span multiple concerns.
   - Match the style and conventions visible in recent commits.
6. Stage all relevant changed files by name (prefer explicit file names over `git add -A`). Use `git add -A` only if the number of changed files makes individual staging impractical (more than ~15 files).
7. Commit using a HEREDOC for the message to preserve formatting:
   ```
   git commit -m "$(cat <<'EOF'
   <message>

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```
8. If the commit fails due to a pre-commit hook, fix the issue, re-stage, and create a NEW commit (never amend).
9. Run `git push` to sync with the remote. If the current branch has no upstream, use `git push -u origin <branch>`.
10. Run `git status` to confirm clean working tree and show the result to the user.
