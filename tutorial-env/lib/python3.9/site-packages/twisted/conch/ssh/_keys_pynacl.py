# -*- test-case-name: twisted.conch.test.test_keys -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Optional PyNaCl fallback code for Ed25519 keys.
"""

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


class Ed25519PublicKey(ed25519.Ed25519PublicKey):
    def __init__(self, data: bytes):
        self._key = VerifyKey(data)

    def __bytes__(self) -> bytes:
        return bytes(self._key)

    def __hash__(self) -> int:
        return hash(bytes(self))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self._key == other._key

    def __ne__(self, other: object) -> bool:
        return not (self == other)

    @classmethod
    def from_public_bytes(cls, data: bytes) -> ed25519.Ed25519PublicKey:
        return cls(data)

    def public_bytes(
        self,
        encoding: serialization.Encoding,
        format: serialization.PublicFormat,
    ) -> bytes:
        if (
            encoding is not serialization.Encoding.Raw
            or format is not serialization.PublicFormat.Raw
        ):
            raise ValueError("Both encoding and format must be Raw")
        return bytes(self)

    def verify(self, signature: bytes, data: bytes) -> None:
        try:
            self._key.verify(data, signature)
        except BadSignatureError as e:
            raise InvalidSignature(str(e))


class Ed25519PrivateKey(ed25519.Ed25519PrivateKey):
    def __init__(self, data: bytes):
        self._key = SigningKey(data)

    def __bytes__(self) -> bytes:
        return bytes(self._key)

    def __hash__(self) -> int:
        return hash(bytes(self))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self._key == other._key

    def __ne__(self, other: object) -> bool:
        return not (self == other)

    @classmethod
    def generate(cls) -> ed25519.Ed25519PrivateKey:
        return cls(bytes(SigningKey.generate()))

    @classmethod
    def from_private_bytes(cls, data: bytes) -> ed25519.Ed25519PrivateKey:
        return cls(data)

    def public_key(self) -> ed25519.Ed25519PublicKey:
        return Ed25519PublicKey(bytes(self._key.verify_key))

    def private_bytes(
        self,
        encoding: serialization.Encoding,
        format: serialization.PrivateFormat,
        encryption_algorithm: serialization.KeySerializationEncryption,
    ) -> bytes:
        if (
            encoding is not serialization.Encoding.Raw
            or format is not serialization.PrivateFormat.Raw
            or not isinstance(encryption_algorithm, serialization.NoEncryption)
        ):
            raise ValueError(
                "Encoding and format must be Raw and "
                "encryption_algorithm must be NoEncryption"
            )
        return bytes(self)

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(data).signature
