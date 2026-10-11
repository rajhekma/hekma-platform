# GitHub / GitLab setup — Day 1

## 1. Create an organization (one-time)

### GitHub

The organization already exists: **[HekmaAI](https://github.com/HekmaAI/)**.

All microservice repos go under this org. Make sure your GitHub user has **Write** access to it.

### GitLab

1. **Groups → New group**
2. Name: `hekma-health`
3. Visibility: **Private**

## 2. Create the `hekma-platform` remote repo

This folder is already initialized as a git repo locally. Push it after creating the empty remote.

### GitHub (web)

1. Go to [https://github.com/organizations/HekmaAI/repositories/new](https://github.com/organizations/HekmaAI/repositories/new)
2. **Owner:** `HekmaAI`
3. **Name:** `hekma-platform`
4. **Private**
5. Leave README / `.gitignore` / license **unchecked** — the local repo already has them
6. **Create repository**, then push:

```bash
cd "/Users/pts_mac_air_m4/Documents/Hekma Projects/hekma-platform"
git push -u origin main
```

The remote is already set to `git@github.com:HekmaAI/hekma-platform.git`.

### Troubleshooting: `ERROR: Repository not found`

| Cause | Fix |
|-------|-----|
| Repo not created on GitHub yet | Create it in the [HekmaAI org](https://github.com/organizations/HekmaAI/repositories/new) first — git never creates remote repos |
| No write access to `HekmaAI` | Ask an org owner to add you as a **Member** with write permission |
| Wrong remote | `git remote set-url origin git@github.com:HekmaAI/hekma-platform.git` |
| HTTPS vs SSH mismatch | Prefer SSH if `ssh -T git@github.com` works |

### GitHub CLI (optional)

```bash
brew install gh
gh auth login
gh repo create HekmaAI/hekma-platform --private --source=. --remote=origin --push
```

### Cursor-hosted (alternative)

If you use Cursor repos instead of GitHub, follow the **new-repo** / **origin** CLI flow from Cursor docs.

## 3. Repo naming for upcoming services

Create repos **when you extract** each service (not all on day 1):

- `hekma-scanner` (MS-11 + MS-13 — extracted in this repo)
- `hekma-support-center` (MS-05)
- `hekma-medication` (MS-12)
- … see [MICROSERVICE_ARCHITECTURE.md](./MICROSERVICE_ARCHITECTURE.md)

## 4. Branch protection (recommended)

On `main` for each service repo:

- Require pull request reviews
- Require status checks (CI) before merge
- No force-push to `main`
