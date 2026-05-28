# Design — Module 5 Cognitive Router

## Summary
The router prepares Antigravity per-model config profiles ahead of request execution, routes by task tier with same-tier secondary fallback, fails closed for local-only tasks, and keeps provider setup off the event loop.

## Key Decisions
- Use static per-model Antigravity profiles under `~/.jules/agy_profiles/<safe-model>`.
- Pass prompts to `agy` using POSIX separator form: `agy --print -- <prompt>`.
- Resolve exact configured model overrides before interpreting `provider:model` syntax.
- Build the router singleton inside `asyncio.to_thread(...)` so config/profile preparation does not block the event loop.
- Keep tests with the behavior they verify.
