"""Per-user exchange API-key vault — encrypted at rest.

Each tenant stores their own exchange (e.g. BingX VST testnet) API key + secret. Values
are encrypted with Fernet (AES-128-CBC + HMAC) using a master key from the VAULT_ENC_KEY
env var; only ciphertext is ever written to Postgres. The daemon reads a user's decrypted
keys at trade time to construct their exchange client (per-user engine — see
docs/MULTI_TENANCY.md).

Generate a master key once and set it as VAULT_ENC_KEY (keep it stable — rotating it
orphans existing ciphertext; key-rotation/re-encryption is future work):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.data_models import ExchangeCredential


class VaultError(RuntimeError):
    """Raised when the vault can't operate (e.g. master key missing/invalid)."""


def _fernet() -> Fernet:
    key = os.getenv("VAULT_ENC_KEY", "").strip()
    if not key:
        raise VaultError(
            "VAULT_ENC_KEY is not set — exchange credentials cannot be encrypted/decrypted. "
            "Generate one with Fernet.generate_key() and set it in the environment."
        )
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise VaultError(f"VAULT_ENC_KEY is not a valid Fernet key: {e}") from e


def _mask(api_key: str) -> str:
    """Non-secret display hint, e.g. '••••••3f9a'."""
    tail = api_key[-4:] if len(api_key) >= 4 else api_key
    return "••••••" + tail


class CredentialVault:
    """Stores/reads per-user exchange credentials as ciphertext in Postgres."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        # Create only this table (checkfirst) — don't touch other models' schema.
        ExchangeCredential.__table__.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)

    def save(
        self,
        user_id: str,
        api_key: str,
        api_secret: str,
        exchange: str = "bingx",
        label: Optional[str] = None,
        is_testnet: bool = True,
    ) -> None:
        """Encrypt + upsert a user's credentials for an exchange (one per user+exchange)."""
        f = _fernet()
        enc_key = f.encrypt(api_key.encode()).decode()
        enc_secret = f.encrypt(api_secret.encode()).decode()
        session = self.Session()
        try:
            row = (
                session.query(ExchangeCredential)
                .filter_by(user_id=user_id, exchange=exchange)
                .first()
            )
            if row:
                row.api_key_enc = enc_key
                row.api_secret_enc = enc_secret
                row.label = label
                row.is_testnet = is_testnet
            else:
                session.add(ExchangeCredential(
                    user_id=user_id, exchange=exchange, api_key_enc=enc_key,
                    api_secret_enc=enc_secret, label=label, is_testnet=is_testnet,
                ))
            session.commit()
            logger.info(f"Stored {exchange} credentials for user {user_id} (testnet={is_testnet})")
        finally:
            session.close()

    def get(self, user_id: str, exchange: str = "bingx") -> Optional[Tuple[str, str]]:
        """Return decrypted (api_key, api_secret) for a user, or None if not stored."""
        f = _fernet()
        session = self.Session()
        try:
            row = (
                session.query(ExchangeCredential)
                .filter_by(user_id=user_id, exchange=exchange)
                .first()
            )
            if not row:
                return None
            try:
                return (
                    f.decrypt(row.api_key_enc.encode()).decode(),
                    f.decrypt(row.api_secret_enc.encode()).decode(),
                )
            except InvalidToken as e:
                # Master key changed since these were stored — treat as unusable.
                raise VaultError(
                    "Stored credentials could not be decrypted with the current "
                    "VAULT_ENC_KEY (was the key rotated?)."
                ) from e
        finally:
            session.close()

    def status(self, user_id: str, exchange: str = "bingx") -> Optional[dict]:
        """Non-secret status for the UI: connected? which exchange? masked key hint."""
        creds = self.get(user_id, exchange)
        if not creds:
            return None
        session = self.Session()
        try:
            row = session.query(ExchangeCredential).filter_by(user_id=user_id, exchange=exchange).first()
            return {
                "exchange": exchange,
                "connected": True,
                "label": row.label if row else None,
                "is_testnet": bool(row.is_testnet) if row else True,
                "api_key_masked": _mask(creds[0]),
            }
        finally:
            session.close()

    def delete(self, user_id: str, exchange: str = "bingx") -> bool:
        """Remove a user's credentials for an exchange. Returns True if one was deleted."""
        session = self.Session()
        try:
            n = session.query(ExchangeCredential).filter_by(user_id=user_id, exchange=exchange).delete()
            session.commit()
            return n > 0
        finally:
            session.close()
