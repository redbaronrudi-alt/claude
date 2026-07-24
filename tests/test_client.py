import email
from email.message import EmailMessage as MimeEmailMessage
from unittest.mock import MagicMock, patch

import pytest

from icloud_email_connector import ICloudEmailConnector, ICloudEmailError


def _build_raw_email(subject="Hello", sender="a@example.com", to="b@example.com", body="Hi there"):
    msg = MimeEmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = "Fri, 24 Jul 2026 10:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


def test_missing_credentials_raises():
    with pytest.raises(ICloudEmailError):
        ICloudEmailConnector(email_address=None, app_password=None)


def test_connect_login_failure_wraps_error():
    connector = ICloudEmailConnector(email_address="a@icloud.com", app_password="secret")
    with patch("imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap = MagicMock()
        mock_imap.login.side_effect = Exception("bad creds")
        mock_imap_cls.return_value = mock_imap
        with pytest.raises(ICloudEmailError):
            connector.connect()


def test_fetch_messages_parses_email():
    connector = ICloudEmailConnector(email_address="a@icloud.com", app_password="secret")
    mock_imap = MagicMock()
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.search.return_value = ("OK", [b"1"])
    raw = _build_raw_email()
    mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822 {123}", raw)])
    connector._imap = mock_imap

    messages = connector.fetch_messages(folder="INBOX", limit=5)

    assert len(messages) == 1
    msg = messages[0]
    assert msg.subject == "Hello"
    assert msg.sender == "a@example.com"
    assert msg.to == "b@example.com"
    assert "Hi there" in msg.body


def test_send_message_uses_smtp():
    connector = ICloudEmailConnector(email_address="a@icloud.com", app_password="secret")
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        connector.send_message(to="b@example.com", subject="Test", body="Body text")
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("a@icloud.com", "secret")
        assert mock_smtp.send_message.called


def test_send_message_wraps_smtp_error():
    connector = ICloudEmailConnector(email_address="a@icloud.com", app_password="secret")
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = Exception("auth failed")
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        with pytest.raises(ICloudEmailError):
            connector.send_message(to="b@example.com", subject="Test", body="Body text")


def test_list_folders_parses_names():
    connector = ICloudEmailConnector(email_address="a@icloud.com", app_password="secret")
    mock_imap = MagicMock()
    mock_imap.list.return_value = (
        "OK",
        [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Messages"'],
    )
    connector._imap = mock_imap

    folders = connector.list_folders()

    assert "INBOX" in folders
    assert "Sent Messages" in folders
