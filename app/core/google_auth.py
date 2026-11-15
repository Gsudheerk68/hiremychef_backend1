"""Verifies a Google ID token (the 'credential' from Sign in with Google)."""
import os

from dotenv import load_dotenv
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

load_dotenv()
_request = google_requests.Request()


class GoogleAuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def verify_google_credential(credential: str) -> dict:
    """Checks signature, expiry, issuer and that the token was issued for OUR client id.
    Returns {sub, email, name}. Raises GoogleAuthError otherwise."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise GoogleAuthError("Google sign-in is not configured on the server", 503)
    try:
        info = id_token.verify_oauth2_token(credential, _request, client_id, clock_skew_in_seconds=10)
    except ValueError as e:  # bad signature, expired, wrong audience or issuer
        raise GoogleAuthError("Invalid Google credential") from e
    except TransportError as e:  # could not reach Google to fetch its public keys
        raise GoogleAuthError("Could not reach Google. Please try again.", 503) from e
    if not info.get("email_verified"):
        raise GoogleAuthError("Your Google email address is not verified")
    if not info.get("email") or not info.get("sub"):
        raise GoogleAuthError("Google did not return an email address")
    email = info["email"].lower()
    return {"sub": info["sub"], "email": email, "name": (info.get("name") or email.split("@")[0]).strip()}
