# Launch the TCA Streamlit app inside the uv virtual environment.
# Uses "python -m streamlit" to guarantee the venv Python is used,
# avoiding conflicts with any globally-installed Streamlit.
# Works from any directory.

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
uv run --directory $ProjectRoot python -m streamlit run frontend/app.py @args
