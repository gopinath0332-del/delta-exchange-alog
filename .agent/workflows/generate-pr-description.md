---
description: Analyse commits in the current branch and generate a pull request description in document.md
---

# Generate PR Description from Branch Commits

This workflow reads commits from the **current branch** (compared to `master` / `main`), inspects the changed files and diffs, then writes a professional pull request description to `document.md` in the project root.

## Steps

1. **Detect the current branch and base branch**

   Run the following to find the current branch and figure out the divergence point:

   ```bash
   git branch --show-current
   ```

   Then find commits ahead of master:

   ```bash
   git log master..HEAD --oneline
   # If master doesn't exist try:
   git log origin/master..HEAD --oneline
   # Or use main:
   git log main..HEAD --oneline
   ```

// turbo 2. **Fetch full commit details (message + diff stat)**

```bash
git log master..HEAD --pretty=format:"### Commit: %h%n**Author:** %an%n**Date:** %ad%n**Message:** %s%n%b" --date=short --stat
```

// turbo 3. **Fetch the full unified diff of all changes in the branch**

```bash
git diff master...HEAD
```

4. **Analyze the commits and diffs**

   Using the output from steps 2 and 3, the agent should:
   - Identify what features/fixes/refactors were made
   - Group related changes together
   - Note which files were modified and why
   - Identify any breaking changes or config changes

5. **Write `document.md` with the PR description**

   Create or overwrite `document.md` in the project root with the following structure:

   ```markdown
   ## Pull Request: <concise title based on branch name and commits>

   ### Summary

   <2–3 sentence overview of what this PR does and why>

   ### Changes Made

   <Grouped bullet points by feature/area, e.g.:>

   - **Strategy Logic**: ...
   - **Configuration**: ...
   - **Dashboard / UI**: ...
   - **Documentation**: ...

   ### Files Changed

   <Table of key files and what changed in each>

   | File                              | Change |
   | --------------------------------- | ------ |
   | `strategies/donchian_strategy.py` | ...    |

   ### Testing Done

   - [ ] Strategy ran successfully in live mode
   - [ ] Dashboard shows correct values
   - [ ] No regressions observed

   ### Notes / Breaking Changes

   <Any config changes, renamed parameters, or things reviewers should be aware of>
   ```

   Save this to `document.md` in the project root.

6. **Confirm output**

   Report back to the user:
   - Path to the generated `document.md`
   - Number of commits analysed
   - Brief summary of what was included
