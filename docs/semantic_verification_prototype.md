# Semantic Verification Prototype

## Status and scope

This document describes the prototype implemented in the US repository after
a read-only investigation of CodeSkeptic commit
0df016efa19182ebc9ef417b6e7bcd285ef73ecd.

CodeSkeptic itself was not changed. The prototype is an isolated vertical slice,
not a production integration and not a general C++ verifier.

Implemented:

- real Clang C++ parsing through the JSON AST interface;
- an owned, deterministic, versioned Semantic IR for branches, modular calls,
  invariant-annotated while loops, exact owned fixed-size arrays, and value records;
- strict inline cs: preconditions, postconditions, and loop invariants;
- path-specific VCs for contracts, signed i32/i64 definedness, unsigned
  u32/u64 modulo arithmetic, conversions, bitwise/shift definedness, modular
  calls, and loop obligations;
- a dependency-free affine checker plus a complete external Z3 backend for the
  emitted homogeneous QF_LIA/QF_BV/QF_ARRAY/QF_RECORD fragments;
- exact local `array<E,N>` values (`1 <= N <= 64`), whole-array SSA stores,
  per-access bounds VCs, contract indexing, QF_ALIA/QF_ABV, and array-model replay;
- named public value `struct` types with scalar/array/nested fields, whole-record
  SSA, field projection/update, copy isolation, by-value calls, QF_RECORD
  datatype emission, and typed model replay;
- deterministic SMT-LIB2, solver timeouts, model parsing, mandatory replay,
  minimized/relevance-projected counterexample cores, and source-mapped branch
  traces for violated paths;
- affine/Z3 cross-check mode as the CLI default, with disagreement promoted to
  solver_error;
- explicit verified, violated, unknown, unsupported, and solver_error results;
- explicit machine-readable loop-termination non-goals;
- deterministic JSON, human-readable output, a versioned golden corpus, and a
  two-process byte-identity CI gate;
- an opt-in persistent exact-result cache keyed by report/key schema, backend
  identity/configuration, solver policy, and canonical obligation semantics;
- deterministic source-ordered per-file check budgets plus positive finite
  per-process solver timeouts, with exhaustion remaining explicit `unknown`;
- a committed scaling slice and hash/count-based phase gate covering exact join
  compaction, uncached/warm cache identity, and repeated budget identity;
- a fixed-width integer phase gate freezing the target profile, conversion and
  operator tables, homogeneous classifier, backend matrix, replay evidence, and
  v1-to-v4, v2-to-v4, and v3-to-v4 migration equivalence;
- 260 deterministic tests, including independent soundness regressions.

Partially implemented:

- modular calls are direct only; assigned/initialized results must have matching
  fixed-width type, and callers learn results from callee ensures rather than
  body inlining;
- recursive call cycles are rejected until a decreasing-measure policy exists;
- loops are while-only, require user-written invariants, and establish partial
  correctness without proving termination;
- signed-only QF_LIA multiplication requires a literal operand; QF_BV supports
  variable multiplication;
- source mapping is statement-granular, but preserves CRLF and Clang UTF-8
  byte offsets;
- the dependency-free affine checker is deliberately incomplete and rejects
  QF_BV, QF_ARRAY, and QF_RECORD; Z3 is complete for every emitted homogeneous fragment;
- v0 through v3 are archived and v4 is current; owned C++17 fixed-width types lower
  to `i32`/`u32`/`i64`/`u64`, integer wire evidence is canonical decimal text,
  and Clang must pass the pinned target-profile probe before lowering.

Proposed, not implemented:

- a native clang::ASTContext adapter inside CodeSkeptic;
- reuse of CodeSkeptic .csk sidecars;
- production diagnostic/SARIF/MCP adapters for proof results and models;
- broader C++ value, memory, alias, and ownership semantics;
- loop termination variants or invariant inference;
- automated repair/AI-loop integration.

## Problem statement

The experiment tests whether structured C++ behavior can cross a stable
boundary:

    C++ source
      -> Clang AST
      -> Semantic IR with explicit state versions
      -> verification conditions
      -> deterministic checker
      -> proof status or counterexample

The verifier layer does not consume C++ syntax or Clang node identities.

## Non-goals

The prototype does not attempt:

- a new programming language;
- full C++ verification;
- arbitrary pointer, heap, ownership, alias, or lifetime reasoning;
- templates, exceptions, virtual dispatch, concurrency, volatile, inline
  assembly, or macro semantics;
- loop termination; verified loop obligations establish partial correctness
  only;
- external-library modeling without contracts;
- automatic repair or AI authority over proof results;
- production certification claims.

## Repository findings

### Current CodeSkeptic architecture

CodeSkeptic is a C++17 application using LLVM/Clang LibTooling. Its pipeline is:

    Config / CLI / MCP
      -> StaticAnalyzer
      -> SourceManager (compile database + ClangTool)
      -> ASTContext callback
      -> RuleEngine
      -> Rule implementations using CfgCache/DataflowEngine
      -> Diagnostic
      -> console / JSON / SARIF / HTML reporters

Relevant implementation points in the inspected revision:

- src/source_manager/SourceManager.h exposes processAll(ASTCallback), where the
  callback receives clang::ASTContext&.
- src/engine/RuleEngine.cpp builds summaries before rules and clears
  translation-unit-local pointer caches afterward.
- src/core/Rule.h provides the narrow extension method
  check(ASTContext&, DiagnosticList&).
- src/engine/CfgCache.cpp centrally builds fine-grained Clang CFGs.
- src/engine/DataflowEngine.h supplies a generic worklist/fixpoint engine over
  Clang statements.
- src/contracts/ContractParser.*, ContractInfo.*, and Sidecar.* already
  implement inline cs: comments and anchored .csk contracts.
- src/reporter/JsonReporter.cpp, SarifReporter.cpp, and
  src/server/McpServer.cpp already provide machine-readable consumers.

### Reusable components

The production implementation can reuse:

- compile-database-aware Clang parsing and broken-TU handling;
- the AST callback and function matcher;
- source-location extraction;
- the existing cs: parser/attachment behavior, extended with arithmetic;
- shared CFG construction where it helps validate control-flow reachability;
- deterministic sorting/serialization conventions;
- JSON/SARIF/MCP output adapters;
- the in-memory Clang test harness.

### Missing components

CodeSkeptic has no persistent Semantic IR, VC generator, SMT/Z3 integration, or
countermodel data model. Existing abstract domains are rule-specific and operate
directly on clang::Stmt*. They intentionally lose relational equalities such as
result = balance - amount.

The current Diagnostic shape represents findings and trace notes, but not
positive proof outcomes, unknown, unsupported, solver errors, obligations, or
concrete models. An unconstrained argument to an integer non-zero precondition
can currently be silent; silence therefore does not mean verified.

### Narrowest viable integration point

The narrowest production seam is a new semantic-verification rule/adaptor at
Rule::check(ASTContext&, ...):

    existing SourceManager / ASTContext
      -> new SemanticLowerer
      -> owned Semantic IR
      -> ContractAdapter
      -> VcGenerator
      -> Checker
      -> VerificationResult
      -> optional Diagnostic adapter

The existing DataflowEngine should not be converted into the Semantic IR.
It is valuable for specialized abstract interpretation, but its contract is
Clang-statement transfer rather than stable program serialization.

## Prototype architecture

### Frontend

semantic_verifier/frontend.py invokes Clang 20 with ast-dump=json and rejects a
translation unit when Clang reports a compile error. This is a real C++
frontend, but the subprocess bridge is prototype-only. It avoids linking a
second copy of the Clang libraries into this isolated repository.

The adapter preserves raw line endings, converts Clang byte offsets to Python
string offsets, normalizes temporary paths out of diagnostics, and filters AST
nodes by the physical main-file identity. Includes are intentionally reported
as unsupported in v0; declarations originating in headers are not mistaken for
main-file functions.

In CodeSkeptic, the equivalent adapter should consume ASTContext directly.
Only the frontend adapter changes; the IR, VC, checker, and result layers do
not.

### Semantic lowering

semantic_verifier/lowering.py accepts only known AST shapes and copies all
meaning into owned values. It never serializes Clang pointer IDs. Variables are
monotonically versioned:

    y#0 := x#0
    y#1 := (y#0 + 1)

Branches contain separate true/false node sequences. When both edges continue
with different versions, an explicit merge is emitted:

    branch (x#0 > 0)
      true:  y#1 := 1
      false: y#2 := 0
      merge y#3 := [true: y#1, false: y#2]

Assigned int call results receive fresh SSA targets. A while node owns its
invariants, one symbolic body iteration, and deterministic entry/head/back-edge/
exit names for every loop-modified variable. Head and exit names are explicit
havoc states; they are never equated to a guessed iteration count.

Stable function, symbol, and node IDs are assigned in source traversal order.
Locations use the caller-visible path plus one-based line and column.
Disjoint lexical scopes may reuse a C++ spelling, but receive distinct IR
identities such as y#0 and y@2#0. Same-name/same-arity overloads are keyed by a
deterministic parameter-type signature in this prototype.

If any semantic node in a function is unsupported, that function is replaced
by one unsupported IR node and no ordinary obligations are generated for it.
This is the fail-closed boundary.

### Semantic IR

The implemented node kinds are:

- function, parameter, and local metadata;
- assume, assign, assert, and return;
- branch plus explicit merge nodes;
- direct call, optionally with a fixed-width or value-record result target and type;
- loop with invariants, a body, loop-variable havoc metadata, and the explicit
  termination=non_goal record;
- unsupported.

Expressions contain typed constants, versioned variables, unary not/negation,
arithmetic, comparisons, boolean connectives, owned `array`/`select`/`store`
expressions, `record`/`project`/`update` expressions, and the exact
`signed_no_overflow` safety predicate. The JSON schema identifier is
`codeskeptic.semantic-verification/v4`. Serialization uses sorted JSON object
keys and source-ordered arrays. Compatibility and major-version triggers are
defined in the [schema version policy](schema_versioning.md).
Heap allocate/release and pointer-based load/store remain proposed. Adding them without
an alias and memory model would create false confidence.

### Contract model

The least disruptive surface is CodeSkeptic's existing structured line-comment
style:

    // cs: requires b != 0
    // cs: ensures result > x

The prototype also accepts return as an alias for result in contract
expressions. Supported contract expression syntax is:

- integer and boolean literals;
- parameter names and result/return;
- addition and subtraction;
- multiplication, division, and remainder at parse time (the checker later
  enforces the supported logic fragment);
- bitwise complement/and/or/xor plus left/right shifts with C++ precedence;
- six comparisons;
- boolean and, or, and not;
- parentheses.

Only the contiguous line-comment block immediately before a function is
attached for requires/ensures. A contiguous cs: invariant block attaches only
to the immediately following while statement and can reference variables in
scope there. result/return is available only to ensures. Malformed clauses,
wrong attachment, and orphan cs: comments produce explicit unsupported results.
The source parameter name result is reserved to prevent collision with the
postcondition result symbol. Sidecars are not implemented in US, although
CodeSkeptic's existing sidecar loader is reusable.

### Verification-condition generation

The VC generator enumerates acyclic structured paths and one symbolic body
iteration per loop. Each obligation is:

    path assumptions -> required condition

Assignments become equality facts over versioned variables. True and false
edges add the condition or its negation and retain guarded branch source
provenance. A structured join factors common assumptions and represents the
exact union of residual path conjunctions as one disjunction; merge equalities
remain inside the edge that selected them. A result-bearing call havocs its
fresh target, adds signed destination-width bounds, proves substituted requires,
and assumes substituted ensures. Recursive
call components fail closed.

A loop proves each invariant at the concrete entry state, checks one arbitrary
bounded head state under I and the condition, and proves I again at the back
edge. Code after the loop sees an independent bounded exit havoc state
constrained by I and the negated condition. Body-path facts do not leak to the
exit state. Missing invariants fail closed before path walking.

Generated obligation kinds:

- contract consistency (satisfiability of requires clauses);
- external-contract fragment well-formedness;
- precondition at a call;
- postcondition at each reachable return;
- loop-invariant entry and inductive preservation;
- source assertion;
- division by zero;
- signed integer overflow;
- shift-count range and signed-left-shift definedness;
- reachable non-void fallthrough;
- unsupported logic/construct.

Obligations distinguish validity, satisfiability, and fragment-well-formedness
modes. Every signed i32/i64 parameter receives implicit type-minimum/type-maximum
bounds. Signed addition, subtraction, multiplication, and negation receive
range-safety obligations. Unsigned arithmetic wraps without overflow VCs.
Division/remainder always receives a divisor-nonzero obligation; signed forms
also receive the type-minimum/-1 obligation. Every shift count must be
nonnegative and below the promoted left width. Signed left shift additionally
requires a nonnegative left operand whose exact shifted value fits the
corresponding unsigned type; negative signed right shift uses the pinned
arithmetic profile.

Expression safety follows C++ short-circuit behavior. Definedness guards are
added to later path states, so a postcondition is not refuted by an execution
that already encountered signed overflow or division by zero.

This is important: for real signed i32/i64 C++, the contract `b != 0` alone
does not make signed division fully defined. The pair a = INT_MIN, b = -1 is another
counterexample.

### Checker

The checker seam is the CheckerBackend ABC. Three stable selections exist:

- affine: the dependency-free checker in semantic_verifier/checker.py;
- z3: deterministic SMT-LIB2 through an external Z3 process;
- both: affine/Z3 cross-check, which is the CLI default.

The affine backend validates the raw fragment before simplification, performs
exact deterministic case splitting for disjunctive join assumptions, substitutes
assignment equalities, normalizes affine comparisons with exact integer
arithmetic, proves matching path facts, and searches a deterministic finite set
for witnesses or counterexamples. Found models are real; exhausting the fixed
100,000-evaluation search set is never promoted to proof and returns unknown.

semantic_verifier/smtlib.py classifies each obligation before emission.
Signed-only formulas use sorted QF_LIA declarations and mathematical `Int`;
unsigned-tainted formulas and every bitwise/shift formula use homogeneous
QF_BV, with every fixed-width term encoded as a 32/64-bit vector. The BV lane
implements modulo arithmetic, variable multiplication/division/remainder,
signed/unsigned comparisons, complement/and/or/xor, logical/arithmetic shifts,
sign/zero extension, and truncation. Signed-result addition, subtraction, and
multiplication use an exact double-width overflow predicate before their wrapped
results become path facts. QF_LIA retains its literal multiplier and
literal divisor restrictions. No query mixes `Int` and `BitVec`; malformed
sorts, widths, casts, or expression kinds fail closed before Z3 starts.

The Z3 runner has deterministic discovery order, a configurable timeout,
fixed solver options, structured stdout/stderr handling, and explicit mappings
for sat/unsat/unknown/process failures. A sat validity result is only a candidate
violation until the complete parsed model replays against the original
obligation. Replay failure is a solver_error soundness alarm, never a violation.
After replay, both backends project the model to the conclusion's transitive
assumption-variable cone. They then greedily remove in-cone bindings in sorted
order only when exact reasoning proves the remaining core still forces the
negated conclusion.

Cross-check mode accepts the stronger definitive answer when the other backend
is unknown. It does not override `unsupported`: BV-required obligations require
explicit `--backend z3`. Definitive disagreement, backend process failure, or
replay failure becomes solver_error. No solver library or Python solver package
is linked; z3 and both modes require the separately installed Z3 executable.
Licensing,
packaging, timeout, and determinism decisions are recorded in
[the solver decision](solver_decision.md). The exponential sequential-diamond
baseline and exact structured-merge choice are recorded in
[the path-scaling decision](path_scaling_decision.md).

### Result taxonomy

- verified: validity was proved, or a satisfiability obligation has a concrete
  witness.
- violated: a complete internal assignment replayed and falsified a validity
  obligation, or exact reasoning proves a set of requirements infeasible.
- unknown: the supported validity/satisfiability question was not decided.
- unsupported: the source construct or formula is outside the declared subset.
- solver_error: the checker failed internally.

Unknown and unsupported are never converted to verified. JSON results contain
the obligation ID, function, kind, location, message, and sorted minimized
counterexample-core bindings when present. A public core may be empty and must
be interpreted with the referenced obligation assumptions. Violated results
also carry a source-ordered machine trace when their VC path crossed a branch;
human output renders each taken direction as a `when` explanation. The trace is
diagnostic and never changes the referee status. Non-goals are separate from
statuses: every loop records
loop_termination with the statement location and the partial-correctness scope,
including when Semantic IR is omitted from JSON.

The field-level contract is documented in [the result and Semantic IR schema
reference](result_schema.md). The frozen integer operation/capability matrix and
phase-gate commands are in [the integer operations runbook](integer_operations.md).

## Supported source subset

- free functions with owned `int`, `unsigned int`, `long long`, `unsigned
  long long`, or `bool` return types, plus supported value-record returns;
- named fixed-width integer and `bool` parameters;
- named public value structs with 1 to 16 supported fields, depth at most 8,
  full aggregate initialization, field reads/writes, copy, and by-value flow;
- initialized local fixed-width integer and `bool` variables;
- assignment to locals;
- unary plus, unary minus, boolean not, and bitwise complement;
- addition, subtraction, bitwise and/or/xor, and left/right shifts after
  integral promotions and usual conversions where applicable;
- literal multiplication in signed-only QF_LIA and general multiplication in
  unsigned-tainted QF_BV;
- signed/unsigned division and remainder safety; QF_LIA formulas require a
  literal divisor while QF_BV accepts variable divisors;
- equality, inequality, and ordered comparisons;
- side-effect-free boolean and/or;
- if/else;
- standalone direct function calls;
- direct matching fixed-width or value-record call results assigned to or
  initializing a local,
  with contracted postconditions assumed after a fresh result havoc;
- assert represented only by a declaration-only void assert(bool) sentinel;
- return;
- implicit return 0 when main falls through;
- inline requires and ensures contracts;
- while loops with a contiguous inline invariant block.

## Intentionally unsupported subset

The frontend explicitly rejects:

- while loops without a contiguous invariant block, invariant inference, do,
  for, range-for, switch, and goto;
- templates and namespaces;
- all preprocessor directives and macros as semantic nodes;
- exceptions and throw;
- pointers, references, classes/private state, record methods/constructors,
  inheritance, unions, bitfields, layout claims, and virtual calls;
- array decay/aliases, dynamic or multidimensional arrays, partial array
  initialization, allocation/release, pointer load/store, and heap semantics;
- globals, static/thread-local locals, and volatile values;
- uninitialized locals;
- shadowing;
- compound assignment, increment/decrement, comma, ternary, and assignment
  expressions;
- indirect/member calls, mismatched assigned results, and calls nested in return,
  arithmetic, or argument expressions;
- calls with neither a visible body nor a contract;
- direct and mutual recursive call cycles without a decreasing measure;
- implicit casts outside bool-to-fixed-width, owned fixed-width conversions,
  integral-to-bool, lvalue-to-rvalue, and no-op;
- `long`, `unsigned long`, `short`, `char`, and extended integers;
- variable multiplication and variable-divisor division/remainder in
  signed-only QF_LIA logical contracts;
- multiple translation units and sidecar contracts.

Unsupported input is not approximated.

## End-to-end demonstration

Input:

    // cs: requires b != 0
    // cs: requires !(a == -2147483648 && b == -1)
    int safe_divide(int a, int b) {
        return a / b;
    }

    int verified_call(int x) {
        safe_divide(x, 2);
        return 0;
    }

    int violating_call(int x, int input) {
        safe_divide(x, input);
        return 0;
    }

Representative IR:

    function safe_divide(a#0:int, b#0:int) -> int
      assume (b#0 != 0)
      assume (!((a#0 == -2147483648) && (b#0 == -1)))
      return (a#0 / b#0)

    function verified_call(x#0:int) -> int
      call safe_divide(x#0, 2)
      return 0

Representative obligations and outcomes:

    safe_divide:
      satisfiable(int32(a) && int32(b) && b != 0 && ...)
      status: verified

    safe_divide:
      assumptions -> b#0 != 0
      status: verified

    verified_call:
      int32(x#0) -> 2 != 0
      status: verified

    violating_call:
      int32(x#0) && int32(input#0) -> input#0 != 0
      status: violated
      counterexample: input = 0

The complete runnable input is examples/vertical_slice.cpp. Under the default
affine/Z3 cross-check it produces 10 verified obligations, two replayed
violations, and zero unknown/unsupported/solver_error results. The affine-only
backend deliberately remains unable to prove the transitive postcondition.
Modular-call and loop gates are in examples/modular_calls.cpp and
examples/sum_loop*.cpp.

## Build and test

Runtime requirements:

- Python 3.11 or newer;
- Clang with JSON AST output (tested with Clang 20.1.8);
- Z3 for the z3/both backends and committed fixture regeneration (tested with
  Z3 5.0.0).

There are no Python package dependencies. The affine backend remains fully
dependency-free; Z3 is a separately installed executable, not a linked library.

Commands:

    python -m semantic_verifier examples/vertical_slice.cpp --format text
    python -m semantic_verifier examples/vertical_slice.cpp --format json
    python -m semantic_verifier examples/vertical_slice.cpp --format ir
    python -m semantic_verifier examples/sum_loop.cpp --format text
    python tools/regenerate_fixtures.py --check
    python -m unittest discover -s tests -v

Reference validation used the environment-specific equivalents of:

    cmake -S C:\tmp\CodeSkeptic-reference -B .tmp\codeskeptic-build -DLLVM_DIR=<LLVM20>/lib/cmake/llvm -DClang_DIR=<LLVM20>/lib/cmake/clang
    cmake --build .tmp\codeskeptic-build --config Release --target codeskeptic_tests
    ctest --test-dir .tmp\codeskeptic-build -C Release --output-on-failure
    .\.tmp\codeskeptic-build\tests\Release\codeskeptic_tests.exe

Exit codes:

- 0: every produced obligation is verified;
- 1: at least one violation;
- 2: no violation, but at least one unknown or unsupported result;
- 3: solver/checker error.

The 155-test suite covers frontend boundaries, deterministic IR/SMT/report
serialization, contracts, branches/merges, modular calls, recursion rejection,
loop havoc and invariant VCs, C++ arithmetic safety, backend disagreement and
process failures, counterexample replay, fixture regeneration, and independent
two-process byte comparison. The test-count ratchet prevents accidental loss of
coverage. Five versioned fixture cases produce ten committed golden artifacts.

The unmodified CodeSkeptic reference was configured separately against LLVM
20.1.8. Its CTest run passed 811/811 tests, and the same 811 tests passed again
inside one direct test-binary process. The initial configure probe failed only
because LLVMConfig.cmake was not on the default CMake path; the explicit LLVM
and Clang package paths resolved it. GoogleTest 1.14 was cloned into an ignored
US temporary build area because the sandbox blocked CMake's nested network
fetch. CodeSkeptic's source worktree remained clean.

## Limitations

- Clang JSON is a convenient prototype transport, not the recommended
  production API. CodeSkeptic should lower directly from ASTContext.
- Verified results are sound only within the documented homogeneous QF_LIA/
  QF_BV formulas, pinned fixed-width conversions, and generated definedness
  obligations; broader C++ semantics remain outside the claim.
- Affine model search is finite. Found models are real, while exhaustion is
  unknown. Z3 is complete only for formulas accepted by the fail-closed emitter.
- Structured branch joins retain exact factored disjunctions, which bound the
  measured diamond obligations but can still grow with formula complexity. Loops
  are summarized by user-written invariants; termination is not checked.
- Modular calls are direct and contract-based. Only matching fixed-width results
  in a local initializer/assignment are modeled, and bodies are not inlined.
- Source columns identify the containing statement rather than the exact
  operator token.
- The prototype validates 32-bit `int`/`unsigned int` and 64-bit `long long`/
  `unsigned long long` under the pinned profile. Unsigned/mixed obligations
  require explicit Z3 mode; default cross-check remains intentionally
  `unsupported` for them.
- Overloads are separated by normalized parameter-type signatures, but a
  production integration should still use canonical Clang declaration identity
  and CodeSkeptic's existing attachment/sidecar machinery.
- Includes and all header semantics are explicitly unsupported in v0.
- The affine model-search cap is 100,000 deterministic evaluations. Each Z3
  process has a configurable timeout. The per-file budget counts supported
  top-level obligation checks, not internal affine evaluations or wall time.

## Technical assessment

### Does CodeSkeptic support this direction?

Yes, as an integration host. It already has the expensive and error-prone
frontend shell: compile databases, real Clang ASTs, CFGs, source locations,
contract attachment, deterministic reports, tests, and multiple output
surfaces.

No, not as an already-existing verifier. Its current dataflow domains are
purpose-built, Clang-coupled abstract interpretations. A new owned IR, logical
obligation model, result taxonomy, and checker are genuinely required.

### Is the prototype useful or merely demonstrative?

It is useful for fixing the architecture and output contracts:

- the IR is executable by tests and serializes deterministically;
- branches and mutable state become explicit;
- contracts generate path-specific obligations;
- real counterexamples are emitted;
- unknown and unsupported are distinguishable from proof.

It remains demonstrative as a C++ verifier because the frontend subset and
checker are deliberately narrow and the Clang JSON bridge is not a production
integration.

### Hardest obstacle

The hardest obstacle is faithful C++ lowering, not formula syntax or calling an
SMT solver. Integer width, signed overflow, implicit conversions, evaluation
order, short-circuit side effects, lvalues, memory, aliasing, object lifetime,
and undefined behavior must all be preserved or rejected explicitly.

The INT_MIN / -1 result already demonstrates this: a seemingly sufficient
non-zero-divisor contract is incomplete under actual C++ signed integer
semantics.

### Is Semantic IR the correct abstraction boundary?

Yes. It prevents every logic/checker component from learning Clang AST shapes
and makes deterministic serialization, testing, solver replacement, and
machine-readable counterexamples natural.

The node list alone is not enough. The IR contract also needs explicit types,
integer semantics, source provenance, evaluation order, unsupported reasons,
and eventually a memory model.

### Restricted SMT versus general FOL

Quantifier-free boolean logic plus linear integer arithmetic is the appropriate
first target. It is decidable, has mature model-producing solvers, and covers
the first useful contracts. General first-order logic would add proof search,
quantifier instantiation, and difficult unknown behavior before the frontend
semantics are trustworthy.

### What should be built next?

Build one native CodeSkeptic integration slice:

1. add an owned semantic module library with no reporter dependency;
2. lower only int/bool parameters, initialized locals, assignment, if/else,
   return, and direct calls from ASTContext;
3. adapt existing ParsedContracts for requires/ensures;
4. preserve the same JSON schema and result taxonomy;
5. run it through CodeSkeptic's in-memory Clang test harness;
6. compare the native IR/VC JSON byte-for-byte against fixtures derived from
   this prototype.

The Python reference has already accepted the external Z3/SMT-LIB2 design and
documents its license, Windows/macOS/Linux packaging, timeouts, deterministic
options, unknown handling, and model replay. The native slice should first match
fixture IR bytes; sharing or porting solver invocation comes only after that
semantic boundary is stable.

### What should not be built yet?

Do not add general FOL, pointer/heap verification, loop inference, templates,
concurrency, AI repair, or a broad annotation language. Do not make the
existing specialized DataflowEngine pretend to be a persistent Semantic IR.

## Recommended next milestone

Implement a native, test-only CodeSkeptic ASTContext-to-Semantic-IR adapter for
the first int/bool fixture subset and reuse the existing contract parser. Stop
when assignment, if/else merge, return, unsupported handling, and deterministic
IR JSON match the corresponding pinned Python fixtures. Do not add native solver
integration in that milestone. For a conservative staged rollout, follow
[the adoption guide](adoption_guide.md).
