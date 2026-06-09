# TCA Report Generator — Project Guide

## Purpose

A **Transaction Cost Analysis (TCA) reporting system** that:

1. Ingests trade-level execution data from Excel files
2. Runs statistical analysis using TableOne (weighted means, sums, winsorized comparisons)
3. Builds CutBy sensitivity panels — feature vs. KPI across quantile bins and over time
4. Renders a multi-page landscape PDF report using ReportLab
5. Delivers the finished PDF to recipients via SMTP email
6. Supports both **on-demand generation** (Streamlit web UI) and **automated scheduled delivery** (APScheduler cron runner)

Reports are fully parameterised via `ReportConfig` dataclass instances — switching clients, strategies, or column mappings requires no code changes.

---

## Tech Stack

| Layer | Library | Version |
|---|---|---|
| Package manager | uv | — |
| Language | Python | ≥ 3.14 |
| Data wrangling | pandas | ≥ 3.0 |
| Numerical | numpy, scipy | ≥ 2.0, ≥ 1.17 |
| Summary statistics | TableOne | local copy (`tableone/`) |
| Visualisation | matplotlib, seaborn | ≥ 3.10, ≥ 0.13 |
| PDF generation | reportlab | ≥ 4.5 |
| Excel I/O | openpyxl | ≥ 3.1 |
| Web UI | streamlit | ≥ 1.58 |
| Scheduler | apscheduler | ≥ 3.10, < 4 |
| Environment vars | python-dotenv | ≥ 1.0 |
| Causal inference | dowhy, econml | ≥ 0.14, ≥ 0.16 — `.venv-causal` only (Python 3.11) |
| Graph / DAG | networkx | ≥ 3.6 |
| ML models | scikit-learn | ≥ 1.9 (main venv); 1.6.x in `.venv-causal` |

> **APScheduler is pinned to `<4`** — the v4 API is a breaking rewrite.

> **econml is NOT in `pyproject.toml`** — it conflicts with the project's
> `scikit-learn>=1.9.0` pin (econml 0.16.0 caps sklearn at `<1.7`), and no
> pre-built Python 3.14 wheels exist on Windows (building from source also
> requires a full Windows SDK that is not straightforward to configure).
> The causal-inference scripts (`causalinference/`) use a **separate Python 3.11
> venv** at `.venv-causal/` where pre-built econml wheels are available:
> ```powershell
> # One-time setup (already done — only needed on a new machine)
> winget install Python.Python.3.11
> uv venv --python 3.11 .venv-causal
> uv pip install econml dowhy networkx --python .venv-causal/Scripts/python.exe
> ```
> Point PyCharm at `.venv-causal/Scripts/python.exe` when running any script
> in `causalinference/`. The main TCA pipeline continues to use the uv venv
> (Python 3.14).

---

## Directory Structure

```
TCA/
├── CLAUDE.md                  ← this file
├── config.py                  ← ReportConfig dataclass (single source of truth)
├── pipeline.py                ← 4-stage report orchestrator
├── MyReportV2.py              ← thin CLI runner (runs default config)
├── pyproject.toml             ← dependencies managed by uv
├── uv.lock                    ← pinned lockfile
├── .env                       ← SMTP credentials (not committed — see .env.example)
├── .env.example               ← template for .env
├── run_app.bat                ← Windows batch launcher for Streamlit
├── run_app.ps1                ← PowerShell launcher for Streamlit
│
├── configs/                   ← per-report ReportConfig definitions
│   └── xyz_strategy.py        ← example: XYZ strategy, runs every Friday 5 PM
│
├── data/                      ← data ingestion and transformation
│   ├── loader.py              ← load_data(), _resolve_path()
│   ├── filters.py             ← CreateOutlierFrame() — winsorise / trim
│   ├── transforms.py          ← resolve_time_grouping() — Daily/Weekly pivot
│   └── simulator.py           ← synthetic trade-data generator (100 k rows, Hive-partitioned Parquet)
│
├── analysis/                  ← statistical analysis
│   ├── __init__.py            ← adds tableone/ to sys.path[0] (required)
│   ├── summary.py             ← CreateCoverPageTable() — TableOne Raw/Win
│   └── cutby.py               ← CreateCutBy() — feature sensitivity panels
│
├── viz/                       ← matplotlib/seaborn chart builders
│   ├── histograms.py          ← CreateFeatureHistograms() — FacetGrid
│   └── timeseries.py          ← CreateFeatureTS() — time-series error bars
│
├── report/                    ← ReportLab PDF assembly
│   ├── templates.py           ← MyDocTemplate, PageNumCanvas
│   ├── components.py          ← df2table(), fig2image()
│   └── builder.py             ← createMultiPage() — top-level doc.build()
│
├── delivery/                  ← email delivery
│   ├── __init__.py            ← lazy re-exports (avoids RuntimeWarning)
│   └── email.py               ← EmailConfig, send_report(), verify_smtp()
│
├── runner/                    ← automated scheduling
│   ├── __init__.py
│   └── scheduler.py           ← discover_configs(), build_scheduler(), main()
│
├── frontend/                  ← Streamlit web UI
│   └── app.py                 ← two modes: Saved Config and Custom Config
│
├── tableone/                  ← local fork of the TableOne library
├── reports/                   ← output directory for generated PDFs
├── toydata_v2.xlsx            ← sample input data
│
├── causal_research/           ← causal-inference research scripts
│   ├── causal_dag.py          ← explicit DAG (networkx) for config-selection analysis
│   ├── synth_data.py          ← shared synthetic execution dataset (DGP)
│   ├── demo_pywhy.py          ← DoWhy + EconML DRLearner demo (needs econml — see note)
│   ├── demo_dr.py             ← hand-rolled doubly-robust estimator demo
│   ├── demo_causalinference.py← uses `causalinference` pip package for matching/balance
│   ├── dr_config_selection.py ← DR-learner config-selection layer
│   └── covariate_balance.py   ← covariate balance diagnostics
│
└── propogator/                ← market-impact propagator calibration
    ├── propagator_calibration.py ← two-stage power-law kernel calibration
    └── test_calibration.py    ← synthetic round-trip validation test
```

### Backward-compatibility shims
`utils.py` and `reportlabutils.py` still exist at the project root as thin
re-exporters — they import from the new subpackages. Any legacy code that
imports from them continues to work; new code should import directly from
the subpackages.

---

## Running the Application

### Prerequisites
```
# Install uv (if not already installed)
pip install uv

# Install all dependencies into the project venv
uv sync
```

### 1 — Streamlit UI (recommended for ad-hoc use)

**From the project root:**
```powershell
# PowerShell
.\run_app.ps1

# Command Prompt
run_app.bat

# Or directly:
uv run python -m streamlit run frontend/app.py
```

> **Important:** Always use `uv run python -m streamlit`, not `uv run streamlit`.
> On Windows the latter may invoke a globally-installed Streamlit that lacks
> the project's venv dependencies (e.g. reportlab).

The UI offers two modes (selected from the sidebar):

| Mode | Description |
|---|---|
| **Saved Config** | Pick any config from `configs/`, optionally override time-bin and bin count |
| **Custom Config** | Upload any Excel/CSV, select columns interactively, generate a one-off report |

After generation, a **Download PDF** button appears alongside an optional
**Email** panel that sends to any address you type (SMTP must be configured).

### 2 — CLI one-shot run
```
uv run python MyReportV2.py
```
Runs the default `ReportConfig()` and writes the PDF to `TestFile.pdf`.

### 3 — Automated scheduler
```
uv run python -m runner.scheduler
```
Scans `configs/` for every config with a non-empty `schedule` field, registers
cron jobs (APScheduler), and blocks until interrupted with `Ctrl+C`.  On each
trigger it runs the pipeline and emails the PDF to `config.recipients`.

To keep it running continuously, wrap it with Windows Task Scheduler, systemd,
or supervisord.

---

## Adding a New Report

1. Create a file in `configs/`:

```python
# configs/my_strategy.py
from config import ReportConfig

config = ReportConfig(
    client_name='My Strategy Report',
    input_file='my_data.xlsx',
    output_file='reports/my_strategy.pdf',
    recipients=['trader@firm.com', 'pm@firm.com'],
    schedule='0 8 * * mon',   # every Monday at 8 AM Eastern
    # Override any other ReportConfig field as needed
)
```

2. The scheduler and Streamlit UI pick it up automatically — no code changes needed.

### Key ReportConfig fields

| Field | Description |
|---|---|
| `input_file` | Path to the source Excel file (relative to project root or absolute) |
| `output_file` | Destination PDF path |
| `feature_cols` | Columns included in the summary table and histograms |
| `kpi` | Key performance indicator column (excluded from CutBy drivers) |
| `weight_col` | Analytic weight column(s) for TableOne |
| `sum_cols` | Columns shown as sums rather than means in the summary table |
| `sub_df_cols` | Base columns always included in CutBy sub-frames |
| `grouping` | Optional column to split all analyses by (e.g. `'trader_id'`) |
| `date_col` | Name of the trade date column (post-rename) |
| `date_format` | `strptime` format for date parsing; `''` = let pandas infer |
| `time_bin` | `'Daily'` or `'Weekly'` for temporal charts |
| `nbins` | Number of quantile bins in CutBy panels (default 5) |
| `scale_multiply` | `{col: factor}` — applied before column rename |
| `scale_divide` | `{col: factor}` — applied before column rename |
| `rename_map` | `{raw_name: display_name}` — applied after scaling |
| `recipients` | List of email addresses (leave empty for no delivery) |
| `schedule` | Cron expression (leave empty for ad-hoc / Streamlit-only) |

---

## Email Delivery Setup

1. Copy the template:
   ```
   copy .env.example .env
   ```

2. Fill in your SMTP credentials in `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=reports@firm.com
   SMTP_PASSWORD=your-app-password
   EMAIL_FROM=TCA Reports <reports@firm.com>
   ```
   For Gmail with 2-Step Verification, generate an **App Password** at
   https://myaccount.google.com/apppasswords.

3. Verify the setup (connection test, no email sent):
   ```
   uv run python -m delivery.email
   ```

4. Send a live test email:
   ```
   uv run python -m delivery.email --to you@example.com
   ```

> `.env` is not committed to source control. Never put credentials in a
> config file or source code.

---

## Pipeline Architecture

The pipeline in `pipeline.py` is split into four explicit stages:

```
Stage 1  load_data()          Read Excel → scale → rename → validate
Stage 2  build_components()   Run analysis → return ReportLab flowables
Stage 3  assemble_elements()  Order flowables for cover + CutBy pages
Stage 4  run_report()         Orchestrate stages → write PDF → return ReportResult
```

`run_report()` returns a `ReportResult` NamedTuple:
```python
result.pdf_path    # Path to the written PDF
result.start_date  # 'YYYY-MM-DD' — first trade date in the data
result.end_date    # 'YYYY-MM-DD' — last trade date in the data
```

Stages 1–3 can be called independently for testing or to inspect intermediate
results without writing a PDF.

### PDF page layout

| Page | Content |
|---|---|
| Page 1 | Cover: Raw/Winsorized summary table (left) + feature histogram grid (right) |
| Page 2+ | CutBy panels: two per page (top frame / bottom frame), one per driver feature |

---

## Known Issues / Notes

- **TableOne local copy:** The project embeds a local fork of TableOne at
  `tableone/`. The `analysis/__init__.py` inserts `tableone/` at `sys.path[0]`
  so that `import tableone` resolves to `tableone/tableone/` (the actual
  package), not `tableone/__init__.py` (the repo wrapper). Do not remove this
  path insertion.

- **TableOne RuntimeWarning:** `invalid value encountered in scalar divide`
  is emitted by TableOne's weighted-variance function when a quantile bin
  contains all-zero weights. This is pre-existing behaviour from the library
  and does not affect output correctness.

- **Streamlit must be launched via `uv run python -m streamlit`** (not
  `uv run streamlit`) to guarantee the venv Python is used on Windows. The
  batch/PowerShell launchers handle this automatically.

- **`data/simulator.py`** generates 100,000 synthetic trades (2025-09-01 to
  2026-03-31, business days only) and writes them as Hive-partitioned Parquet
  under `data/year=YYYY/month=MM/`.  Run with::

      uv run python -m data.simulator

  All 29 columns follow the schema defined in ``DataSchema.xlsx``, including
  derived fields (``exec_qty``, ``exec_val_usd``, ``end_time``,
  ``min_since_open``, ``int_spread``, ``arrival_mid_px_slp_bps``).
  Parquet types are enforced via an explicit PyArrow schema (``date32``,
  ``timestamp[us]``, ``int32``, ``float64``, ``string``).
