from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from typing import Any

from raiw_api.db import Database

ANONYMOUS_CUSTOMER_ID = "00000000-0000-0000-0000-000000000000"
ANONYMOUS_CUSTOMER_NAME = "Anonymous API Client"
ANONYMOUS_EXTERNAL_ID = "anonymous"


@dataclass(frozen=True, slots=True)
class Principal:
    customer_id: str
    customer_name: str
    external_id: str | None
    key_id: str | None
    key_prefix: str | None


def _digest(key: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def issue_api_key(db: Database, pepper: str, customer_id: str) -> tuple[str, dict[str, Any]]:
    if not db.get_customer(customer_id):
        raise ValueError(f"Unknown customer: {customer_id}")
    prefix = secrets.token_hex(6)
    key = f"raiw_{prefix}_{secrets.token_urlsafe(32)}"
    record = db.insert_api_key(customer_id, prefix, _digest(key, pepper))
    return key, record


def authenticate_api_key(db: Database, pepper: str, key: str) -> Principal | None:
    parts = key.split("_", 2)
    if len(parts) != 3 or parts[0] != "raiw" or len(parts[1]) != 12:
        return None
    row = db.find_api_key_by_prefix(parts[1])
    if not row or row["revoked_at"] is not None or not row["customer_active"]:
        return None
    if not hmac.compare_digest(row["key_hmac"], _digest(key, pepper)):
        return None
    db.touch_api_key(row["id"])
    return Principal(
        customer_id=row["customer_id"],
        customer_name=row["customer_name"],
        external_id=row["external_id"],
        key_id=row["id"],
        key_prefix=row["prefix"],
    )


def anonymous_principal(db: Database) -> Principal:
    customer = db.ensure_customer(
        ANONYMOUS_CUSTOMER_ID,
        ANONYMOUS_CUSTOMER_NAME,
        ANONYMOUS_EXTERNAL_ID,
    )
    return Principal(
        customer_id=customer["id"],
        customer_name=customer["name"],
        external_id=customer["external_id"],
        key_id=None,
        key_prefix=None,
    )


def client_ip(peer_ip: str, forwarded_for: str | None, trusted_cidrs: tuple[str, ...]) -> str:
    """Use X-Forwarded-For only when the immediate socket peer is trusted."""
    try:
        peer = ipaddress.ip_address(peer_ip)
        trusted = any(peer in ipaddress.ip_network(cidr, strict=False) for cidr in trusted_cidrs)
    except ValueError:
        return peer_ip
    if not trusted or not forwarded_for:
        return peer_ip

    chain = [item.strip() for item in forwarded_for.split(",") if item.strip()]
    chain.append(peer_ip)
    networks = [ipaddress.ip_network(cidr, strict=False) for cidr in trusted_cidrs]
    for candidate in reversed(chain):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(address in network for network in networks):
            return str(address)
    return str(peer)
