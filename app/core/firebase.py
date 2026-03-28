"""Firebase Admin SDK — initialized once on first use."""
import firebase_admin
from firebase_admin import credentials, firestore as fb_store, auth as fb_auth
from app.core.config import settings

_app = None


def _init():
    global _app
    if _app is not None:
        return
    if settings.FIREBASE_SA_KEY_PATH:
        cred = credentials.Certificate(settings.FIREBASE_SA_KEY_PATH)
        _app = firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
    else:
        # Use Application Default Credentials (works on GCP / local with gcloud auth)
        _app = firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})


def get_db():
    _init()
    return fb_store.client()


def create_custom_token(uid: str, extra_claims: dict = None) -> str:
    _init()
    token = fb_auth.create_custom_token(uid, extra_claims)
    return token.decode("utf-8") if isinstance(token, bytes) else token
