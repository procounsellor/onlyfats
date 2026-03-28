"""Real-time messaging via Firestore.

Conversation ID format: u{fan_user_id}_c{creator_id}
  - fan_user_id : User.id of the visitor/fan
  - creator_id  : Creator.id (the creator profile id)

Firestore collections:
  conversations/{convId}
  conversations/{convId}/messages/{autoId}
"""
from fastapi import APIRouter, Depends, HTTPException
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.firebase import get_db as get_fstore, create_custom_token
from app.models.creator import Creator
from app.models.user import User

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _conv_id(fan_user_id: int, creator_id: int) -> str:
    return f"u{fan_user_id}_c{creator_id}"


def _firebase_uid(user_id: int) -> str:
    return f"user_{user_id}"


# ── schemas ───────────────────────────────────────────────────────────────────

class StartConversationRequest(BaseModel):
    creator_id: int   # Creator profile ID


class SendMessageRequest(BaseModel):
    conv_id: str
    body: str


# ── Firebase custom token ─────────────────────────────────────────────────────

@router.get("/auth/firebase-token")
async def firebase_token(current_user=Depends(get_current_user)):
    """Exchange JWT for a Firebase custom token so the client can use Firestore listeners."""
    uid = _firebase_uid(current_user.id)
    token = create_custom_token(uid, {"role": current_user.role, "db_id": current_user.id})
    return {"firebase_token": token}


# ── Conversation management ───────────────────────────────────────────────────

@router.post("/messages/conversations")
async def start_conversation(
    payload: StartConversationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fan starts (or re-opens) a conversation with a creator.
    Creators cannot initiate with other creators."""
    # Block creators from using this endpoint (they reply via send_message)
    if current_user.role == "creator":
        raise HTTPException(400, "Use /messages/send to reply as a creator")

    # Find creator
    result = await db.execute(
        select(Creator).where(Creator.id == payload.creator_id, Creator.is_active == True)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(404, "Creator not found")

    # Get creator's user record
    creator_user = await db.get(User, creator.user_id)
    if not creator_user:
        raise HTTPException(404, "Creator user not found")

    fan_user_id = current_user.id
    conv_id = _conv_id(fan_user_id, payload.creator_id)

    fstore = get_fstore()
    conv_ref = fstore.collection("conversations").document(conv_id)
    conv_doc = conv_ref.get()

    if not conv_doc.exists:
        conv_ref.set({
            "convId": conv_id,
            "fanUserId": fan_user_id,
            "creatorId": payload.creator_id,
            "creatorUserId": creator.user_id,
            "fanUid": _firebase_uid(fan_user_id),
            "creatorUid": _firebase_uid(creator.user_id),
            "fanDisplayName": current_user.display_name,
            "creatorDisplayName": creator.display_name,
            "fanAvatarUrl": current_user.profile_image_url or "",
            "creatorAvatarUrl": creator.profile_image_url or "",
            "lastMessage": "",
            "lastMessageAt": SERVER_TIMESTAMP,
            "lastSenderId": None,
            "unreadByFan": 0,
            "unreadByCreator": 0,
            "createdAt": SERVER_TIMESTAMP,
        })

    return {"conv_id": conv_id}


@router.get("/messages/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all conversations for the current user (fan or creator)."""
    fstore = get_fstore()
    uid = _firebase_uid(current_user.id)

    if current_user.role == "creator":
        query = fstore.collection("conversations").where("creatorUid", "==", uid)
    else:
        query = fstore.collection("conversations").where("fanUid", "==", uid)

    docs = query.stream()
    result = []
    for doc in docs:
        d = doc.to_dict()
        is_fan = current_user.role != "creator"
        other_name = d.get("creatorDisplayName") if is_fan else d.get("fanDisplayName")
        other_avatar = d.get("creatorAvatarUrl") if is_fan else d.get("fanAvatarUrl")
        unread = d.get("unreadByFan", 0) if is_fan else d.get("unreadByCreator", 0)
        last_at = d.get("lastMessageAt")
        result.append({
            "conv_id": doc.id,
            "other_name": other_name,
            "other_avatar": other_avatar,
            "last_message": d.get("lastMessage", ""),
            "last_message_at": last_at.isoformat() if hasattr(last_at, "isoformat") else None,
            "unread_count": unread,
        })

    result.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return result


@router.post("/messages/send")
async def send_message(
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send a message. Validates role rules then writes to Firestore."""
    fstore = get_fstore()
    conv_ref = fstore.collection("conversations").document(payload.conv_id)
    conv_doc = conv_ref.get()

    if not conv_doc.exists:
        raise HTTPException(404, "Conversation not found")

    conv = conv_doc.to_dict()
    sender_uid = _firebase_uid(current_user.id)

    # Authorization: sender must be fan or creator of this conversation
    if sender_uid not in (conv["fanUid"], conv["creatorUid"]):
        raise HTTPException(403, "Not a participant of this conversation")

    # Enforce creator-to-creator block
    if current_user.role == "creator":
        fan_user_id = conv["fanUserId"]
        fan = await db.get(User, fan_user_id)
        if not fan:
            raise HTTPException(404, "Fan not found")
        if fan.role == "creator":
            raise HTTPException(400, "Creators cannot message other creators")

    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Message body cannot be empty")

    # Write message to subcollection
    msg_ref = conv_ref.collection("messages").document()
    msg_ref.set({
        "senderId": current_user.id,
        "senderUid": sender_uid,
        "senderName": current_user.display_name,
        "senderRole": current_user.role,
        "body": body,
        "createdAt": SERVER_TIMESTAMP,
        "read": False,
    })

    # Update conversation metadata
    is_sender_fan = sender_uid == conv["fanUid"]
    conv_ref.update({
        "lastMessage": body[:200],
        "lastMessageAt": SERVER_TIMESTAMP,
        "lastSenderId": current_user.id,
        "unreadByFan": conv.get("unreadByFan", 0) + (0 if is_sender_fan else 1),
        "unreadByCreator": conv.get("unreadByCreator", 0) + (1 if is_sender_fan else 0),
    })

    return {"status": True}


@router.get("/messages/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    current_user=Depends(get_current_user),
):
    """Fetch all messages in a conversation (Admin SDK — bypasses Firestore security rules)."""
    fstore = get_fstore()
    conv_ref = fstore.collection("conversations").document(conv_id)
    conv_doc = conv_ref.get()
    if not conv_doc.exists:
        raise HTTPException(404, "Conversation not found")

    conv = conv_doc.to_dict()
    uid = _firebase_uid(current_user.id)
    if uid not in (conv.get("fanUid", ""), conv.get("creatorUid", "")):
        raise HTTPException(403, "Not a participant")

    docs = list(conv_ref.collection("messages").order_by("createdAt").stream())
    result = []
    for d in docs:
        data = d.to_dict()
        created_at = data.get("createdAt")
        result.append({
            "id": d.id,
            "senderId": data.get("senderId"),
            "senderUid": data.get("senderUid"),
            "senderName": data.get("senderName"),
            "senderRole": data.get("senderRole"),
            "body": data.get("body", ""),
            "createdAt": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
            "read": data.get("read", False),
        })
    return result


@router.post("/messages/conversations/{conv_id}/read")
async def mark_read(
    conv_id: str,
    current_user=Depends(get_current_user),
):
    """Mark all messages as read for the current user."""
    fstore = get_fstore()
    conv_ref = fstore.collection("conversations").document(conv_id)
    conv_doc = conv_ref.get()
    if not conv_doc.exists:
        raise HTTPException(404, "Conversation not found")

    conv = conv_doc.to_dict()
    sender_uid = _firebase_uid(current_user.id)
    if sender_uid not in (conv["fanUid"], conv["creatorUid"]):
        raise HTTPException(403, "Not a participant")

    is_fan = sender_uid == conv["fanUid"]
    conv_ref.update({"unreadByFan": 0} if is_fan else {"unreadByCreator": 0})
    return {"status": True}
