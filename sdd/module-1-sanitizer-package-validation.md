# Package Validation: module-1-sanitizer

## Status
PASS

## Purpose
Validate that the post-review packaging fix (`[tool.setuptools.packages.find] include = ["jules*"]`) includes `jules.sanitizer` in a built distribution and that installed callers can import it.

## Commands

| Command | Result |
|---|---|
| `./.venv/bin/python -m pip wheel . --no-deps -w /tmp/jules-package-check/dist` | PASS — built `jules-0.1.0-py3-none-any.whl` |
| wheel content inspection via Python `zipfile` | PASS — wheel contains `jules/sanitizer/__init__.py` and `jules/sanitizer/sanitizer.py` |
| isolated venv install from wheel with `pip install --no-deps` | PASS — installed `jules-0.1.0` |
| isolated import check: `from jules.sanitizer import Sanitizer, SanitizeResult` | PASS |
| isolated behavior check: `Sanitizer.check("api_key=abc123")` | PASS — returned `SanitizeResult False assignment_secret` |

## Notes
- Build dependencies were installed by pip in an isolated PEP 517 build environment; no global install was performed.
- Runtime install check used `/tmp/jules-install-check` and installed the locally built wheel with `--no-deps`.
- Temporary validation outputs live under `/tmp/jules-package-check` and `/tmp/jules-install-check`.
