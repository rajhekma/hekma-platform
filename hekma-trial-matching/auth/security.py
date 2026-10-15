from fastapi import Header, HTTPException, Request
from .jwt_util import JwtUtil
import os
import logging

jwt_util = JwtUtil()

#logger = logging.getLogger("jwt_debug")
#logger.setLevel(logging.INFO)


def jwt_filter(
    request: Request,
    authorization: str = Header(None)
):
    # logger.info("---- JWT FILTER CALLED ----")
    # logger.info(f"Request method: {request.method}")
    # logger.info(f"Incoming headers: {dict(request.headers)}")
    # logger.info(f"Authorization param value: {authorization}")

    if request.method == "OPTIONS":
        #logger.info("OPTIONS request detected, skipping JWT check.")
        return None

    if not authorization:
        #logger.error("Authorization header missing!")
        raise HTTPException(status_code=401, detail="Authorization header missing")

    prefix = os.getenv("JWT_HEADER_PREFIX", "Bearer")
    #logger.info(f"Configured prefix: {prefix}")

    if authorization.startswith(prefix + " "):
        token = authorization[len(prefix) + 1:].strip()
        #logger.info("Matched configured prefix.")
    elif authorization.startswith("Token "):
        token = authorization[len("Token "):].strip()
        ##logger.info("Matched 'Token ' prefix.")
    else:
        #logger.error(f"Invalid Authorization format received: {authorization}")
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format"
        )

    #logger.info(f"Extracted token (first 20 chars): {token[:20]}...")

    try:
        validated = jwt_util.validate(token)
        #logger.info("JWT validation successful.")
        return validated
    except Exception as e:
        #logger.error(f"JWT validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")