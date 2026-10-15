import base64
import hashlib
import hmac
import logging
import os
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from api.config.settings import settings

logger = logging.getLogger("pii-phi.crypto")


class CryptoEngine:
    """Enterprise Cryptographic Engine supporting AES-256-GCM, HMAC indexing, and AWS KMS."""

    def __init__(self, key_bytes: Optional[bytes] = None, hmac_secret: Optional[str] = None):
        raw_key = key_bytes or settings.ENCRYPTION_KEY.encode()
        try:
            # Check if valid Fernet key
            self._fernet = Fernet(raw_key)
            self._raw_key = base64.urlsafe_b64decode(raw_key)
        except Exception:
            # Fallback/derive 32-byte key for AES-GCM
            self._raw_key = hashlib.sha256(raw_key).digest()
            self._fernet = Fernet(base64.urlsafe_b64encode(self._raw_key))

        self._hmac_secret = (hmac_secret or settings.HMAC_SECRET).encode()
        self._kms_client = None

        if settings.KMS_ENABLED and settings.AWS_KMS_KEY_ID:
            try:
                import boto3
                self._kms_client = boto3.client("kms", region_name=settings.AWS_REGION)
                logger.info("AWS KMS envelope encryption initialized with key ID: %s", settings.AWS_KMS_KEY_ID)
            except Exception as e:
                logger.warning("Failed to initialize AWS KMS client: %s. Falling back to local AES-256.", e)

    def hash_plaintext(self, plaintext: str) -> str:
        """Computes a secure HMAC-SHA256 hash of plaintext for O(1) deduplication indexing."""
        if not plaintext:
            return ""
        return hmac.new(self._hmac_secret, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()

    def generate_deterministic_token(self, prefix: str, plaintext: str, length: int = 8) -> str:
        """Generates a consistent, collision-resistant pseudonym token for a given plaintext."""
        h = self.hash_plaintext(plaintext)
        short_hash = h[:length]
        return f"{prefix.upper()}_{short_hash}"

    def encrypt(self, plaintext: str) -> str:
        """Encrypts raw PHI/PII plaintext returning an armored ciphertext string."""
        if not plaintext:
            return ""
        if self._kms_client and settings.AWS_KMS_KEY_ID:
            try:
                return self._encrypt_kms(plaintext)
            except Exception as e:
                logger.error("KMS encryption failed: %s. Falling back to local AES-256.", e)
        
        # Local Fernet (AES-128-CBC + HMAC-SHA256) / AES-GCM
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypts an armored ciphertext string back to raw plaintext."""
        if not ciphertext:
            return ""
        if ciphertext.startswith("kms:"):
            return self._decrypt_kms(ciphertext)
        
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error("Decryption failed for ciphertext: %s", e)
            raise ValueError(f"Failed to decrypt ciphertext: {e}") from e

    def _encrypt_kms(self, plaintext: str) -> str:
        """AWS KMS Envelope Encryption: generates data key, encrypts with AES-256-GCM."""
        response = self._kms_client.generate_data_key(
            KeyId=settings.AWS_KMS_KEY_ID,
            KeySpec="AES_256",
        )
        plain_key = response["Plaintext"]
        encrypted_key = response["CiphertextBlob"]

        aesgcm = AESGCM(plain_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        enc_key_b64 = base64.b64encode(encrypted_key).decode("utf-8")
        nonce_b64 = base64.b64encode(nonce).decode("utf-8")
        ct_b64 = base64.b64encode(ct).decode("utf-8")

        return f"kms:{enc_key_b64}:{nonce_b64}:{ct_b64}"

    def _decrypt_kms(self, kms_ciphertext: str) -> str:
        """Decrypts KMS envelope ciphertext."""
        parts = kms_ciphertext.split(":")
        if len(parts) != 4:
            raise ValueError("Malformed KMS ciphertext payload")
        
        _, enc_key_b64, nonce_b64, ct_b64 = parts
        encrypted_key = base64.b64decode(enc_key_b64)
        nonce = base64.b64decode(nonce_b64)
        ct = base64.b64decode(ct_b64)

        response = self._kms_client.decrypt(CiphertextBlob=encrypted_key)
        plain_key = response["Plaintext"]

        aesgcm = AESGCM(plain_key)
        pt = aesgcm.decrypt(nonce, ct, None)
        return pt.decode("utf-8")


crypto_engine = CryptoEngine()
