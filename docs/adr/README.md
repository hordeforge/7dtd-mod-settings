# Architecture Decision Records

One file per significant, hard-to-reverse **technical** decision for this
mod: the chosen approach, alternatives considered, and consequences — a
permanent record of *why*, not just *what*. Not for gameplay/balance
decisions (those go in [`../design.md`](../design.md)) and not for routine
implementation notes without a real fork in approach (those go in
[`../architecture.md`](../architecture.md)). See `../../AGENTS.md` for when
a decision warrants an ADR.

Numbered sequentially with a zero-padded 4-digit filename prefix (`0001-`,
`0002-`, …), never renumbered or deleted — a superseded decision gets a
**new** ADR that references and supersedes the old one, with the old one's
`Status` updated to `Superseded by NNNN`.

For a new decision: copy [`template.md`](template.md) into the next unused
number, fill it in, then add it to the index below.

## Index

| # | Title | Status |
|---|---|---|
| 0001 | [The target mod's TOML file is the integration surface](0001-toml-file-is-the-integration-surface.md) | Accepted |
