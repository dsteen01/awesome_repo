"""
delivery/email.py - PDF report delivery via SMTP.

SMTP credentials are read exclusively from environment variables so they
never appear in source code or committed config files.  Copy .env.example
to .env (which is .gitignore'd), fill in your values, and load it with
python-dotenv or your shell before running.

Required environment variables
-------------------------------
    SMTP_HOST       Hostname of your SMTP server   e.g. smtp.gmail.com
    SMTP_USER       Login username / sender email  e.g. reports@firm.com
    SMTP_PASSWORD   Login password or app token

Optional environment variables
-------------------------------
    SMTP_PORT       Port number          default: 587  (use 465 for SSL)
    EMAIL_FROM      Sender display name  default: same as SMTP_USER

Gmail users
-----------
If the account has 2-Step Verification enabled, generate an App Password at
https://myaccount.google.com/apppasswords and use that as SMTP_PASSWORD.

Basic usage
-----------
    from config import ReportConfig
    from delivery import send_report, EmailConfig
    from pipeline import run_report

    cfg      = ReportConfig(recipients=['alice@firm.com', 'bob@firm.com'])
    pdf_path = run_report(cfg)
    send_report(pdf_path, cfg, sd='2025-01-01', ed='2025-05-28')
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import smtplib
import ssl
import sys
import textwrap
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import ReportConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email body template
# ---------------------------------------------------------------------------

_BODY_TEMPLATE = """\
Please find the {client_name} TCA Report attached.

  Date range : {start_date} – {end_date}
  Generated  : {generated_at}

This is an automated report. Please do not reply to this email.
"""


# ---------------------------------------------------------------------------
# EmailConfig
# ---------------------------------------------------------------------------

@dataclass
class EmailConfig:
    """SMTP connection and sender parameters.

    Prefer ``EmailConfig.from_env()`` over constructing this directly so
    credentials stay out of source code.

    Attributes:
        smtp_host:  SMTP server hostname.
        smtp_port:  Port number. 465 uses SSL; everything else uses STARTTLS.
        username:   Login username (usually the sender email address).
        password:   Login password or app-specific token.
        sender:     The From address shown to recipients.
                    Defaults to *username* when left blank.
    """

    smtp_host: str
    smtp_port: int = 587
    username:  str = ''
    password:  str = ''
    sender:    str = ''

    def __post_init__(self) -> None:
        if not self.sender:
            self.sender = self.username

    @classmethod
    def from_env(cls) -> EmailConfig:
        """Build an EmailConfig by reading environment variables.

        Raises:
            EnvironmentError: If ``SMTP_HOST`` or ``SMTP_USER`` is not set.
        """
        host = os.environ.get('SMTP_HOST', '').strip()
        user = os.environ.get('SMTP_USER', '').strip()

        missing = [name for name, val in [('SMTP_HOST', host), ('SMTP_USER', user)] if not val]
        if missing:
            raise EnvironmentError(
                f"Required environment variable(s) not set: {', '.join(missing)}.\n"
                "See delivery/email.py for the full list of expected variables."
            )

        return cls(
            smtp_host=host,
            smtp_port=int(os.environ.get('SMTP_PORT', 587)),
            username=user,
            password=os.environ.get('SMTP_PASSWORD', ''),
            sender=os.environ.get('EMAIL_FROM', user),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _open_smtp(email_cfg: EmailConfig) -> smtplib.SMTP:
    """Open, upgrade, and authenticate an SMTP connection.

    Port 465  → SSL wrapper  (``smtplib.SMTP_SSL``)
    All other → STARTTLS     (``smtplib.SMTP`` + ``starttls()``)

    The returned object is a context manager; use it with ``with`` so the
    connection is always cleanly closed even if sending raises.

    Raises:
        smtplib.SMTPException: On any connection or authentication failure.
    """
    context = ssl.create_default_context()

    if email_cfg.smtp_port == 465:
        logger.debug(
            "Connecting via SSL to %s:%d", email_cfg.smtp_host, email_cfg.smtp_port
        )
        conn: smtplib.SMTP = smtplib.SMTP_SSL(
            email_cfg.smtp_host, email_cfg.smtp_port, context=context
        )
    else:
        logger.debug(
            "Connecting via STARTTLS to %s:%d", email_cfg.smtp_host, email_cfg.smtp_port
        )
        conn = smtplib.SMTP(email_cfg.smtp_host, email_cfg.smtp_port)
        conn.ehlo()
        conn.starttls(context=context)
        conn.ehlo()

    if email_cfg.username and email_cfg.password:
        conn.login(email_cfg.username, email_cfg.password)
    elif not email_cfg.password:
        logger.warning(
            "SMTP_PASSWORD is not set - attempting unauthenticated relay. "
            "This will fail on most external mail servers."
        )

    return conn


def _build_message(
    pdf_path:  Path,
    config:    ReportConfig,
    email_cfg: EmailConfig,
    sd:        str,
    ed:        str,
) -> MIMEMultipart:
    """Assemble a MIME message with a plain-text body and a PDF attachment."""

    subject = f'[TCA Report] {config.client_name}'
    if sd and ed:
        subject += f' | {sd} – {ed}'

    body = _BODY_TEMPLATE.format(
        client_name=config.client_name,
        start_date=sd or 'N/A',
        end_date=ed   or 'N/A',
        generated_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    )

    msg = MIMEMultipart()
    msg['From']    = email_cfg.sender
    msg['To']      = ', '.join(config.recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with open(pdf_path, 'rb') as fh:
        attachment = MIMEApplication(fh.read(), _subtype='pdf')
    attachment.add_header(
        'Content-Disposition', 'attachment', filename=pdf_path.name
    )
    msg.attach(attachment)

    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_report(
    pdf_path:  Path | str,
    config:    ReportConfig,
    email_cfg: EmailConfig | None = None,
    *,
    sd: str = '',
    ed: str = '',
) -> None:
    """Email *pdf_path* to every address in *config.recipients*.

    Designed to be called immediately after ``pipeline.run_report()``::

        pdf = run_report(cfg)
        send_report(pdf, cfg, sd='2025-01-01', ed='2025-05-28')

    Args:
        pdf_path:   Path to the rendered PDF.
        config:     The same ReportConfig used to generate the report.
                    ``config.recipients`` determines who receives the email.
        email_cfg:  SMTP settings.  If *None*, loaded automatically from
                    environment variables via ``EmailConfig.from_env()``.
        sd:         Report start date string shown in the subject line and
                    email body (e.g. ``'2025-01-01'``).
        ed:         Report end date string (e.g. ``'2025-05-28'``).

    Raises:
        FileNotFoundError:        If *pdf_path* does not exist.
        EnvironmentError:         If *email_cfg* is None and required env
                                  variables are missing.
        smtplib.SMTPAuthenticationError: If credentials are rejected.
        smtplib.SMTPException:    On any other SMTP-level failure.
    """
    # ---- Guard: nothing to do if no recipients -------------------------
    if not config.recipients:
        logger.warning(
            "send_report() called for '%s' but config.recipients is empty - "
            "skipping delivery.",
            config.client_name,
        )
        return

    # ---- Validate PDF exists before touching the network ---------------
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path.resolve()}")

    # ---- Load email settings from env if not supplied ------------------
    if email_cfg is None:
        email_cfg = EmailConfig.from_env()

    # ---- Build message -------------------------------------------------
    msg = _build_message(pdf_path, config, email_cfg, sd, ed)

    logger.info(
        "Sending '%s' to %d recipient(s): %s",
        pdf_path.name,
        len(config.recipients),
        config.recipients,
    )

    # ---- Send ----------------------------------------------------------
    try:
        with _open_smtp(email_cfg) as conn:
            conn.sendmail(email_cfg.sender, config.recipients, msg.as_string())

    except smtplib.SMTPAuthenticationError as exc:
        # Re-raise with a friendlier message; never echo the password
        raise smtplib.SMTPAuthenticationError(
            exc.smtp_code,
            f"SMTP authentication failed for user '{email_cfg.username}'. "
            "Check the SMTP_USER and SMTP_PASSWORD environment variables.",
        ) from exc

    except smtplib.SMTPException:
        logger.exception("SMTP error while sending report for '%s'", config.client_name)
        raise

    logger.info("Report delivered successfully to %s", config.recipients)


# ---------------------------------------------------------------------------
# SMTP verification (CLI + importable)
# ---------------------------------------------------------------------------

#: Variables checked in order during verification.  Tuple: (name, required).
_SMTP_VARS: list[tuple[str, bool]] = [
    ('SMTP_HOST',     True),
    ('SMTP_PORT',     False),
    ('SMTP_USER',     True),
    ('SMTP_PASSWORD', True),
    ('EMAIL_FROM',    False),
]

_OK   = '[OK]  '
_FAIL = '[FAIL]'
_WARN = '[WARN]'


def verify_smtp(
    env_file: str | Path = '.env',
    send_test_to: str = '',
) -> bool:
    """Check SMTP environment variables and probe a live server connection.

    Runs four steps and prints a human-readable checklist for each:

    1. Load the ``.env`` file (if present and python-dotenv is installed)
    2. Confirm every required variable is set
    3. Open a real SMTP connection and authenticate (NOOP - no email sent)
    4. *Optionally* send a minimal test email to *send_test_to*

    Args:
        env_file:     Path to the ``.env`` file.  Defaults to ``.env`` in
                      the current working directory.
        send_test_to: If non-empty, send a test email to this address as a
                      final end-to-end confirmation step.

    Returns:
        ``True`` if every check (including the optional send) passed.
        ``False`` if any required check failed.
    """
    passed = True

    # ── Step 1: load .env ────────────────────────────────────────────────────
    print('\n-- Environment --------------------------------------------------')
    try:
        from dotenv import load_dotenv
        if load_dotenv(env_file):
            print(f'  {_OK} Loaded {env_file}')
        else:
            print(f'  {_WARN} {env_file} not found - '
                  'reading from shell environment variables')
    except ImportError:
        print(f'  {_WARN} python-dotenv not installed - '
              'reading from shell environment variables')

    # ── Step 2: check each variable ──────────────────────────────────────────
    print()
    all_required_set = True
    for var, required in _SMTP_VARS:
        val = os.environ.get(var, '').strip()
        if val:
            # Never echo the password - show only that it is set
            display = '*** (set)' if 'PASSWORD' in var else val
            print(f'  {_OK} {var:<15} = {display}')
        elif required:
            print(f'  {_FAIL} {var:<15} = (not set - REQUIRED)')
            all_required_set = False
            passed = False
        else:
            defaults = {'SMTP_PORT': '587', 'EMAIL_FROM': 'same as SMTP_USER'}
            print(f'  {_WARN} {var:<15} = (not set - '
                  f'default: {defaults.get(var, "n/a")})')

    if not all_required_set:
        print('\n  Cannot continue: set the missing variables and re-run.')
        return False

    # ── Step 3: open connection and authenticate (NOOP) ──────────────────────
    print('\n-- SMTP Connection ----------------------------------------------')
    try:
        email_cfg = EmailConfig.from_env()
    except EnvironmentError as exc:
        print(f'  {_FAIL} Could not build EmailConfig: {exc}')
        return False

    protocol = 'SSL' if email_cfg.smtp_port == 465 else 'STARTTLS'
    print(f'  Connecting to {email_cfg.smtp_host}:{email_cfg.smtp_port} '
          f'({protocol}) ...')

    try:
        conn = _open_smtp(email_cfg)
    except smtplib.SMTPAuthenticationError:
        print(f'  {_FAIL} Connected but authentication failed.')
        print(f'       Check SMTP_USER ("{email_cfg.username}") '
              'and SMTP_PASSWORD.')
        return False
    except OSError as exc:
        print(f'  {_FAIL} Could not reach '
              f'{email_cfg.smtp_host}:{email_cfg.smtp_port}')
        print(f'       {exc}')
        return False
    except smtplib.SMTPException as exc:
        print(f'  {_FAIL} SMTP error: {exc}')
        return False

    try:
        code, _ = conn.noop()
        if code == 250:
            print(f'  {_OK} Connected and authenticated as {email_cfg.username}')
            print(f'  {_OK} NOOP → 250 (server is responding correctly)')
        else:
            print(f'  {_WARN} NOOP returned unexpected code {code}')
    finally:
        try:
            conn.quit()
        except Exception:
            pass   # ignore errors on cleanup

    # ── Step 4 (optional): send a real test email ─────────────────────────────
    if send_test_to:
        print(f'\n-- Test Email -> {send_test_to} {"-" * max(0, 44 - len(send_test_to))}')
        try:
            msg = MIMEMultipart()
            msg['From']    = email_cfg.sender
            msg['To']      = send_test_to
            msg['Subject'] = '[TCA] SMTP verification test'
            msg.attach(MIMEText(
                'This is a test email from the TCA report scheduler.\n\n'
                'If you received this, SMTP delivery is working correctly.\n',
                'plain',
            ))
            with _open_smtp(email_cfg) as conn:
                conn.sendmail(email_cfg.sender, [send_test_to], msg.as_string())
            print(f'  {_OK} Test email sent to {send_test_to}')
        except Exception as exc:
            print(f'  {_FAIL} Failed to send test email: {exc}')
            passed = False

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if passed:
        print(f'  {_OK} All checks passed -- email delivery is ready.\n')
    else:
        print(f'  {_FAIL} Some checks failed -- see above for details.\n')

    return passed


# ---------------------------------------------------------------------------
# CLI entry point  (python -m delivery.email)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='python -m delivery.email',
        description='Verify SMTP configuration and optionally send a test email.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples
            --------
              # Check vars and connection only (no email sent)
              python -m delivery.email

              # Also send a test email to confirm end-to-end delivery
              python -m delivery.email --to you@example.com

              # Use a specific .env file path
              python -m delivery.email --env /path/to/.env --to you@example.com
        """),
    )
    parser.add_argument(
        '--to',
        metavar='EMAIL',
        default='',
        help='Send a test email to this address (step 4).',
    )
    parser.add_argument(
        '--env',
        metavar='FILE',
        default='.env',
        help='Path to the .env file (default: .env in the current directory).',
    )
    args = parser.parse_args()

    success = verify_smtp(env_file=args.env, send_test_to=args.to)
    sys.exit(0 if success else 1)
