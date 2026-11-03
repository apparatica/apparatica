"""Letters over SMTP (specs/09 §1): `APX_SMTP_URL`, an external provider in production, Mailpit in
development. A letter is plain text; a failure is logged and counted, the caller does not wait for
it (`apparatica_mail_letters{result="failed"}`).
"""

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol
from urllib.parse import unquote, urlsplit

import structlog
from prometheus_client import Counter

log = structlog.get_logger(__name__)

LETTERS = Counter(
    "apparatica_mail_letters", "Letters handed to SMTP by kind and result", ["kind", "result"]
)
# smtp: plain (a local relay, Mailpit); smtp+starttls: STARTTLS, required; smtps: TLS at once.
SCHEMES = {"smtp": 25, "smtp+starttls": 587, "smtps": 465}


@dataclass(frozen=True)
class Letter:
    kind: str  # for the logs and metrics, e.g. "login-link"
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    async def send(self, letter: Letter) -> bool:
        """Send a letter; False when it failed (logged)."""
        ...


@dataclass(frozen=True)
class SmtpServer:
    scheme: str
    host: str
    port: int
    username: str | None
    password: str | None

    @classmethod
    def parse(cls, url: str) -> "SmtpServer":
        parts = urlsplit(url)
        if parts.scheme not in SCHEMES or not parts.hostname:
            raise ValueError(f"APX_SMTP_URL must be {', '.join(SCHEMES)}://[user:password@]host")
        return cls(
            parts.scheme,
            parts.hostname,
            parts.port or SCHEMES[parts.scheme],
            unquote(parts.username) if parts.username else None,
            unquote(parts.password) if parts.password else None,
        )


class SmtpMailer:
    def __init__(self, url: str, sender: str, *, timeout_s: float) -> None:
        self.server = SmtpServer.parse(url)
        self._sender, self._timeout_s = sender, timeout_s

    async def send(self, letter: Letter) -> bool:
        try:
            await asyncio.to_thread(self._send, self._message(letter), letter.to)
        except (smtplib.SMTPException, OSError) as error:
            log.warning("letter not sent", kind=letter.kind, error=repr(error))
            LETTERS.labels(letter.kind, "failed").inc()
            return False
        log.info("letter sent", kind=letter.kind)
        LETTERS.labels(letter.kind, "sent").inc()
        return True

    def _message(self, letter: Letter) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = letter.to
        message["Subject"] = letter.subject
        message["Message-ID"] = make_msgid()
        message.set_content(letter.body)
        return message

    def _send(self, message: EmailMessage, to: str) -> None:
        server, context = self.server, ssl.create_default_context()
        client: smtplib.SMTP
        if server.scheme == "smtps":
            client = smtplib.SMTP_SSL(
                server.host, server.port, timeout=self._timeout_s, context=context
            )
        else:
            client = smtplib.SMTP(server.host, server.port, timeout=self._timeout_s)
        with client:
            if server.scheme == "smtp+starttls":
                client.starttls(context=context)
            if server.username is not None:
                client.login(server.username, server.password or "")
            # One recipient whatever the To header parses into: an address may hold a comma.
            client.send_message(message, to_addrs=[to])
