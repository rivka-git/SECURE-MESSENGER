import logging
import json

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from .models import User, Message, Group, GroupMember, GroupMessage, GroupMessageRead, get_db
from .schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    SendMessageRequest, MessageResponse,
    CreateGroupRequest, GroupResponse, SendGroupMessageRequest, GroupMessageResponse,
)
from .auth import create_access_token, hash_password, verify_password, require_auth
from .crypto import encrypt, decrypt
from .broadcaster import broadcaster
from .emoji_mapper import emotion_to_emoji
from emotion_detector import get_current_emotion


def decrypt_safe(blob: str) -> str:
    try:
        return decrypt(blob)
    except Exception as exc:
        log.warning('Failed to decrypt message blob: %s', exc)
        return ''


log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="username already taken")
    db.add(User(username=body.username, password_hash=hash_password(body.password)))
    db.commit()
    return {"message": "user created successfully"}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=create_access_token(user.username))


@router.post("/detect-emotion")
async def detect_emotion(
    frame: UploadFile | None = File(default=None),
    username: str = Depends(require_auth),
):
    """
    Detect user's emotion from an uploaded browser camera frame.
    If no frame is supplied, falls back to the server camera.
    """
    try:
        if frame is None:
            emotion = get_current_emotion()
        else:
            data = await frame.read()
            image = np.frombuffer(data, np.uint8)
            frame_img = cv2.imdecode(image, cv2.IMREAD_COLOR)
            if frame_img is None:
                raise ValueError("Could not decode uploaded image")
            emotion = get_current_emotion(frame_img)

        emoji = emotion_to_emoji(emotion)
        return {"emotion": emotion, "emoji": emoji}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emotion detection failed: {str(e)}")


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    body: SendMessageRequest,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    if not body.content and not body.emoji:
        raise HTTPException(status_code=400, detail="message must include text or emoji")
    if not db.query(User).filter(User.username == body.recipient).first():
        raise HTTPException(status_code=404, detail="recipient not found")

    msg = Message(sender=username, recipient=body.recipient, ciphertext=encrypt(body.content), emoji=body.emoji)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    response = MessageResponse(
        id=msg.id, sender=msg.sender, recipient=msg.recipient,
        content=body.content, emoji=msg.emoji, created_at=msg.created_at, is_read=False,
    )
    # Broadcast the decrypted message to both sender and recipient
    broadcast_data = response.model_dump(mode="json")
    await broadcaster.publish(broadcast_data)
    return response


@router.post("/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    message_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    msg = db.query(Message).filter(Message.id == message_id, Message.recipient == username).first()
    if not msg or msg.is_read:
        return
    msg.is_read = True
    db.commit()
    await broadcaster.publish({"type": "read", "message_id": message_id, "recipient": username, "sender": msg.sender})


@router.get("/messages", response_model=list[MessageResponse])
def get_messages(db: Session = Depends(get_db), username: str = Depends(require_auth)):
    messages = db.query(Message).filter(
        (Message.sender == username) | (Message.recipient == username)
    ).order_by(Message.created_at).all()
    return [
        MessageResponse(
            id=m.id, sender=m.sender, recipient=m.recipient,
            content=decrypt_safe(m.ciphertext), emoji=m.emoji, created_at=m.created_at, is_read=m.is_read,
        )
        for m in messages
    ]


@router.get("/stream")
async def stream(
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
    token: str = None,
) -> EventSourceResponse:
    """SSE stream — client holds open connection, receives messages in real time."""
    async def event_generator():
        async for msg in broadcaster.stream(username):
            yield {"data": json.dumps(msg)}

    return EventSourceResponse(event_generator())


@router.get("/users/online")
def get_online_users(username: str = Depends(require_auth)):
    return {"online_users": broadcaster.online_users()}


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _group_members(db: Session, group_id: int) -> list[str]:
    return [m.username for m in db.query(GroupMember).filter(GroupMember.group_id == group_id).all()]


def _group_msg_response(msg: GroupMessage, db: Session) -> GroupMessageResponse:
    read_by = [r.username for r in db.query(GroupMessageRead).filter(GroupMessageRead.message_id == msg.id).all()]
    return GroupMessageResponse(
        id=msg.id, group_id=msg.group_id, sender=msg.sender,
        content=decrypt(msg.ciphertext), created_at=msg.created_at, read_by=read_by,
    )


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    all_members = list({username} | set(body.members))
    for m in all_members:
        if not db.query(User).filter(User.username == m).first():
            raise HTTPException(status_code=404, detail=f"user '{m}' not found")

    group = Group(name=body.name, created_by=username)
    db.add(group)
    db.commit()
    db.refresh(group)

    for m in all_members:
        db.add(GroupMember(group_id=group.id, username=m))
    db.commit()

    event = {"type": "group_created", "group": {"id": group.id, "name": group.name, "created_by": username, "members": all_members}}
    await broadcaster.publish_to_users(event, all_members)
    return GroupResponse(id=group.id, name=group.name, created_by=username, members=all_members)


@router.get("/groups", response_model=list[GroupResponse])
def get_groups(db: Session = Depends(get_db), username: str = Depends(require_auth)):
    memberships = db.query(GroupMember).filter(GroupMember.username == username).all()
    result = []
    for m in memberships:
        group = db.query(Group).filter(Group.id == m.group_id).first()
        if group:
            result.append(GroupResponse(id=group.id, name=group.name, created_by=group.created_by, members=_group_members(db, group.id)))
    return result


@router.post("/groups/{group_id}/messages", response_model=GroupMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_group_message(
    group_id: int,
    body: SendGroupMessageRequest,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.username == username).first():
        raise HTTPException(status_code=403, detail="not a member")

    msg = GroupMessage(group_id=group_id, sender=username, ciphertext=encrypt(body.content))
    db.add(msg)
    db.commit()
    db.refresh(msg)

    members = _group_members(db, group_id)
    response = GroupMessageResponse(id=msg.id, group_id=group_id, sender=username, content=body.content, created_at=msg.created_at, read_by=[])
    event = {"type": "group_message", "message": response.model_dump(mode="json")}
    await broadcaster.publish_to_users(event, members)
    return response


@router.get("/groups/{group_id}/messages", response_model=list[GroupMessageResponse])
def get_group_messages(
    group_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.username == username).first():
        raise HTTPException(status_code=403, detail="not a member")
    msgs = db.query(GroupMessage).filter(GroupMessage.group_id == group_id).order_by(GroupMessage.created_at).all()
    return [_group_msg_response(m, db) for m in msgs]


@router.post("/groups/{group_id}/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_group_message_read(
    group_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
):
    if not db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.username == username).first():
        raise HTTPException(status_code=403, detail="not a member")
    already = db.query(GroupMessageRead).filter(GroupMessageRead.message_id == message_id, GroupMessageRead.username == username).first()
    if already:
        return
    db.add(GroupMessageRead(message_id=message_id, username=username))
    db.commit()

    members = _group_members(db, group_id)
    await broadcaster.publish_to_users({"type": "group_read", "message_id": message_id, "group_id": group_id, "username": username}, members)
