"""Broker adapters (read-only)."""

from __future__ import annotations


def make_adapter(account):
    """Return the right read-only adapter for the account's broker."""
    if account.broker == "angel":
        from .angel import AngelAdapter
        return AngelAdapter(account)
    from .hdfc import HdfcAdapter
    return HdfcAdapter(account)

