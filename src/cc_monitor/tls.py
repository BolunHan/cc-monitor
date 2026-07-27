"""TLS certificate generation and fingerprinting for LAN HTTPS."""

import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

_CERT_FILE = "cert.pem"
_KEY_FILE = "key.pem"


@dataclass
class CertConfig:
    """Loaded TLS certificate configuration."""
    certfile: Path
    keyfile: Path
    fingerprint: str


def generate_self_signed_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Generate a self-signed TLS certificate if one doesn't exist.

    Args:
        cert_dir: Directory to store cert.pem and key.pem.

    Returns:
        Tuple of (cert_path, key_path).
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / _CERT_FILE
    key_path = cert_dir / _KEY_FILE

    if cert_path.exists() and key_path.exists():
        logger.info("TLS certificate already exists at %s", cert_dir)
        return cert_path, key_path

    logger.info("Generating self-signed TLS certificate in %s", cert_dir)

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "cc-monitor"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365 * 10)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("cc-monitor")]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), backend=default_backend())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    logger.info("Generated self-signed certificate: %s", cert_path)
    return cert_path, key_path


def get_cert_fingerprint(cert_path: Path) -> str:
    """Compute the SHA-256 fingerprint of a certificate.

    Args:
        cert_path: Path to the PEM-encoded certificate.

    Returns:
        Fingerprint string in the format "sha256:<64 hex chars>".
    """
    pem = cert_path.read_bytes()
    cert = x509.load_pem_x509_certificate(pem, backend=default_backend())
    der = cert.public_bytes(serialization.Encoding.DER)
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(der)
    return f"sha256:{digest.finalize().hex()}"
