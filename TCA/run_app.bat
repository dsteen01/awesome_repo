@echo off
:: Launch the TCA Streamlit app inside the uv virtual environment.
:: Uses "python -m streamlit" to guarantee the venv Python is used,
:: avoiding conflicts with any globally-installed Streamlit.
:: Works from any directory.

cd /d "%~dp0"
uv run python -m streamlit run frontend/app.py %*
