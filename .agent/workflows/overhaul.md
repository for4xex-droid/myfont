# Overhaul Workflow

> **Source License**: Based on `code-overhaul-skill` by David Hewison (MIT License). Customized for the Aiome ecosystem by the Antigravity Agent.
> **Description**: A comprehensive protocol for overhauling, refactoring, and restructuring code with zero downtime and strict adherence to Aiome's TypeState patterns and Golden Rules.

## Prerequisites

Before executing this workflow, the user must define the scope of the overhaul. Overhauls should be limited to individual modules, traits, or components to prevent massive, unreviewable pull requests.

## Workflow Steps

### Step 0: Preflight Impact & Audit (Aiome Specific)

Before making any structural changes, you MUST map the dependencies and potential blast radius:

1. **Impact Query**: Run `grep_search` for the main structures you plan to overhaul to find all usages and dependencies.
2. **Architecture Audit**: Review `ARCHITECTURE.md` (repository root, auto-generated) to ensure you aren't violating implicit module isolation.
3. Review `.context/RIPPLE_MAP.md` to identify any previously recorded architectural invariants for the target modules.

### Step 1: Baseline Analysis

1. Read the target files carefully using `view_file`.
2. Do NOT use search tools like `grep` unless you are tracing an undocumented symbol. Prefer `view_file`.
3. Identify:
    - Current dependencies
    - Trait boundaries and `impl` blocks
    - Potential code smells or technical debt

### Step 2: Implementation Plan Generation

Create an artifact (e.g., `overhaul_plan.md`) formatted like the Perfect Plan. It must include:
- **Rust specifics**: Which types or traits will be refactored? Will TypeState be introduced?
- **Web/JS/CSS specifics**: Will the changes align with the UX Golden Rules?
- **Test Strategy**: How will you prove the overhaul hasn't broken existing behavior?

**CRITICAL**: Prompt the user to approve the plan before proceeding.

### Step 3: Execution (The "Heart Transplant")

Execute the overhaul systematically:

1. **Create the New Structure**: Write the new interfaces, types, and logic alongside the old ones. Do not delete the old code yet!
2. **Port Tests**: Ensure tests point to the new structure, or write new tests if the type signatures changed.
3. **Rust Addendum**:
    - Ensure zero `unsafe` blocks are added (`#[forbid(unsafe_code)]`).
    - Maintain strict TypeState boundaries where state transitions dictate logic.
4. **Web Addendum** (if touching UI):
    - Verify against `.agent/skills/docs-ui-ux-golden-rules.md`.
    - Do not break existing CSS animations.

### Step 4: Verification

1. **Compilation**: Run `cargo check --workspace --tests`
2. **Quality**: Run `cargo clippy --workspace -- -D warnings`
3. **Tests**: Run `cargo test --workspace`
4. **UI Validation**: If UI changed, generate a visual or run local UI checks.

### Step 5: Cleanup & Deferral (Aiome Ripple Map)

1. **Delete Old Code**: Once tests pass on the new structure, safely remove the old code.
2. **Deferred Work**: If there were minor cleanup tasks or out-of-scope refactors you noticed, DO NOT leave `TODO` comments. Instead, append them to `.context/RIPPLE_MAP.md` under a "Deferred Overhauls" section.
3. **Changelog**: Update `CHANGELOG.md` to reflect the internal refactoring and improved maintainability.

## Engineering Preferences

- Always favor explicit compile-time errors (via TypeState) over runtime `Result` checks where feasible.
- Do not add external dependencies without explicit user permission.
- Ensure all struct fields and logic adhere strictly to the Aiome Agentic adaptation rules outlined in `AGENTS.md`.
