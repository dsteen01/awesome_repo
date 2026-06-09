"""
frontend/app.py - Streamlit UI for on-demand TCA report generation.

Usage
-----
    streamlit run frontend/app.py

Two modes are available from the sidebar:

  Saved Config  -- pick any ReportConfig from configs/, with optional
                   parameter overrides (time bin, bins).  Fastest path
                   for standard reports.

  Custom Config -- upload any Excel/CSV file, select columns
                   interactively, and configure every parameter from
                   scratch.  Intended for one-off or exploratory runs.

After generation the main area shows a Download button and an optional
Email section (requires SMTP env vars -- run ``python -m delivery.email``
to verify the setup).
"""

from __future__ import annotations

import dataclasses
import io
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Project root on sys.path so all internal imports resolve ─────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import ReportConfig
from pipeline import ReportResult, run_report
from runner.scheduler import discover_configs

# Load .env from the project root so SMTP credentials are available
# regardless of which directory streamlit is launched from.
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / '.env')
except ImportError:
    pass

# ── Page config (must come before any other st call) ─────────────────────────

st.set_page_config(
    page_title='TCA Report Generator',
    page_icon=':bar_chart:',
    layout='wide',
)

# ── Session-state initialisation ─────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict = {
        'result':    None,   # ReportResult from the last successful run
        'cfg':       None,   # ReportConfig used for that run
        'pdf_bytes': None,   # raw PDF bytes for the download button
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Data helpers ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _load_saved_configs() -> dict[str, ReportConfig]:
    """Discover and cache configs from the configs/ directory."""
    found = discover_configs(_ROOT / 'configs')
    return {c.client_name: c for c in found}


@st.cache_data(show_spinner=False)
def _peek_columns(file_name: str, file_bytes: bytes) -> list[str]:
    """Read only the header row of an uploaded file (cached by content)."""
    buf = io.BytesIO(file_bytes)
    if file_name.lower().endswith('.csv'):
        df = pd.read_csv(buf, nrows=0)
    else:
        df = pd.read_excel(buf, nrows=0)
    return df.columns.tolist()


# ── Sidebar: Saved Config mode ───────────────────────────────────────────────

def _sidebar_saved() -> ReportConfig | None:
    """Let the user pick a pre-defined config with optional overrides."""
    saved = _load_saved_configs()
    if not saved:
        st.warning(
            'No configs found in configs/.  '
            'Add a ReportConfig file there and restart the app.'
        )
        return None

    name = st.selectbox('Report', list(saved.keys()))
    base = saved[name]

    # Show the key static fields for reference (read-only)
    st.caption(
        f'Input: `{base.input_file}`  |  '
        f'KPI: `{base.kpi}`  |  '
        f'Recipients: {len(base.recipients)}'
    )

    st.divider()
    st.markdown('**Overrides**')

    time_bin = st.selectbox(
        'Time bin',
        ['Daily', 'Weekly'],
        index=0 if base.time_bin == 'Daily' else 1,
        help='Granularity of the temporal CutBy charts.',
    )
    nbins = st.slider(
        'CutBy bins',
        min_value=3, max_value=10, value=base.nbins,
        help='Number of quantile bins for each CutBy panel.',
    )

    return dataclasses.replace(base, time_bin=time_bin, nbins=nbins)


# ── Sidebar: Custom Config mode ───────────────────────────────────────────────

def _sidebar_custom() -> ReportConfig | None:
    """Build a ReportConfig interactively from an uploaded file."""

    client_name = st.text_input('Client name', value='Custom Report')

    uploaded = st.file_uploader(
        'Data file',
        type=['xlsx', 'xls', 'csv'],
        help='Upload the trade-level data file to analyse.',
    )
    if uploaded is None:
        st.info('Upload a data file to configure columns.')
        return None

    file_bytes = uploaded.read()
    cols = _peek_columns(uploaded.name, file_bytes)

    if not cols:
        st.error('Could not read column names from the uploaded file.')
        return None

    st.divider()
    st.markdown('**Columns**')

    date_col = st.selectbox(
        'Date column',
        cols,
        help='Column containing the trade date.',
    )
    feature_cols = st.multiselect(
        'Feature columns',
        cols,
        default=cols[:min(6, len(cols))],
        help='Numeric columns used in the summary table and histograms.',
    )
    if not feature_cols:
        st.warning('Select at least one feature column.')
        return None

    kpi = st.selectbox(
        'KPI column',
        feature_cols,
        index=len(feature_cols) - 1,
        help='The key performance indicator (excluded from CutBy drivers).',
    )
    weight_col = st.selectbox(
        'Weight column',
        cols,
        help='Column used as analytic weight in TableOne (e.g. exec_val_usd).',
    )
    sum_cols = st.multiselect(
        'Sum columns',
        cols,
        help='Columns for which TableOne shows sums rather than means.',
    )

    grouping_opts = ['(none)'] + [c for c in cols if c not in (date_col, kpi)]
    grouping_label = st.selectbox(
        'Grouping column',
        grouping_opts,
        help='Optional column to split all analyses by (e.g. trader_id).',
    )
    grouping = None if grouping_label == '(none)' else grouping_label

    st.divider()
    st.markdown('**Analysis**')

    time_bin = st.selectbox('Time bin', ['Daily', 'Weekly'])
    nbins    = st.slider('CutBy bins', min_value=3, max_value=10, value=5)

    st.divider()
    st.markdown('**Output**')

    output_name   = st.text_input('PDF filename', value='custom_report.pdf')
    recipients_raw = st.text_area(
        'Email recipients (one per line)',
        placeholder='alice@firm.com\nbob@firm.com',
        height=80,
    )
    recipients = [r.strip() for r in recipients_raw.splitlines() if r.strip()]

    # Write uploaded bytes to a temp file so the pipeline can read it by path
    suffix = Path(uploaded.name).suffix or '.xlsx'
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(file_bytes)
    tmp.close()

    return ReportConfig(
        client_name=client_name,
        input_file=tmp.name,
        output_file=str(_ROOT / 'reports' / output_name),
        feature_cols=feature_cols,
        kpi=kpi,
        weight_col=[weight_col],
        sum_cols=sum_cols,
        sub_df_cols=[date_col, weight_col, kpi],
        date_col=date_col,
        grouping=grouping,
        time_bin=time_bin,
        nbins=nbins,
        recipients=recipients,
        # Custom uploads are assumed pre-scaled and pre-renamed
        scale_multiply={},
        scale_divide={},
        rename_map={},
    )


# ── Main area: report results ─────────────────────────────────────────────────

def _show_results() -> None:
    """Render the download button and optional email panel."""
    result: ReportResult   = st.session_state.result
    cfg:    ReportConfig   = st.session_state.cfg
    pdf_bytes: bytes       = st.session_state.pdf_bytes

    st.success(
        f'Report ready: **{cfg.client_name}** '
        f'| {result.start_date} to {result.end_date}'
    )

    dl_col, email_col = st.columns([1, 2], gap='large')

    # ── Download ──────────────────────────────────────────────────────────────
    with dl_col:
        st.subheader('Download')
        st.download_button(
            label='Download PDF',
            data=pdf_bytes,
            file_name=Path(cfg.output_file).name,
            mime='application/pdf',
            type='primary',
            use_container_width=True,
        )

    # ── Email ─────────────────────────────────────────────────────────────────
    with email_col:
        st.subheader('Email')

        # Editable recipient list — pre-populate from config, allow UI overrides
        default_recipients = '\n'.join(cfg.recipients) if cfg.recipients else ''
        recipients_input = st.text_area(
            'Recipients (one per line)',
            value=default_recipients,
            placeholder='alice@firm.com\nbob@firm.com',
            height=100,
            key='email_recipients_input',
        )
        recipients = [r.strip() for r in recipients_input.splitlines() if r.strip()]

        send_clicked = st.button(
            'Email Report',
            disabled=not recipients,
            use_container_width=True,
            help='Requires SMTP env vars — run `python -m delivery.email` to verify.',
        )

        if send_clicked and recipients:
            _send_email(
                result=result,
                cfg=dataclasses.replace(cfg, recipients=recipients),
            )

        if not recipients:
            st.caption(
                'Enter at least one recipient above to enable email delivery.'
            )


def _send_email(result: ReportResult, cfg: ReportConfig) -> None:
    """Attempt SMTP delivery and show success / error in the UI."""
    from delivery import EmailConfig, send_report

    try:
        email_cfg = EmailConfig.from_env()
    except EnvironmentError as exc:
        st.error(f'SMTP not configured: {exc}')
        st.info(
            'Fill in your SMTP credentials in `.env` then run  \n'
            '`python -m delivery.email`  \n'
            'to verify the setup.'
        )
        return

    with st.spinner(f'Sending to {", ".join(cfg.recipients)} ...'):
        try:
            send_report(
                result.pdf_path,
                cfg,
                email_cfg,
                sd=result.start_date,
                ed=result.end_date,
            )
            st.success(f'Delivered to: {", ".join(cfg.recipients)}')
        except Exception as exc:
            st.error(f'Email failed: {exc}')


# ── App entry point ───────────────────────────────────────────────────────────

def main() -> None:
    _init_state()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title('TCA Reports')
        mode = st.radio(
            'Mode',
            ['Saved Config', 'Custom Config'],
            help=(
                '**Saved Config** — run a pre-defined report from configs/.  \n'
                '**Custom Config** — upload a file and configure everything.'
            ),
        )

        st.divider()

        cfg: ReportConfig | None = None
        if mode == 'Saved Config':
            cfg = _sidebar_saved()
        else:
            cfg = _sidebar_custom()

        st.divider()

        generate = st.button(
            'Generate Report',
            type='primary',
            disabled=(cfg is None),
            use_container_width=True,
        )

    # ── Header ────────────────────────────────────────────────────────────────
    st.title('TCA Report Generator')

    # ── Generate ──────────────────────────────────────────────────────────────
    if generate and cfg is not None:
        # Ensure the output directory exists (especially for saved configs that
        # reference reports/xyz_strategy.pdf)
        Path(cfg.output_file).parent.mkdir(parents=True, exist_ok=True)

        with st.spinner(f'Generating report for **{cfg.client_name}** ...'):
            try:
                result = run_report(cfg)
                with open(result.pdf_path, 'rb') as fh:
                    pdf_bytes = fh.read()
                st.session_state.result    = result
                st.session_state.cfg       = cfg
                st.session_state.pdf_bytes = pdf_bytes
            except Exception as exc:
                st.error(f'Report generation failed: {exc}')
                st.exception(exc)

    # ── Results or welcome ────────────────────────────────────────────────────
    if st.session_state.result is not None:
        _show_results()
    else:
        # Landing state — show instructions when nothing has been generated yet
        st.info(
            'Configure a report in the sidebar, then click **Generate Report**.'
        )
        st.markdown(
            '''
            **Saved Config mode** runs any report defined in `configs/`
            with optional time-bin and bin-count overrides.

            **Custom Config mode** lets you upload any Excel or CSV file
            and configure every parameter interactively -- useful for
            one-off analyses without touching a config file.
            '''
        )
        st.divider()
        st.caption(
            'To set up email delivery, copy `.env.example` to `.env`, '
            'fill in your SMTP credentials, and run  \n'
            '`python -m delivery.email --to you@example.com`  \n'
            'to verify the connection.'
        )


if __name__ == '__main__':
    main()
