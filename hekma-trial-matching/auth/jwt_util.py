import os
import jwt
import base64
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException

class JwtUtil:
    def __init__(self):
        raw_secret = os.getenv("JWT_SECRET")
        if not raw_secret:
            raise RuntimeError("JWT_SECRET not configured")

        raw_secret = raw_secret.strip()

        # Try Base64 first
        try:
            self.jwt_secret = base64.b64decode(raw_secret)
        except Exception:
            # Fallback: Java secret.getBytes()
            self.jwt_secret = raw_secret.encode("utf-8")

        self.algorithm = "HS512"

    def validate(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.algorithm],
                options={
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )

            return {
                "userName": payload.get("sub"),
                "role": payload.get("role"),
                "userId": payload.get("userId"),
            }

        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Expired JWT token")
        except InvalidTokenError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid JWT token: {str(e)}",
            )
