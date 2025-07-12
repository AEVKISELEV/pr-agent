# AGENTS Guidelines for PR-Agent

**PR-Agent** is an AI-powered assistant that reviews and augments pull or merge requests. This repository is organized as a Python package with dedicated servers for each git provider, a collection of tools (each implementing a command), and extensive documentation.

## Project layout

- `pr_agent/`
  - `agent/` – dispatcher and request handler (`pr_agent/agent/pr_agent.py`).
  - `tools/` – implementation of each command (e.g. `pr_reviewer.py`, `pr_description.py`).
  - `servers/` – webhook/app servers for GitHub, GitLab, Bitbucket, etc.
  - `git_providers/` – API wrappers for the supported git platforms.
  - `settings/` – default configuration and prompt templates.
- `docs/` – Markdown documentation used by the website under `docs/docs/`.
- `tests/` – unit tests in `tests/unittest` and end‑to‑end tests in `tests/e2e_tests`.
- `.pr_agent.toml` – optional configuration file that overrides defaults. It should be placed in the root of the default branch.

## Loading repository settings

When a command runs, PR‑Agent looks for `.pr_agent.toml` in the target repository. The relevant server calls `get_repo_settings()` to fetch the file via the git provider’s API. The contents are merged with the base configuration inside `apply_repo_settings()` before executing any tool.

## Adding a new command

1. **Create a tool class** in `pr_agent/tools/`, implementing a `run()` coroutine. Use existing tools like `pr_reviewer.py` as a reference.
2. **Register the command** in `pr_agent/agent/pr_agent.py` by adding it to the `command2class` mapping. The command name is what users will type (e.g. `/gen_tests`).
3. **(Optional) Configure automation** by editing `pr_agent/settings/configuration.toml` under the relevant provider section (e.g. `[gitlab].pr_commands`). This determines which commands run automatically on pull/merge request events.
4. **Update documentation**. Add a Markdown file under `docs/docs/tools/` describing the command and link it from `docs/docs/tools/index.md`.
5. **Update help text** in `pr_agent/tools/pr_help_message.py` so `/help` lists the new command.

## Running tests

Install dependencies from `requirements.txt` and `requirements-dev.txt`. Run unit tests with:

```bash
pytest -v tests/unittest
```

Use `pre-commit` to run linters on the changed files:

```bash
pre-commit run --files <file1> <file2>
```
