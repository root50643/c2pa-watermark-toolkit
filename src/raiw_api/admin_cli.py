from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from raiw_api.archive import ArchiveManager
from raiw_api.config import get_settings
from raiw_api.db import Database
from raiw_api.security import issue_api_key


def _database() -> tuple[Database, ArchiveManager]:
    settings = get_settings()
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    db.initialize()
    return db, ArchiveManager(settings, db)


def _print_rows(rows: list[dict[str, Any]]) -> None:
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


def _export(rows: list[dict[str, Any]], output: Path, fmt: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raiw-api-admin", description="Local administration for RAIW API")
    root = parser.add_subparsers(dest="resource", required=True)

    customer = root.add_parser("customer")
    customer_actions = customer.add_subparsers(dest="action", required=True)
    create = customer_actions.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--external-id")
    create.add_argument("--contact")
    create.add_argument("--issue-key", action="store_true")
    customer_actions.add_parser("list")
    state = customer_actions.add_parser("set-active")
    state.add_argument("customer_id")
    state.add_argument("active", choices=["true", "false"])

    key = root.add_parser("key")
    key_actions = key.add_subparsers(dest="action", required=True)
    issue = key_actions.add_parser("issue")
    issue.add_argument("customer_id")
    key_list = key_actions.add_parser("list")
    key_list.add_argument("--customer-id")
    revoke = key_actions.add_parser("revoke")
    revoke.add_argument("key_id")

    archive = root.add_parser("archive")
    archive_actions = archive.add_subparsers(dest="action", required=True)
    archive_export = archive_actions.add_parser("export")
    archive_export.add_argument("--format", choices=["csv", "json"], default="json")
    archive_export.add_argument("--output", type=Path, required=True)
    archive_actions.add_parser("verify")
    delete = archive_actions.add_parser("delete")
    delete.add_argument("request_id")
    delete.add_argument("--yes", action="store_true")

    audit = root.add_parser("audit")
    audit_actions = audit.add_subparsers(dest="action", required=True)
    audit_export = audit_actions.add_parser("export")
    audit_export.add_argument("--format", choices=["csv", "json"], default="json")
    audit_export.add_argument("--output", type=Path, required=True)
    audit_export.add_argument("--customer-id")
    audit_export.add_argument("--client-ip")
    audit_export.add_argument("--route")
    audit_export.add_argument("--start")
    audit_export.add_argument("--end")
    audit_export.add_argument("--status", type=int)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    db, archive = _database()
    settings = archive.settings

    if args.resource == "customer" and args.action == "create":
        customer = db.create_customer(args.name, args.external_id, args.contact)
        result: dict[str, Any] = {"customer": customer}
        if args.issue_key:
            plain, key = issue_api_key(db, settings.api_key_pepper, customer["id"])
            result.update(api_key=plain, key_id=key["id"], warning="This key is displayed once; store it securely.")
        _print_rows([result])
    elif args.resource == "customer" and args.action == "list":
        _print_rows(db.list_customers())
    elif args.resource == "customer" and args.action == "set-active":
        if not db.set_customer_active(args.customer_id, args.active == "true"):
            raise SystemExit("Customer not found")
        print("updated")
    elif args.resource == "key" and args.action == "issue":
        plain, record = issue_api_key(db, settings.api_key_pepper, args.customer_id)
        _print_rows([{"api_key": plain, "key_id": record["id"], "warning": "Displayed once; store securely."}])
    elif args.resource == "key" and args.action == "list":
        _print_rows(db.list_api_keys(args.customer_id))
    elif args.resource == "key" and args.action == "revoke":
        if not db.revoke_api_key(args.key_id):
            raise SystemExit("Active key not found")
        print("revoked")
    elif args.resource == "archive" and args.action == "export":
        rows = db.list_archives()
        for row in rows:
            row.pop("key_id", None)
        _export(rows, args.output, args.format)
        print(f"exported {len(rows)} records to {args.output}")
    elif args.resource == "archive" and args.action == "verify":
        failures: list[dict[str, str]] = []
        rows = db.list_archives()
        for row in rows:
            for path_key, hash_key in (("input_path", "input_sha256"), ("output_path", "output_sha256")):
                if not row.get(path_key):
                    continue
                path = archive.absolute_path(row[path_key])
                if not path.exists():
                    failures.append({"request_id": row["request_id"], "path": row[path_key], "error": "missing"})
                elif row.get(hash_key) and _hash(path) != row[hash_key]:
                    failures.append(
                        {"request_id": row["request_id"], "path": row[path_key], "error": "sha256 mismatch"}
                    )
        _print_rows(failures)
        print(f"checked {len(rows)} records; failures={len(failures)}", file=sys.stderr)
        if failures:
            raise SystemExit(1)
    elif args.resource == "archive" and args.action == "delete":
        if not args.yes:
            raise SystemExit("Refusing deletion without --yes")
        row = db.get_archive(args.request_id)
        if not row:
            raise SystemExit("Archive record not found")
        directory = archive.absolute_path(row["input_path"]).parent
        deleting = directory.with_name(f".{directory.name}.deleting")
        directory.replace(deleting)
        try:
            if not db.delete_archive_record(args.request_id):
                raise RuntimeError("Could not delete database record")
            shutil.rmtree(deleting)
        except Exception:
            if deleting.exists():
                deleting.replace(directory)
            raise
        print("deleted")
    elif args.resource == "audit" and args.action == "export":
        rows = db.list_access_logs(
            customer_id=args.customer_id,
            client_ip=args.client_ip,
            route=args.route,
            start=args.start,
            end=args.end,
            status=args.status,
        )
        _export(rows, args.output, args.format)
        print(f"exported {len(rows)} records to {args.output}")


if __name__ == "__main__":
    main()
