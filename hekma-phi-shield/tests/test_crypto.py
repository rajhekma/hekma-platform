import pytest
from api.services.crypto import CryptoEngine


def test_crypto_encryption_and_decryption():
    engine = CryptoEngine()
    secret_text = "John Doe, SSN: 123-45-6789, MRN: 987654"
    ciphertext = engine.encrypt(secret_text)
    assert ciphertext != secret_text
    assert len(ciphertext) > 0

    decrypted = engine.decrypt(ciphertext)
    assert decrypted == secret_text


def test_crypto_deterministic_token_and_hmac():
    engine = CryptoEngine()
    val1 = "Afton574 Casper496"
    val2 = "Afton574 Casper496"
    val3 = "Different Patient"

    hash1 = engine.hash_plaintext(val1)
    hash2 = engine.hash_plaintext(val2)
    hash3 = engine.hash_plaintext(val3)

    assert hash1 == hash2
    assert hash1 != hash3

    token1 = engine.generate_deterministic_token("PATIENT_NAME", val1)
    token2 = engine.generate_deterministic_token("PATIENT_NAME", val2)
    token3 = engine.generate_deterministic_token("PATIENT_NAME", val3)

    assert token1 == token2
    assert token1.startswith("PATIENT_NAME_")
    assert token1 != token3


def test_crypto_empty_and_error_handling():
    engine = CryptoEngine()
    assert engine.encrypt("") == ""
    assert engine.decrypt("") == ""
    assert engine.hash_plaintext("") == ""

    with pytest.raises(ValueError):
        engine.decrypt("invalid-non-fernet-string")
