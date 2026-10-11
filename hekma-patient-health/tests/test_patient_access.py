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
