# Repository Guidelines

## Project Structure & Module Organization

- `app/` contains the FastAPI backend: `main.py` defines routes and trading orchestration, `paper.py` implements simulated trading, `models.py` defines data models, `state.py` handles persistence, and `toss_client.py` integrates market data.
- `frontend/` contains the directly served HTML, CSS, and vanilla JavaScript dashboard; there is no frontend bundler.
- `tests/` contains Python backend tests and CommonJS UI tests. `assets/` holds screenshots and the favicon.
- `data/paper-state.json` is generated account state and is excluded from Git. `PRD.md` describes requirements; `README.md` documents behavior and setup.

## Build, Test, and Development Commands

Run commands from the repository root:

- `python -m venv .venv` creates a virtual environment; on PowerShell, activate it with `.\.venv\Scripts\Activate.ps1`.
- `python -m pip install -r requirements.txt` installs backend and pytest dependencies.
- `Copy-Item .env.example .env` creates local configuration; fill in your own credentials.
- `python -m app` starts the dashboard at `http://127.0.0.1:8000`. Restart after backend changes; automatic reload is disabled.
- `python -m pytest tests` runs backend tests.
- `node --test tests/manual_sell_ui.test.cjs tests/manual_refill_ui.test.cjs tests/commissions_ui.test.cjs tests/trade_history_ui.test.cjs` runs UI tests using Node's built-in runner.

There is no separate build step or configured formatter/linter.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, `PascalCase` classes, and type annotations in Python. Use `Decimal` for monetary calculations. Match the frontend's two-space indentation, `camelCase` names, and semicolon usage. Preserve UTF-8 Korean interface text and keep changes focused on the relevant module.

## Testing Guidelines

Name Python tests `tests/test_<feature>.py` with `test_<behavior>` functions; name UI tests `<feature>_ui.test.cjs`. Cover changed trading rules, budget limits, duplicate requests, and persistence failures. Mock market-data calls and isolate state with temporary files. No numeric coverage threshold is configured. Run both suites for changes spanning API and UI behavior.

## Commit & Pull Request Guidelines

History uses short Korean or English subject lines, often describing a feature or work date; no enforced prefix convention is evident. Prefer concise subjects describing the actual change. PRs should explain behavior, list test commands and results, link relevant issues, and include screenshots for visible dashboard changes.

## Security & Configuration

Keep `.env`, credentials, and generated account state out of commits. Preserve PAPER-only execution. Run one server process per state file; do not increase Uvicorn workers. Persistence failures must cancel changes, and invalid snapshots must prevent startup rather than silently reset the account.
