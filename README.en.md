# excel-to-sql

[中文](README.md) | English

A standalone desktop tool (macOS / Windows) that imports Excel/CSV files into an SQLite database with built-in data browsing and conditional search. Design document: [plan.md](plan.md) (Chinese).

## Features

- **Multi-file / multi-sheet batch import** — check the sheets you want; empty sheets and blank rows are skipped automatically
- **Automatic type inference**: INTEGER / REAL / TEXT / dates (ISO8601); column names and types can be edited per column before importing. Integers beyond 2^53 (e.g. long IDs) are kept as TEXT to avoid precision loss
- **Conditional search**: equals / not-equals / contains / not-contains / partial match (`*` = any characters, `?` = single character). Chinese text works out of the box. Each condition accepts multiple comma-separated values (equals/contains/match = any-of; not-equals/not-contains = exclude-all), and multiple condition rows combine with AND / OR. Each search opens in its own result tab
- **Catalog tree & scope search**: a two-level catalog "workbook (Excel file) ▸ sheet" on the left; check sheets — across workbooks — to define the search scope. Forward search (checked scope) or inverse search (unchecked scope). Cross-table searches pre-validate that all sheets in scope share an identical header structure (column names + types); if not, the search is refused with a diff. Scope results are summarized per sheet (hit counts) with a linked detail view. Move a sheet to another workbook by drag & drop or context menu; rename workbooks — catalog changes never touch your data
- **Tabs**: at most 3 tabs visible at a time; overflow scrolls via the built-in left/right arrows
- Export results to Excel / CSV (UTF-8 with BOM — opens correctly in Excel on both platforms)
- Same-name table strategies: replace / rename / append; GBK-encoded CSVs are detected automatically
- Import and sample loading run in background threads with `lxml` acceleration — the UI never freezes

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# GUI (import wizard + browsing & search)
python main.py

# Command line (automation / testing)
python scripts/make_samples.py                                 # generate sample Excel
python cli.py convert samples/订单示例.xlsx -o output/demo.db   # import
python cli.py tables -d output/demo.db                         # list tables
python cli.py search -d output/demo.db -t 订单表 --where 商品名称~手机
python cli.py export -d output/demo.db -t 订单表 -o output/订单表.xlsx
```

CLI condition syntax: `col=value` (equals), `col!=value` (not equals), `col~value` (contains), `col!~value` (not contains), `col@pattern` (partial match with `*`/`?` wildcards). Quote patterns containing `*` so your shell does not expand them. Multiple values may be comma-separated.

## Tests

```bash
python -m pytest tests/ -q                              # unit + integration (55 tests)
QT_QPA_PLATFORM=offscreen python scripts/smoke_gui.py   # offscreen GUI smoke test
```

## Project Layout

```
app/core/     Core engine: excel_reader / type_inference / schema_builder /
              sqlite_writer / query_builder / db_browser / library (catalog).
              UI-independent and unit-testable.
app/models/   TableMeta / ColumnMeta
app/ui/       Main window (catalog + search), three-step import wizard,
              shared widgets (catalog tree, data table, scope results)
cli.py        CLI entry point; main.py GUI entry point
tests/        pytest suite; scripts/ sample generation, GUI smoke, screenshots
```
