import pytest

from hekma_patient_health.utils.url_safety import UnsafeDownloadUrlError, assert_safe_download_url


def test_rejects_localhost():
    with pytest.raises(UnsafeDownloadUrlError):
        assert_safe_download_url("http://127.0.0.1/secret")


def test_rejects_non_http():
    with pytest.raises(UnsafeDownloadUrlError):
        assert_safe_download_url("file:///etc/passwd")
