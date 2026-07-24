"""Simple CLI for the iCloud email connector.

Examples:
    python -m icloud_email_connector list-folders
    python -m icloud_email_connector fetch --folder INBOX --limit 5
    python -m icloud_email_connector send --to x@example.com --subject Hi --body "Hello!"
"""

from __future__ import annotations

import argparse
import sys

from .client import ICloudEmailConnector, ICloudEmailError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="icloud_email_connector")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-folders")

    fetch_p = sub.add_parser("fetch")
    fetch_p.add_argument("--folder", default="INBOX")
    fetch_p.add_argument("--search", default="ALL")
    fetch_p.add_argument("--limit", type=int, default=10)

    send_p = sub.add_parser("send")
    send_p.add_argument("--to", required=True)
    send_p.add_argument("--subject", required=True)
    send_p.add_argument("--body", required=True)

    args = parser.parse_args(argv)

    try:
        with ICloudEmailConnector() as connector:
            if args.command == "list-folders":
                for name in connector.list_folders():
                    print(name)
            elif args.command == "fetch":
                for msg in connector.fetch_messages(args.folder, args.search, args.limit):
                    print(f"[{msg.uid}] {msg.date} {msg.sender} - {msg.subject}")
            elif args.command == "send":
                connector.send_message(args.to, args.subject, args.body)
                print("Message sent.")
    except ICloudEmailError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
