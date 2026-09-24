# Request 0 — Initial implementation

Implement the supplied ReportBuilder specification in Python 3.11 using only
the standard library. Keep the solution small. Do not modify the supplied
specification.

## Required public trial API

Create a package named `report_builder` with these public names:

- `report_builder.ui.UI`
- `report_builder.service.ReportService`
- `report_builder.data.DataReader`
- `report_builder.render.Renderer`
- `report_builder.results.ReadFailure`
- `report_builder.results.EmptyReport`

Required callable shape:

- `ReportService(reader, renderer)` accepts injected reader and renderer objects.
- `ReportService.build_report(query)` performs one report request.
- `UI(service)` accepts a ReportService-like object.
- `UI.build_report(query)` delegates a report request through the service.
- The injected reader exposes `read(query)`, returns a sequence of mapping-like
  source rows, and signals a read failure by raising `OSError`.
- The injected renderer exposes `render(rows)` and returns an opaque report
  value.
- Failure and empty outcomes are represented by instances of `ReadFailure` and
  `EmptyReport` respectively.

No other internal file layout, algorithm, or data structure is prescribed.
