"""Tests for cc_monitor.tls."""
import tempfile
from pathlib import Path

from cc_monitor.tls import generate_self_signed_cert, get_cert_fingerprint


class TestGenerateSelfSignedCert:
    def test_creates_cert_and_key_files(self, tmp_path):
        cert_dir = tmp_path / "certs"
        cert_path, key_path = generate_self_signed_cert(cert_dir)

        assert cert_path.exists()
        assert key_path.exists()
        assert cert_path.suffix == ".pem"
        assert key_path.suffix == ".pem"

    def test_skips_if_files_exist(self, tmp_path):
        cert_dir = tmp_path / "certs"
        cert_dir.mkdir()
        (cert_dir / "cert.pem").write_text("fake-cert")
        (cert_dir / "key.pem").write_text("fake-key")

        cert_path, key_path = generate_self_signed_cert(cert_dir)

        assert cert_path.read_text() == "fake-cert"
        assert key_path.read_text() == "fake-key"

    def test_creates_parent_directory(self, tmp_path):
        cert_dir = tmp_path / "nested" / "certs"
        cert_path, key_path = generate_self_signed_cert(cert_dir)

        assert cert_dir.exists()
        assert cert_path.exists()
        assert key_path.exists()

    def test_cert_is_valid_pem(self, tmp_path):
        from cryptography import x509

        cert_path, _ = generate_self_signed_cert(tmp_path)
        pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(pem)
        assert cert.subject == cert.issuer  # self-signed


class TestGetCertFingerprint:
    def test_returns_sha256_prefix(self, tmp_path):
        cert_path, _ = generate_self_signed_cert(tmp_path)
        fp = get_cert_fingerprint(cert_path)
        assert fp.startswith("sha256:")
        assert len(fp) == 7 + 64  # "sha256:" + 64 hex chars

    def test_same_cert_same_fingerprint(self, tmp_path):
        cert_path, _ = generate_self_signed_cert(tmp_path)
        fp1 = get_cert_fingerprint(cert_path)
        fp2 = get_cert_fingerprint(cert_path)
        assert fp1 == fp2
