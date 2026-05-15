---
name: workflow_creator
description: Use this skill whenever a new Python service needs a Dockerfile, .dockerignore, or GitHub Actions CI/CD pipeline that builds and pushes to GHCR (GitHub Container Registry). Trigger on phrases like "set up CI", "add a pipeline", "dockerize this service", "push the image to GitHub", "create a workflow for this service", "add CI/CD", or whenever a new Python/UV service is added to the repo and needs automated image publishing. Always use this skill before manually writing any Dockerfile or workflow YAML for a Python service.
---

# Python + UV → GHCR CI/CD

Full pipeline from source to published image. Works for both **server services** (long-running HTTP) and **script services** (one-shot runners).

## Step 0 — Read the service first

Before writing anything, understand what you're packaging:

1. Read `pyproject.toml` — note `name`, `version`, `requires-python`, `dependencies`
2. Read the entrypoint — determine if it's a **server** (binds a port, runs forever) or a **script** (runs and exits)
3. Check test files — scan for **module-level** `os.environ[...]` / `os.getenv(...)` calls (these crash pytest collection when the key is absent in CI)
4. Note the `uv.lock` — must exist; `uv sync --frozen` depends on it

## Step 1 — Dockerfile

Delegate to the `multi-stage-dockerfile` skill. Key constraints for this stack:

- Base: `python:3.13-slim` (or match `.python-version` if present)
- UV installer: pin to a specific version — **never `uv:latest`** (supply chain risk)
  - Find the current version: `uv --version` or check https://github.com/astral-sh/uv/releases
  - Use: `COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv`
- Non-root system user: `groupadd --system <name> && useradd --system --gid <name> --no-create-home <name>`
- Builder syncs deps: `uv sync --frozen --no-dev --no-install-project`
- Runtime copies only `.venv` and `src/`
- Set `PYTHONUNBUFFERED=1` and `PYTHONPATH=/app/src`

**CMD by service type:**

| Type | CMD | EXPOSE | HEALTHCHECK |
|---|---|---|---|
| Server (HTTP) | `["python", "-m", "<module>"]` | Yes (e.g. `8000`) | TCP socket on port |
| Script | `["python", "src/<entrypoint>.py"]` | No | No |

## Step 2 — .dockerignore

Always create this alongside the Dockerfile:

```
.venv/
.env
.pytest_cache/
__pycache__/
*.pyc
*.pyo
dist/
*.egg-info/
```

## Step 3 — GitHub Actions workflow

Load `references/workflow-template.yml` and fill in the blanks. Key decisions:

**Image name pattern:**
```
ghcr.io/<github_owner_lowercase>/<repo_name_lowercase>/<service_name>
```
Derive from: `gh repo view --json owner,name`

**Path triggers** — always include both:
```yaml
paths:
  - "<service-dir>/**"
  - ".github/workflows/<service-name>.yml"
```

**Always add `workflow_dispatch`** — without it you can't manually re-trigger after fixing permissions.

**Permissions:**
- `test` job: `permissions: contents: read` (restrict — default token is too broad)
- `publish` job: `permissions: contents: read` + `packages: write`

**Tags** — always both:
```yaml
tags: |
  ${{ env.IMAGE }}:latest
  ${{ env.IMAGE }}:sha-${{ github.sha }}
```

### Handling env vars in the test job

Python test files often read `os.environ["KEY"]` at **module level** — before any test runs. Pytest imports every file to collect tests, so this crashes collection with `KeyError` even if the test itself doesn't make any API calls.

**How to detect:** Scan test files for top-level (not inside a function or class) `os.environ[...]` or `os.getenv(...)` or `load_dotenv()` followed by `os.environ[...]`.

**The fix:** Add dummy values to the test step's `env:` block — enough to satisfy the import, no real secret needed:

```yaml
- name: Run tests
  env:
    OPENAI_API_KEY: dummy   # satisfies module-level import; no real call made
    GEMINI_API_KEY: dummy
  run: uv run pytest <target> -v
```

**What to run in CI:** Only tests that make no live API calls. Target a specific test or class:
```bash
uv run pytest src/test_foo.py::test_config_only -v
```
Tests that call real APIs → run locally, not in CI (unless you add GitHub Secrets).

**`testpaths` bug to watch for:** If `pyproject.toml` says `testpaths = ["tests"]` but test files live in `src/`, pytest finds nothing. Fix: `testpaths = ["src"]`.

## Step 4 — Local build and smoke test

```bash
# Build
docker build -t <service>:local .

# Smoke test — verify imports resolve, no crash on startup
docker run --rm <service>:local python -c "import <main_module>; print('OK')"

# For servers — verify it binds the port
docker run --rm -p 8000:8000 <service>:local &
sleep 3 && curl -s http://localhost:8000/mcp | head -c 100
```

## Step 5 — Tag and push manually (first publish)

```bash
gh auth token | docker login ghcr.io -u <github_username> --password-stdin

GIT_SHA=$(git rev-parse HEAD)
IMAGE=ghcr.io/<owner>/<repo>/<service>

docker tag <service>:local ${IMAGE}:latest
docker tag <service>:local ${IMAGE}:sha-${GIT_SHA}
docker push ${IMAGE}:latest
docker push ${IMAGE}:sha-${GIT_SHA}
```

## Step 6 — Commit, push, watch CI

```bash
git add <service>/Dockerfile <service>/.dockerignore <service>/pyproject.toml \
        .github/workflows/<service>.yml
git commit -m "Add Dockerfile and CI/CD pipeline for <service>"
git push origin main

# Watch the run
gh run list --workflow=<service>.yml --limit=3
gh run watch <run-id>
```

## Step 7 — One-time GHCR package permissions (required on first push from CI)

CI uses `GITHUB_TOKEN` which has no access to packages created outside Actions until you grant it manually. This always fails the first time with `permission_denied: write_package`.

**Fix (do once per new package):**
1. GitHub → your profile → **Packages** → find `<repo>/<service>`
2. **Package settings** → **Manage Actions access** → **Add repository**
3. Select the repo → role: **Write**
4. Re-run the failed job: `gh run rerun <run-id> --failed`

After this it works permanently — never needed again for this package.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'SOME_KEY'` during `pytest` | Module-level env read | Add `env: SOME_KEY: dummy` to test step |
| `permission_denied: write_package` | GHCR package not linked to repo | Step 7 above |
| CI not triggering after a fix commit | Fix only touched `.github/workflows/` (outside path glob) | Add workflow file to `paths:` + use `workflow_dispatch` to trigger manually |
| `pytest` finds 0 tests | `testpaths` points to wrong dir | Fix `testpaths` in `pyproject.toml` |
| Container exits immediately | Script finished — expected for script services | Not a bug; confirm with `docker run --rm <image> python -c "print('ok')"` |

## Security checklist

- [ ] `uv` pinned to a specific version (not `latest`)
- [ ] Both jobs have explicit `permissions` blocks
- [ ] No real secrets in workflow YAML (dummies only for import-satisfaction)
- [ ] `.env` in `.dockerignore`
- [ ] Non-root user in runtime stage
