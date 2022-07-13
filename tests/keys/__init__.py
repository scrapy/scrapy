import os
from datetime import datetime, timedelta

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.x509 import (
    CertificateBuilder,
    DNSName,
    Name,
    NameAttribute,
    random_serial_number,
    SubjectAlternativeName,
)
from cryptography.x509.oid import NameOID


# https://cryptography.io/en/latest/x509/tutorial/#creating-a-self-signed-certificate
def generate_keys():
    folder = os.path.dirname(__file__)

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    with open(os.path.join(folder, 'localhost.key'), "wb") as f:
        f.write(
            key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption(),
            )
        )

    subject = issuer = Name(
        [
            NameAttribute(NameOID.COUNTRY_NAME, "IE"),
            NameAttribute(NameOID.ORGANIZATION_NAME, "Scrapy"),
            NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )
    cert = (
        CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=10))
        .add_extension(
            SubjectAlternativeName([DNSName("localhost")]),
            critical=False,
        )
        .sign(key, SHA256(), default_backend())
    )
    with open(os.path.join(folder, 'localhost.crt'), "wb") as f:
        f.write(cert.public_bytes(Encoding.PEM))
