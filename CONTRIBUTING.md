# Contributing

Pull requests are welcome: bug fixes, new helpers, better docs.

1. Fork, branch, and keep the change focused.
2. Python: `uv sync && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.
3. JavaScript: `cd js && npm install && npm run typecheck && npm test`.
4. Tests run on fixtures only (`tests/fixtures/`, `js/test/`). Never commit a real API key, secret, token or a real
   person's vehicle data; use made-up registrations.
5. Keep both languages in step when you change behaviour, and note it in the README.

Found a quirk in the DVSA API? Open an issue with the request (minus credentials) and the response shape.
