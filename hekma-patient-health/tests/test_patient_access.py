import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from hekma_patient_health.auth.jwt_util import JwtUtil
from hekma_patient_health.auth.patient_access import assert_patient_access
from hekma_patient_health.main import create_app


def _token(user_id: str, role: str = "PATIENT") -> str:
    util = JwtUtil()
    return jwt.encode(
        {
            "sub": f"user-{user_id}",
            "userId": user_id,
            "role": role,
            "exp": int(time.time()) + 3600,
        },
        util.jwt_secret,
        algorithm=util.algorithm,
    )


def test_patient_cannot_read_another_patient():
    with pytest.raises(HTTPException) as exc:
        assert_patient_access({"userId": "111", "role": "PATIENT"}, "222")
    assert exc.value.status_code == 404


def test_patient_can_read_self():
    user = assert_patient_access({"userId": "111", "role": "PATIENT"}, "111")
    assert user["userId"] == "111"


def test_staff_can_read_any_patient():
    user = assert_patient_access({"userId": "99", "role": "SITE"}, "222")
    assert user["role"] == "SITE"


def test_medication_route_rejects_cross_patient_token():
    client = TestClient(create_app())
    token = _token("111")
    response = client.get(
        "/api/patients/222/medications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_health_is_public():
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["service"] == "hekma-patient-health"


def test_medications_require_auth():
    client = TestClient(create_app())
    assert client.get("/api/patients/111/medications").status_code == 401


def test_fasten_initiate_requires_auth():
    client = TestClient(create_app())
    assert (
        client.post("/fastenhealth/initiate", json={"orgConnectionId": "x"}).status_code
        == 401
    )


def test_fasten_revoke_is_staff_only():
    client = TestClient(create_app())
    token = _token("111")
    response = client.post(
        "/fastenhealth/vault/revoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "a@b.com"},
    )
    assert response.status_code == 404


def test_widget_complete_requires_auth():
    client = TestClient(create_app())
    response = client.post(
        "/fastenhealth/callback",
        json={"type": "widget.complete", "patientId": "111", "data": []},
    )
    assert response.status_code == 401


def test_healthkit_requires_auth():
    client = TestClient(create_app())
    assert client.get("/healthkit", params={"id": "111"}).status_code == 401
    assert client.post("/healthkit", json={"id": "111", "timestamp": "2026-10-11T00:00:00"}).status_code == 401


def test_healthkit_rejects_cross_patient_token():
    client = TestClient(create_app())
    token = _token("111")
    response = client.get(
        "/healthkit",
        params={"id": "222"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_ctms_repo_does_not_import_monolith():
    import hekma_patient_health.repositories.ctms_clinical_repo as repo

    assert not repo.__file__.endswith("hekma_data_pipleline")
