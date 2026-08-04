import os
import time
import json
import base64
import requests
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "mock-project-id")

security = HTTPBearer()

# Dynamic caching for Google's public x509 certificates
_certs_cache = {}
_certs_expire = 0

def get_google_certs():
    global _certs_cache, _certs_expire
    now = time.time()
    if _certs_cache and now < _certs_expire:
        return _certs_cache
    
    try:
        response = requests.get("https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com")
        if response.status_code == 200:
            _certs_cache = response.json()
            # Parse max-age from Cache-Control header
            cache_control = response.headers.get("Cache-Control", "")
            max_age = 3600
            for part in cache_control.split(","):
                if "max-age" in part:
                    try:
                        max_age = int(part.split("=")[1])
                    except Exception:
                        pass
            _certs_expire = now + max_age
            return _certs_cache
    except Exception as e:
        print(f"Error fetching Google certificates: {e}")
    
    return _certs_cache

def base64url_decode(s: str) -> bytes:
    padding_needed = len(s) % 4
    if padding_needed:
        s += '=' * (4 - padding_needed)
    return base64.urlsafe_b64decode(s.encode('utf-8'))

def verify_firebase_token(token: str) -> dict:
    # Support mock auth token bypass for offline/local testing
    if token.startswith("mock-token-"):
        username = token.replace("mock-token-", "")
        return {
            "uid": f"mock-uid-{username}",
            "email": f"{username}@example.com",
            "name": username.capitalize(),
            "picture": "/images/avatars/v1.jpg"
        }

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Token must have header, payload, and signature parts.")
        
        header = json.loads(base64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(base64url_decode(parts[1]).decode('utf-8'))
        signature = base64url_decode(parts[2])
        message = (parts[0] + "." + parts[1]).encode('utf-8')
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token format: {str(e)}"
        )
    
    if header.get("alg") != "RS256":
        raise HTTPException(status_code=401, detail="Invalid token algorithm, must be RS256")
    
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="kid missing from header")
    
    certs = get_google_certs()
    if not certs or kid not in certs:
        raise HTTPException(status_code=401, detail="Valid public signature certificate not found")
        
    pem_cert = certs[kid]
    
    # Verify RSA signature
    try:
        cert_obj = load_pem_x509_certificate(pem_cert.encode('utf-8'))
        public_key = cert_obj.public_key()
        public_key.verify(
            signature,
            message,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token signature verification failed: {str(e)}")
        
    # Validate payload properties
    now = time.time()
    if payload.get("exp", 0) < now:
        raise HTTPException(status_code=401, detail="Token has expired")
    if payload.get("iat", now) > now + 300:
        raise HTTPException(status_code=401, detail="Token issued in the future")
        
    if payload.get("aud") != FIREBASE_PROJECT_ID:
        raise HTTPException(status_code=401, detail="Audience mismatch")
    
    expected_iss = f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}"
    if payload.get("iss") != expected_iss:
        raise HTTPException(status_code=401, detail="Issuer mismatch")
        
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="sub (uid) missing from payload")
        
    return {
        "uid": payload["sub"],
        "email": payload.get("email"),
        "name": payload.get("name"),
        "picture": payload.get("picture")
    }

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return verify_firebase_token(credentials.credentials)
