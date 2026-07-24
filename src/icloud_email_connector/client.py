"""IMAP/SMTP connector for iCloud Mail.

iCloud has no public OAuth API for third-party mail access, so this
connector authenticates with an Apple ID + app-specific password
(https://appleid.apple.com > Sign-In and Security > App-Specific Passwords)
over standard IMAP4 and SMTP.
"""

from __future__ import annotations

import email
import imaplib
import os
import smtplib
from dataclasses import dataclass, field
from email.header import decode_header
from email.message import EmailMessage as MimeEmailMessage
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import Iterable, Optional

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587


class ICloudEmailError(Exception):
    """Raised for connector-level failures (auth, connection, parsing)."""


@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    to: str
    date: Optional[datetime]
    body: str
    raw: bytes = field(repr=False)


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


class ICloudEmailConnector:
    """Read and send email on an iCloud Mail account via IMAP/SMTP.

    Credentials can be passed explicitly or read from the
    ICLOUD_EMAIL / ICLOUD_APP_PASSWORD environment variables. An
    app-specific password is required; the regular Apple ID password
    will not work.
    """

    def __init__(
        self,
        email_address: Optional[str] = None,
        app_password: Optional[str] = None,
        imap_host: str = IMAP_HOST,
        imap_port: int = IMAP_PORT,
        smtp_host: str = SMTP_HOST,
        smtp_port: int = SMTP_PORT,
    ) -> None:
        self.email_address = email_address or os.environ.get("ICLOUD_EMAIL")
        self.app_password = app_password or os.environ.get("ICLOUD_APP_PASSWORD")
        if not self.email_address or not self.app_password:
            raise ICloudEmailError(
                "Missing credentials: pass email_address/app_password or set "
                "ICLOUD_EMAIL / ICLOUD_APP_PASSWORD environment variables."
            )
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    # -- connection lifecycle -------------------------------------------------

    def connect(self) -> "ICloudEmailConnector":
        try:
            self._imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            self._imap.login(self.email_address, self.app_password)
        except Exception as exc:
            raise ICloudEmailError(f"Failed to connect/login to iCloud IMAP: {exc}") from exc
        return self

    def close(self) -> None:
        if self._imap is not None:
            try:
                self._imap.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
            self._imap = None

    def __enter__(self) -> "ICloudEmailConnector":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_connection(self) -> imaplib.IMAP4_SSL:
        if self._imap is None:
            raise ICloudEmailError("Not connected. Use 'with ICloudEmailConnector(...) as c:' or call connect().")
        return self._imap

    # -- reading ---------------------------------------------------------------

    def list_folders(self) -> list[str]:
        imap = self._require_connection()
        status, folders = imap.list()
        if status != "OK":
            raise ICloudEmailError(f"Failed to list folders: {status}")
        names = []
        for raw in folders:
            if not raw:
                continue
            decoded = raw.decode() if isinstance(raw, bytes) else raw
            name = decoded.split(' "/" ')[-1].strip().strip('"')
            names.append(name)
        return names

    def fetch_messages(
        self,
        folder: str = "INBOX",
        search_criteria: str = "ALL",
        limit: Optional[int] = 20,
    ) -> list[EmailMessage]:
        """Fetch messages from a folder, newest first.

        search_criteria uses IMAP SEARCH syntax, e.g. 'UNSEEN',
        'FROM "someone@example.com"', 'SINCE 01-Jan-2026'.
        """
        imap = self._require_connection()
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            raise ICloudEmailError(f"Failed to select folder '{folder}'")

        status, data = imap.search(None, search_criteria)
        if status != "OK":
            raise ICloudEmailError(f"IMAP search failed: {status}")

        uids = data[0].split()
        uids.reverse()
        if limit is not None:
            uids = uids[:limit]

        messages: list[EmailMessage] = []
        for uid in uids:
            status, msg_data = imap.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            parsed = email.message_from_bytes(raw)
            date_hdr = parsed.get("Date")
            try:
                date_val = parsedate_to_datetime(date_hdr) if date_hdr else None
            except (TypeError, ValueError):
                date_val = None
            messages.append(
                EmailMessage(
                    uid=uid.decode(),
                    subject=_decode(parsed.get("Subject")),
                    sender=_decode(parsed.get("From")),
                    to=_decode(parsed.get("To")),
                    date=date_val,
                    body=_extract_body(parsed),
                    raw=raw,
                )
            )
        return messages

    def get_message(self, uid: str, folder: str = "INBOX") -> Optional[EmailMessage]:
        messages = self.fetch_messages(folder=folder, search_criteria=f"UID {uid}", limit=1)
        return messages[0] if messages else None

    # -- sending -----------------------------------------------------------

    def send_message(
        self,
        to: str | Iterable[str],
        subject: str,
        body: str,
        cc: Optional[str | Iterable[str]] = None,
    ) -> None:
        recipients = [to] if isinstance(to, str) else list(to)
        cc_list = [] if cc is None else ([cc] if isinstance(cc, str) else list(cc))

        msg = MimeEmailMessage()
        msg["From"] = self.email_address
        msg["To"] = ", ".join(recipients)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
                smtp.starttls()
                smtp.login(self.email_address, self.app_password)
                smtp.send_message(msg, to_addrs=recipients + cc_list)
        except Exception as exc:
            raise ICloudEmailError(f"Failed to send message: {exc}") from exc
