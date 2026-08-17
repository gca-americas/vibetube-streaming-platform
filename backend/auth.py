"""Google sign-in for the admin console.

Admin access is two independent checks, and both must pass:

  1. **Firebase verifies the Google sign-in** and issues an ID token. That
     establishes *who* the caller is. It says nothing about what they may do --
     anyone with a Google account can obtain a valid token for this project.
  2. **The `admin_users` table** says which verified identities are admins.
     This is the actual authorisation boundary.

Neither is sufficient alone, and the order matters: the allowlist is only
meaningful because the token is verified server-side. A browser can claim any
email it likes, so the address checked against the allowlist is the one Google
signed, never one the client sent.

Verification is done with `google-auth`, which is already a dependency and
checks the signature against Firebase's `securetoken` certificates as well as
the expiry and audience. The issuer and the email claims are checked here on
top, because `verify_firebase_token` does not look at them.
"""
import os
from typing import Optional

from fastapi import Header, HTTPException
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from database import get_db_conn, is_admin_email

# The Firebase project whose tokens this service accepts. Also the audience
# every ID token must carry. Empty disables the admin API entirely.
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
# Public client configuration, served to the browser by /api/auth/config.
# A Firebase web API key is not a credential -- it identifies the project and
# is designed to ship inside client code. What protects the data is this
# module plus the allowlist, not the secrecy of these values.
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "").strip()
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "").strip()

_ISSUER_PREFIX = "https://securetoken.google.com/"

# Shown when the server has no Firebase configuration. Fails closed: an
# unconfigured deployment has an unusable admin API rather than an open one.
_NOT_CONFIGURED = "Admin sign-in is not configured on this server."
_SIGN_IN = "Sign in to use the admin console."


def auth_configured() -> bool:
    return bool(FIREBASE_PROJECT_ID and FIREBASE_API_KEY and FIREBASE_AUTH_DOMAIN)


def public_auth_config() -> dict:
    """The values the browser needs to start a Google sign-in.

    Served at runtime rather than baked into the frontend bundle, so the same
    container image can be pointed at a different Firebase project by changing
    an environment variable instead of rebuilding.
    """
    return {
        "configured": auth_configured(),
        "apiKey": FIREBASE_API_KEY,
        "authDomain": FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
    }


def verify_google_identity(authorization: Optional[str]) -> dict:
    """Verifies a Firebase ID token and returns its claims.

    Raises 401 for anything wrong with the token, 403 for an unverified email,
    and 503 when Google cannot be reached -- a network failure must not be
    reported to the operator as a bad sign-in.
    """
    if not FIREBASE_PROJECT_ID:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=_SIGN_IN)
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail=_SIGN_IN)

    try:
        # One certificate fetch per call. google-auth does not cache them, but
        # admin traffic is a handful of requests per session, and a cache of
        # our own holding a revoked signing key would be a security problem
        # rather than a slow page.
        claims = google_id_token.verify_firebase_token(
            token, google_requests.Request(), audience=FIREBASE_PROJECT_ID
        )
    except google_exceptions.TransportError:
        raise HTTPException(
            status_code=503,
            detail="Could not reach Google to verify the sign-in. Try again.",
        )
    except (ValueError, google_exceptions.GoogleAuthError):
        # Expired, malformed, wrong audience and bad signature all land here.
        # The remedy is identical in every case, so they get one message --
        # and distinguishing them for the caller would only help an attacker.
        raise HTTPException(
            status_code=401, detail="Your sign-in is invalid or has expired. Sign in again."
        )

    if not claims:
        raise HTTPException(status_code=401, detail=_SIGN_IN)

    # verify_firebase_token checks the signature, expiry and audience but not
    # the issuer. Without this, a token minted by a different Firebase project
    # that happened to share our project id as its audience would pass.
    if claims.get("iss") != _ISSUER_PREFIX + FIREBASE_PROJECT_ID:
        raise HTTPException(status_code=401, detail="That token was not issued for this service.")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="That token identifies no account.")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=403, detail="That Google account has no email address.")
    if not claims.get("email_verified"):
        raise HTTPException(
            status_code=403, detail="That Google account's email address is not verified."
        )

    return {**claims, "email": email}


def require_admin_ui(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency guarding every admin route.

    Used as a dependency rather than called inside handlers so that a new
    admin route cannot ship unguarded by forgetting a line: a route without
    it simply has no admin identity to work with.

    The allowlist is read on every request, so revoking someone takes effect
    immediately rather than when their hour-long ID token expires.
    """
    claims = verify_google_identity(authorization)
    email = claims["email"]

    with get_db_conn() as conn:
        cursor = conn.cursor()
        allowed = is_admin_email(cursor, email)

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"{email} is not on the admin allowlist.",
        )

    return {
        "email": email,
        "name": claims.get("name") or "",
        "picture": claims.get("picture") or "",
    }
