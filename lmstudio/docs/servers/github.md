# github (official MCP)

**MCP server:** `github`  
**Package:** `@modelcontextprotocol/server-github`  
**Auth:** `GITHUB_PERSONAL_ACCESS_TOKEN`

Full GitHub API — repos, branches, files, issues, PRs, code search, Actions, gists.

---

## vs github-watch

| github | github-watch |
|---|---|
| Create/update issues & PRs | Watch + poll for changes |
| Code search, file contents | CI/review/merge deltas |
| Write operations | Read + diff awareness |

---

## When to use

| Task | Server |
|---|---|
| “Open an issue for this bug” | github |
| “What's the status of PR #12?” one-shot | github or github-watch `gh_pr_status` |
| “Tell me when CI passes on PR #12” | github-watch `gh_watch` + `gh_poll` |

---

## Typical flow

```
github: search_code / get_file_contents → understand remote repo
coding-tools: local changes
github: create_pull_request
github-watch: gh_watch PR → gh_poll until merged
```
