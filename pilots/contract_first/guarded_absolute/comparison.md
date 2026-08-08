# Guarded absolute-value contract-first pilot

This pilot uses existing A-phase signed-i32 semantics; it does not claim that
the historical A stages were contract-first and does not change the checker.

The earlier implementation-first phase gates typically began with a C++
example and expected verifier results. This pilot adds two pre-code artifacts:
the prose task/proposal manifest and a separately marker-free approval. The
human edit changes `value > INT_MIN` to the equivalent, review-explicit
`value != INT_MIN` before the implementation exists.

The correct implementation produces six verified obligations and no other
status. The seeded implementation returns the negative input unchanged. It is
valid C++, but the accepted `result >= 0` intent exposes it as a replayed
postcondition violation. Compiler success alone would not express that intent.

Measured artifact tradeoff: the workflow adds proposal, approval, task
manifest, and run-report evidence around one implementation. In return, the
intent transition, exact accepted contract set, source hashes, and referee
result are independently inspectable and relocation-stable.
