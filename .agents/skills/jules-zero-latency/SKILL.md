---
name: jules-zero-latency
description: "Trigger: core logic, memory engine, async IO, terminal response. Ensure zero latency terminal responses by moving heavy IO to background tasks."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Run this skill when modifying the CLI entrypoint, memory engine, or any code that runs in the synchronous path before delivering a response to the user.

## Hard Rules

- NEVER block the event loop with synchronous I/O.
- Persistence, scoring, embeddings, and post-processing MUST run asynchronously.
- The user's terminal MUST receive the response immediately after the provider returns it.

## Execution Steps

1. Identify any new I/O operations (SQLite, LanceDB, API calls).
2. If they are not required to generate the immediate text response, wrap them in `async def`.
3. Invoke them using `asyncio.create_task(function_name())` instead of `await`.
4. Add a unit test verifying that the response is returned before the background task completes.
