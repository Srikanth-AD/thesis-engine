# Contributing to thesis-engine

Thanks for your interest in contributing! This project is a personal investment research tool, but improvements that help everyone are welcome.

## How to contribute

1. **Fork** the repository
2. **Create a branch** for your change: `git checkout -b my-feature`
3. **Make your changes** and add tests if applicable
4. **Test locally**: `source .venv/bin/activate && pytest -v`
5. **Lint**: `ruff check .`
6. **Open a pull request** with a clear description of what changed and why

## Ideas for contributions

- **New data layers** -- additional free data sources (e.g., patent filings, job postings, app store rankings)
- **Better sentiment analysis** -- improved keyword lists, NLP-based scoring
- **New alert channels** -- Slack, Discord, Telegram, push notifications
- **Dashboard** -- a simple web UI to view portfolio status without email
- **Backtesting** -- compare thesis-engine alerts against historical price action
- **International stocks** -- better support for non-US markets
- **Options data** -- unusual options activity monitoring

## Guidelines

- **Free APIs only** -- thesis-engine should cost near-zero to run. No paid data providers unless there's a meaningful free tier.
- **Graceful failure** -- every data layer must handle errors silently and return a useful fallback. One broken API should never crash the whole system.
- **Test with `--test`** -- run `python analyzer.py --test` to verify end-to-end behavior before submitting.
- **Pure function tests** -- unit tests should not require API keys. Use mocks for external calls, test pure logic functions directly.
- **Keep it simple** -- this is a personal tool, not an enterprise platform. Prefer clarity over abstraction.

## Code style

- Python 3.10+
- Formatted and linted with [Ruff](https://docs.astral.sh/ruff/)
- Type hints are welcome but not required
- Docstrings on public functions

## Reporting issues

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce (if applicable)
- Relevant log output (redact any API keys or personal data)
