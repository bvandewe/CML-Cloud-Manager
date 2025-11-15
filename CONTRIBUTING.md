# Contributing

Thanks for your interest in improving this Neuroglia FastAPI template!

## Quick Start

1. Fork or use the GitHub Template to create your copy.
2. Create a feature branch: `git checkout -b feat/short-description`
3. Install dependencies: `make setup`
4. Run tests & lint: `make test && make lint`
5. Commit with DCO sign-off (see below) and open a PR.

## Development Workflow

- Keep PRs focused and small; prefer incremental improvements.
- Include tests for new behavior (happy path + at least one edge case).
- Update documentation (`README.md`, `docs/`) if user-facing behavior changes.
- Avoid large refactors mixed with feature changes—split into separate PRs.

## Code Style & Tooling

- Python formatting: Black
- Imports: isort (via `make lint` / `make format`)
- Testing: pytest
- Types: (Optional) Add type annotations where helpful; avoid over-specifying.

## Commit Messages

Format: `<type>: <short summary>`

Common types:

- feat: new feature
- fix: bug fix
- docs: documentation only
- refactor: code restructuring without feature change
- test: add or adjust tests
- chore: build / tooling / dependency updates

Example:

```
feat: add Redis session store backend
```

## DCO (Developer Certificate of Origin)

This project uses a lightweight DCO process instead of a CLA. Every commit must be signed off to certify you have the right to submit the work.

Add this line to each commit message (or use `git commit -s`):

```
Signed-off-by: Your Name <your.email@example.com>
```

If you forgot to sign off, you can amend and force push:

```
git commit --amend -s
git push --force-with-lease
```

## Pull Request Checklist

Before marking your PR ready for review:

- [ ] Code builds locally (`make run` succeeds)
- [ ] Tests pass (`make test`)
- [ ] New code is formatted (`make format`)
- [ ] Lint passes (`make lint`)
- [ ] Added/updated tests for changes
- [ ] Added/updated docs if behavior changed
- [ ] Commits are signed off (DCO)

## Tests

Place new tests under `tests/` in an appropriate domain folder or alongside existing patterns.

Recommended minimal coverage for features:

- Core logic path
- Failure or edge condition (e.g., invalid input, unauthorized access)

Run:

```
make test
make test-cov
```

## Security

- Do not include secrets in commits.
- Prefer environment variables for sensitive config.
- Report potential vulnerabilities privately (open an issue labeled "security" with minimal detail and request maintainer contact).

## Release Notes / Changelog

If your change is user-impacting, add an entry to `CHANGELOG.md` under `Unreleased` with format:

```
### Added | Changed | Fixed | Removed
- Short description (#PR_NUMBER)
```

## Attribution

By contributing you agree your contributions are licensed under Apache 2.0 and you certify compliance with the DCO.

---
Thanks again for helping improve this template! 🎉
