# Code Context

## Files Retrieved
1. `jules/core/auth_pkce.py` (lines 1-240, 263-560) - OAuth provider config, token store, provider aliasing, PKCE/device-code login, runtime->OAuth mapping, CLI env bridge.
2. `jules/core/router.py` (lines 22-177, 179-351) - task routing, provider registry/build, model enumeration, override parsing, fallback behavior.
3. `jules/providers/base.py` (lines 9-72) - provider protocol every runtime provider must satisfy.
4. `jules/providers/codex.py` (lines 17-95) - current OpenAI-authenticated CLI provider; only provider wired to OAuth env injection.
5. `jules/providers/opencode.py` (lines 27-143) - current coding CLI provider; no OAuth bridge.
6. `jules/providers/antigravity.py` (lines 20-169) - current default cloud CLI provider; profile-based CLI exec, no OAuth bridge.
7. `jules/providers/google.py` (lines 19-107) - native API-key provider shape.
8. `jules/providers/openrouter.py` (lines 22-142) - native API-key provider shape.
9. `jules/providers/ollama.py` (lines 17-182) - local native provider shape and fallback target.
10. `jules/cli/commands.py` (lines 9-21, 33-48, 156-250) - slash command surface for `/model`, `/login`, `/logout`, `/auth`; auth defaults/wording.
11. `tests/unit/test_auth_pkce.py` (lines 31-313) - OAuth config, alias, runtime mapping, CLI env bridge, callback, token-store tests.
12. `tests/unit/test_router.py` (lines 16-44, 47-149, 152-312) - router config fixture and route/fallback expectations.
13. `tests/unit/test_commands.py` (lines 4-68) - slash parsing/help/auth smoke coverage.

## Key Code
- Provider contract is name + `ask/stream/embed/health_check/close` in `jules/providers/base.py:51-72`.
- Router hardcodes task→provider selection:
  - local-only → `ollama` (`jules/core/router.py:66-67`)
  - coding/heavy → `opencode` (`jules/core/router.py:69-73`)
  - analysis/quick/reasoning → `antigravity` (`jules/core/router.py:75-78`)
- Provider instances are hard-wired in `_build_providers()` (`jules/core/router.py:151-177`), including `codex`, `google`, `openrouter`, but route logic never selects `codex` by default.
- OAuth is provider-config driven via `OAuthProviderConfig` in `jules/core/auth_pkce.py:69-91`. Built-ins only exist for `openai` and `claude` in `default_provider_configs()` (`jules/core/auth_pkce.py:208-259`).
- Runtime→OAuth mapping is separate from router/provider names in `resolve_runtime_oauth_provider()` (`jules/core/auth_pkce.py:275-289`):
  - `codex` => `openai`
  - `claude` or `anthropic/`/`claude/` model => `claude`
  - `opencode` currently maps to `None`
- Token acquisition flow:
  1. `login_provider()` resolves config and runs PKCE or device-code (`jules/core/auth_pkce.py:461-477`).
  2. `get_valid_token()` loads store, refreshes, or auto-logins (`jules/core/auth_pkce.py:499-530`).
  3. `cli_environment_for_runtime()` maps runtime provider/model to OAuth provider, fetches token, returns `{cli_env_var: access_token}` (`jules/core/auth_pkce.py:550-579`).
- Only `CodexProvider` consumes that bridge in `_build_env()` (`jules/providers/codex.py:89-95`) and passes env to subprocess (`jules/providers/codex.py:45-52`).
- CLI auth UX is still Codex-oriented:
  - help text: `"login": "Login OAuth: openai | claude | codex"` (`jules/cli/commands.py:16`)
  - `/login` default provider is `openai` and normalizes aliases (`jules/cli/commands.py:200-221`)
  - `/auth` only reports `openai` and `claude` by default (`jules/cli/commands.py:236-250`)

## Architecture
- `jules/cli/commands.py` is the user entrypoint for auth commands; it dynamically imports `jules.core.auth_pkce` and never touches provider classes directly.
- `jules/core/auth_pkce.py` is the auth subsystem boundary: provider metadata, token storage, PKCE/device-code flows, refresh, status, and the runtime env bridge.
- `jules/core/router.py` is the runtime dispatch boundary: it picks a provider instance and model from config/task type, then calls `provider.ask(...)`.
- Providers are heterogeneous:
  - CLI wrappers: `codex`, `opencode`, `antigravity`
  - native/API-key: `google`, `openrouter`, `ollama`
- Slice-1 implication: an OpenAI OAuth native provider can be added without changing CLI auth flow first, but it will not be used until router selection and/or model override surfaces can target it.

## Start Here
Open `jules/core/auth_pkce.py` first. It already contains the OpenAI OAuth defaults and the only runtime auth bridge; Slice 1 should start by generalizing `resolve_runtime_oauth_provider()` and `cli_environment_for_runtime()` around the new OpenAI-native runtime/provider name before touching router behavior.

## What must change first for an OpenAI OAuth native provider
1. `jules/core/auth_pkce.py`
   - `resolve_runtime_oauth_provider()` (`275-289`): map the new runtime provider name/model family to `openai`.
   - `cli_environment_for_runtime()` (`550-579`): ensure the new runtime gets the right env contract, or split this into a more generic runtime-auth bridge if native provider needs bearer token access another way.
   - Potentially `OAuthProviderConfig` / `default_provider_configs()` (`69-91`, `208-259`) only if the native provider needs a different env var or extra token metadata.
2. `jules/providers/` 
   - Add new provider module beside existing ones, following `Provider` protocol from `jules/providers/base.py:51-72`.
   - If it shells out like Codex, mirror `CodexProvider._build_env()` (`89-95`); if it is truly native, it likely needs direct token loading via `get_valid_token()` instead of env injection.
3. `jules/core/router.py`
   - `_build_providers()` (`151-177`): register the new provider instance.
   - `route()` / `_models_for_provider()` / `_configured_models()` (`59-78`, `230-260`): make the provider selectable for at least one task tier and discoverable via `/model`.
4. `jules/cli/commands.py`
   - Update auth help/default wording only after the runtime/provider name is settled (`9-21`, `200-250`).
   - If user-facing provider name differs from OAuth provider id (`openai`), keep normalization/user text aligned.

## Minimal safe Slice 1 implementation order
1. `jules/core/auth_pkce.py`: extend runtime→OAuth mapping for the new provider/model family; keep token store/config ids unchanged as `openai`.
2. Add new `jules/providers/<openai_native>.py` implementing `Provider` and fetching OpenAI auth through auth_pkce.
3. `jules/core/router.py`: register provider in `_build_providers()`, expose its models in `_configured_models()` / `_models_for_provider()`, then route one narrow task class to it or allow explicit override first.
4. `jules/cli/commands.py`: update `/model`/`/login` help text only after routing/provider naming is stable.
5. Then broaden default routing if desired.

## Test files to update first
1. `tests/unit/test_auth_pkce.py`
   - Extend alias/runtime mapping tests (`264-292`) for the new runtime provider/model family.
   - Add env/token bridge expectations for the new provider if Slice 1 uses env injection.
2. `tests/unit/test_router.py`
   - Expand `CONFIG_TEXT` + `make_router()` (`16-44`, `142-149`) to include the new provider.
   - Add route/override expectations before changing defaults (`152-312`).
3. `tests/unit/test_commands.py`
   - Update parsing/help/auth default-provider text only if slash command surface changes.

## Risks / constraints
- Router and auth use different vocabularies today (`codex` runtime => `openai` OAuth). A new provider name will repeat that split unless normalized deliberately.
- `_models_for_provider()` in `jules/core/router.py:248-260` is closed over explicit provider names; forgetting it breaks routing and `/model` enumeration.
- Current tests assume coding routes to `opencode` and quick/reasoning to `antigravity`; changing defaults early will cascade through `tests/unit/test_router.py`.
- `tests/unit/test_commands.py` is shallow; command behavior changes need new async tests, not just parse/help updates.

## Recent Architectural Shifts (Phase 2)
1. **OpenAI OAuth WebSockets**: `openai_oauth.py` now uses WebSockets (`wss://chatgpt.com/backend-api/codex/responses`) and bypasses Cloudflare using `response.create`. Note: The Codex API hard-blocks models like `gpt-4o`, `o1`, and `o3` for standard ChatGPT accounts. Only `gpt-5.4` and `gpt-5.5` families are supported. If the account lacks quota, the error changes to `The usage limit has been reached`.
2. **TUI Provider Hierarchy (Planned)**: The monolithic `/model` command will be refactored into a `/provider` hierarchy (`cli`, `oauth`, `api`). The TUI will use interactive Modals (Textual OptionList) to initialize providers and then dynamically autocomplete `/model` based on the active provider.
