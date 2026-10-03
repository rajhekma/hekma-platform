# GitHub / GitLab setup — Day 1

## 1. Create an organization (one-time)

### GitHub

1. Go to [https://github.com/organizations/plan](https://github.com/organizations/plan)
2. Choose **Free** plan (fine for private repos)
3. Suggested org name: `hekma-health` or `hekma-ai`
4. Add your team as **Owners** or **Members**

### GitLab

1. **Groups → New group**
2. Name: `hekma-health`
3. Visibility: **Private**

## 2. Create the `hekma-platform` remote repo

This folder is already initialized as a git repo locally. Push it after creating the empty remote.

### GitHub (web)

1. Org → **New repository**
2. Name: `hekma-platform`
3. Private, **no** README (we already have one)
4. Then:

```bash
cd "/Users/pts_mac_air_m4/Documents/Hekma Projects/hekma-platform"
git remote add origin git@github.com:YOUR_ORG/hekma-platform.git
git push -u origin main
```

### GitHub CLI (optional)

```bash
brew install gh
gh auth login
gh org create hekma-health --description "Hekma microservices"
gh repo create hekma-health/hekma-platform --private --source=. --remote=origin --push
```

### Cursor-hosted (alternative)

If you use Cursor repos instead of GitHub, follow the **new-repo** / **origin** CLI flow from Cursor docs.

## 3. Repo naming for upcoming services

Create repos **when you extract** each service (not all on day 1):

- `hekma-clinical-scanner` (MS-11 — next)
- `hekma-support-center` (MS-05)
- `hekma-medication` (MS-12)
- … see [MICROSERVICE_ARCHITECTURE.md](./MICROSERVICE_ARCHITECTURE.md)

## 4. Branch protection (recommended)

On `main` for each service repo:

- Require pull request reviews
- Require status checks (CI) before merge
- No force-push to `main`
