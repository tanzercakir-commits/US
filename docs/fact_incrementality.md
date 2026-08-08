# Incremental fact extraction

Status: implemented in D4.1.

The incremental layer is an execution optimization around the D1 fact
extractor. It never joins translation units and never changes a fact's trust.

## Input contract

A codeskeptic.translation-units/v1 document declares one or more units:

    {
      "schema": "codeskeptic.translation-units/v1",
      "units": [
        {
          "display_path": "project/src/example.cpp",
          "source": "src/example.cpp"
        }
      ]
    }

source is resolved beneath the caller-supplied workspace. source and
display_path must be normalized, relative POSIX paths. Absolute paths, drive
paths, backslashes, empty segments, dot segments, duplicate sources, duplicate
display paths, unknown fields, duplicate JSON keys, and invalid UTF-8 fail
closed.

The display path is the stable path embedded in the fact index. Relocating the
workspace therefore does not change cache keys or output bytes.

## Cache contract

current.json is a canonical codeskeptic.fact-cache-manifest/v1 document. Each
entry records:

- the declared source and display path;
- the SHA-256 hash of the exact UTF-8 source bytes;
- a cache key over the source hash, display path, fact schema, and extractor
  contract;
- the canonical relative index path and validated FactIndex identity.

The manifest has its own content identity and repeats the frozen fact schema
and extractor contract. It contains no absolute path, time, duration, random
value, compiler process detail, or stale unit.

A cache hit is accepted only when all of these checks succeed:

1. current.json is strict, canonical UTF-8 JSON with a valid content identity;
2. the source's newly computed cache key equals the declared entry key;
3. the entry key and index path match their canonical derivation;
4. the cached fact index is strict canonical JSON with a valid graph identity;
5. its display path, source hash, and index identity equal the cache entry.

Any corruption or mismatch in a would-be hit is an error, not a cache miss.
Changed and newly added units invoke the existing D1 Clang extractor exactly
once. Index files and current.json are written through deterministic temporary
paths and atomic replacement. current.json is replaced only after every
required extraction succeeds, so an extractor failure preserves the prior
current state. Content-addressed orphan files may remain after a failed run;
garbage collection is deliberately outside D4.

Removed units disappear from the new current manifest. Per-TU fact indexes
remain separate. There is no include scan, compile_commands ingestion,
cross-TU symbol merge, concurrency, semantic inference, or proof promotion.

## CLI

Update a cache:

    python tools/extract_facts_incremental.py translation-units.json \
      --workspace project-root --cache-dir .codeskeptic/fact-cache

Check without invoking Clang or writing:

    python tools/extract_facts_incremental.py translation-units.json \
      --workspace project-root --cache-dir .codeskeptic/fact-cache --check

The canonical codeskeptic.fact-cache-run/v1 response lists added, extracted,
removed, and reused source paths.

Exit codes:

- 0: update succeeded, or check found the cache current;
- 1: check found changed, added, removed, or uncached units;
- 2: input, cache, filesystem, frontend, or extraction error.

The frozen fixture under fixtures/fact_incremental contains two real C++17
translation units, cold and warm run reports, the canonical current manifest,
and both cached fact indexes.
