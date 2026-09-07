---
name: lean-dev
description: >-
  Use whenever writing, generating, or modifying code, including new features,
  scripts, components, or fixes. Also use when the user asks to review my diff,
  review my changes, audit this repo, review this code, or asks whether something
  is over-engineered, over-built, or has unnecessary complexity. Keeps
  implementations minimal, preferring the smallest correct solution over new
  abstractions, wrapper components, or dependencies, without ever cutting corners
  on security, validation, error handling, or accessibility. Trigger this even if
  the user doesn't mention minimal or simple explicitly; it applies by default to
  all code-writing tasks.
---

# Lean Dev

Write the smallest amount of code that correctly and safely solves the task. Never add structure, abstraction, or dependencies the task doesn't yet need.

## The ladder

Before writing any code, walk this list top to bottom and stop at the first rung that solves the problem:

1. **Does this need to exist at all?** If the task can be solved by deleting code, config, or a whole feature request's premise, do that instead of adding more. (YAGNI)
2. **Does the current codebase already do this?** Search before writing — reuse an existing helper/util/component rather than re-implementing it.
3. **Does the standard library handle it?** Prefer built-ins over a package.
4. **Does a native platform feature handle it?** e.g. `<input type="date">` instead of a date-picker library; native `fetch` instead of a wrapper; CSS instead of a JS animation library.
5. **Is a dependency already installed that handles it?** Use what's already in package.json/requirements — don't add a new one for something one existing library can do.
6. **Can it be done in one line or a few lines?** Don't build a class, a config object, or a plugin system for something a single function does.
7. **Only if none of the above apply**: write the minimum new code that correctly solves the task.

Read and understand the surrounding code and the actual problem *before* picking a rung — this ladder governs the solution, not the understanding. Don't skip reading in the name of being lazy.

## Language-specific tuning

The ladder above was written with dynamic/scripting languages in mind (its rung 4 example is a browser). Some languages have their own definition of "minimal," and the ladder should be read through that lens rather than applied literally.

### Rust

- **Rung 3 vs. rung 5 — idiomatic crates aren't rung 7.** In Rust, ecosystem-standard crates for error handling (`thiserror`, `anyhow`), serialization (`serde`), and async (`tokio`) are the idiomatic minimal solution, not a shortcut to avoid. Treat them like rung 4 ("native platform feature") rather than holding out for hand-rolled `impl std::error::Error` or a bespoke parser. Fighting the ecosystem to stay dependency-free usually produces *more* code, not less.
- **What over-engineering looks like in Rust** (apply the same "cut this" instinct from the ladder, just retargeted):
  - Generic type parameters or trait bounds with only one real caller — a concrete type is simpler until a second caller actually shows up.
  - Reaching for `Arc<Mutex<T>>` or `dyn Trait` in single-threaded, single-implementation code where an owned value or a plain `enum` would do.
  - Builder patterns or config structs for types with a handful of fields that could just be constructed directly.
  - Unnecessary `.clone()` calls papering over a borrow-checker fight that a lifetime or restructure would resolve more simply.
- **What is *not* over-engineering in Rust**, even though it can look verbose: explicit lifetimes, `Result`/`?` propagation, and trait bounds the type system actually requires. Don't "simplify" these away — that's fighting correctness, not cutting bloat.
- **If this skill and your `rust` skill disagree** (e.g. this ladder says "avoid the dependency," the rust skill says "that crate is the idiomatic choice"), defer to the `rust` skill's idiom guidance. This skill's job is to stop over-building, not to override language-specific best practice.

## Non-negotiables (never cut these to save lines)

- Input validation at trust boundaries (user input, API responses, file reads, env vars)
- Error handling for anything that can fail (network calls, file I/O, parsing)
- Protection against data loss (confirmations before destructive ops, no silent overwrites)
- Security basics (no secrets in code, no injection vectors, proper auth checks)
- Accessibility (semantic HTML, labels, keyboard nav) for anything user-facing

If following the ladder would mean skipping one of these, go to the next rung instead — being lean is about not over-building, not about being negligent.

## Marking shortcuts

When you deliberately take a shortcut that trades completeness for simplicity (e.g. "this doesn't handle the multi-timezone case because the app is single-timezone today"), leave a one-line comment marking it:

```
// lean-dev: single-timezone only — revisit if multi-region ships
```

This keeps deferred complexity visible instead of silently missing.

## Commands (invoke by asking in plain language)

There's no slash-command system here — just ask for these directly and this skill will follow the corresponding procedure:

### "Review this diff" / "review my changes"
Look at the diff (or the files just written/edited). For each change, check:
- Is there a dependency, wrapper, or abstraction that a native feature or existing util could replace?
- Is there unused flexibility (config options, parameters, generality) nothing currently calls for?
- Could any function collapse to fewer lines without losing clarity or a non-negotiable above?

Report back as a short list: what to cut, and why, referencing the ladder rung that applies. Don't rewrite unprompted — let the user say go-ahead.

### "Audit this repo" / "audit for over-engineering"
Same lens as above but scanning the whole project (or a directory the user names) rather than just a diff. Sample the largest/newest files first — that's where over-building accumulates. Summarize patterns (e.g. "3 different date-formatting utilities exist; codebase could standardize on one native `Intl.DateTimeFormat` call") rather than listing every line.

### "Show me what this saved" / "what did lean-dev change"
If you've been tracking shortcuts taken (via the `lean-dev:` comment convention above), summarize them: what was skipped, and what would need to happen for a fuller version to become worth building.

## Notes

- This skill is deliberately just a ruleset, not a plugin — it has no hooks, no background processes, and doesn't run any code on its own. It only shapes how code gets written when this skill is active in context.
- Works the same whether you're using Claude Code, Claude.ai, or Cowork — it's just instructions the model follows, not a separate tool.
