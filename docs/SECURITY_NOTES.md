# Security Notes

- Do **not** commit secrets. Always load credentials via environment variables.
- Treat third-party skills/extensions as untrusted. Pin versions and audit before use.
- Follow least-privilege: avoid granting permissions you do not need.
- Prefer offline-first workflows (local logs/reports) and explicitly opt-in to network actions.
- Keep `ENABLE_LIVE_TRADING` disabled unless you intentionally accept real order risk.
