# ReportBuilder specification

## Purpose

- **[F01]** The system must produce reports from source records without
  modifying the source data.

## Architecture

- **[F02]** The UI may directly depend on and call `ReportService`.
- **[F03]** `ReportService` may directly depend on and call `DataReader`.
- **[F04]** The UI must not directly depend on or call `DataReader`.
- **[F05]** `ReportService` may directly depend on and call `Renderer`.

## Required rules

- **[F06]** Source records must remain immutable.
- **[F07]** The implementation must not perform network access.
- **[F08]** A read failure and an empty report are distinct observable outcomes:
  `ReadFailure` must not be collapsed into `EmptyReport`.

## Deliberately delegated choices

- **[F09]** The implementation may choose its internal data structures.
- **[F10]** The implementation may choose cache mechanics except for the cache
  eviction policy, subject to every other requirement in this specification.

## Required behavior

- **[F11]** If `DataReader` fails to read, return the `ReadFailure` outcome.
- **[F12]** If `DataReader` succeeds and returns zero rows, return the
  `EmptyReport` outcome.
- **[F13]** If `DataReader` succeeds with non-empty rows, return the
  `Renderer` output for those rows.

## Open decision

- **[F14]** The cache eviction policy is intentionally unresolved. The
  implementation must not silently choose a default policy. If a cache feature
  depends on eviction behavior, it must require an explicit external policy or
  explicitly expose/fail the unresolved decision.
