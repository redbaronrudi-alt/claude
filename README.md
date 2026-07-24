# iCloud Email Connector

Ein leichtgewichtiger Python-Connector für den Zugriff auf iCloud Mail
(`@icloud.com`, `@me.com`, `@mac.com`) über IMAP (lesen) und SMTP (senden).

iCloud stellt für E-Mail keine öffentliche OAuth-API für Drittanbieter
bereit. Der unterstützte Weg ist der klassische IMAP/SMTP-Zugriff mit
einem **App-spezifischen Passwort**.

## Voraussetzungen

1. Zwei-Faktor-Authentifizierung für die Apple-ID aktivieren (Pflicht).
2. App-spezifisches Passwort erstellen: https://appleid.apple.com →
   "Anmelden und Sicherheit" → "App-spezifische Passwörter" → "Passwort
   erstellen".
3. Das erzeugte Passwort (Format `xxxx-xxxx-xxxx-xxxx`) zusammen mit der
   iCloud-Adresse als Zugangsdaten verwenden — **nicht** das normale
   Apple-ID-Passwort.

## Installation

```bash
pip install -e .
```

Es werden ausschließlich Python-Bordmittel (`imaplib`, `smtplib`, `email`)
verwendet, es gibt keine externen Abhängigkeiten.

## Konfiguration

Zugangsdaten entweder per Umgebungsvariablen setzen (siehe `.env.example`):

```bash
export ICLOUD_EMAIL="deine-adresse@icloud.com"
export ICLOUD_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

oder direkt beim Erstellen des Connectors übergeben.

## Nutzung als Bibliothek

```python
from icloud_email_connector import ICloudEmailConnector

with ICloudEmailConnector() as connector:
    # Ordner auflisten
    print(connector.list_folders())

    # Neueste 10 Nachrichten aus dem Posteingang lesen
    for msg in connector.fetch_messages(folder="INBOX", limit=10):
        print(msg.date, msg.sender, msg.subject)

    # Nur ungelesene Nachrichten
    unread = connector.fetch_messages(search_criteria="UNSEEN")

    # E-Mail senden
    connector.send_message(
        to="empfaenger@example.com",
        subject="Hallo",
        body="Das ist eine Testnachricht.",
    )
```

`search_criteria` folgt der IMAP-SEARCH-Syntax, z. B. `'FROM "chef@example.com"'`
oder `'SINCE 01-Jan-2026'`.

## CLI

```bash
python -m icloud_email_connector list-folders
python -m icloud_email_connector fetch --folder INBOX --limit 5
python -m icloud_email_connector send --to x@example.com --subject "Hi" --body "Hallo!"
```

## Server-Einstellungen (Referenz)

| Zweck | Host | Port | Sicherheit |
|---|---|---|---|
| IMAP (lesen) | imap.mail.me.com | 993 | SSL |
| SMTP (senden) | smtp.mail.me.com | 587 | STARTTLS |

## Tests

```bash
pip install pytest
pytest
```

Die Tests mocken IMAP/SMTP vollständig, es wird keine echte iCloud-Verbindung
benötigt.
