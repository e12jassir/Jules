---
name: agent-superpowers
description: "Trigger: upgrade agent, terminal assistants, agent capabilities, pi, agy, opencode. Apply SOTA cognitive shell and agentic behaviors (context mapping, agentic search, persistent shell state, self-correction)."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Run this skill to upgrade the cognitive behaviors of the Agent Team (primarily Pi [terminal assistant] and agy/Antigravity [architect]), bringing SOTA terminal assistant superpowers (like Claude Code and Aider) into prompt executions.

---

## 1. Context Compression & Codebase Mapping (agy & Pi)

To avoid saturating the LLM context window with raw code, the agent MUST use a structured repository map:

- **Signatures Over Prose**: When analyzing the codebase structure, only read and output class definitions, function signatures, and imports. Omit full implementation bodies unless specifically requested.
- **Dynamic Tree-Sitter / Ripgrep extraction**:
  - Before writing code, use a glob or `find` to map the workspace up to depth 3.
  - If a file is relevant, extract its high-level interface rather than reading all 400+ lines.
- **Context Budgets**: Limit injected file context to a maximum of 1,500 tokens per turn. Use the `view_file` tool specifying precise line ranges (`StartLine` and `EndLine`) to read only the target blocks.

---

## 2. Agentic Search Loop (glob, grep, read)

Stop guessing file paths or asking the user where things are. The agent MUST follow the "Agentic Search" hierarchy:

1. **Glob / List**: Use file-glob tools or fast listings to find files matching a name or extension.
2. **Ripgrep (`grep_search`)**: Run high-speed regex content searches to locate exact symbols, variable definitions, or error strings in the current state of the workspace (respecting `.gitignore`).
3. **Read (`view_file` range)**: Read the specific lines returned by Ripgrep. Never read entire files if only a 20-line block is relevant.

---

## 3. PTY Shell & Stateful Subprocesses (Pi & OpenCode)

Ensure execution continuity and eliminate sandbox startup taxes:

- **Directory Tracking**: Always track the active working directory (`cwd`) across subprocess execution. If the platform runs stateless subprocesses, chain commands using `cd <dir> && <command>` to maintain continuity.
- **TTY Emulation**: When writing scripts for process execution, force terminal outputs to support ANSI colors and non-blocking streaming so standard outputs are parsed in real time.
- **Safe Permissions**: Tier actions into safe (read, list, grep) and destructive (rm, write, force commit). Destructive operations MUST trigger an interactive confirmation gate for the developer.

---

## 4. Self-Correction & Debugging Loop (OpenCode & agy)

When a command, compilation, or test fails during an autonomous run:

- **Do Not Panic / Do Not Stop**: If exit code `!= 0`, the agent enters `debugging` intent.
- **Analyze stderr**: Extract the exact error message, filename, and line number from the console output.
- **Locate & Repair**:
  1. Jump directly to the failing coordinate using `grep_search` and `view_file`.
  2. Map the mismatched interface or type signature.
  3. Formulate the fix, apply it, and rerun the test suite automatically.
  4. Only ask the user if the error is due to an external sandbox dependency issue or missing API keys.
