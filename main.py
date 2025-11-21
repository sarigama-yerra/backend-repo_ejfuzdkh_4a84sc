import os
import hashlib
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents, update_document

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Utility
# -----------------------------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# -----------------------------
# Models
# -----------------------------
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class CreateDirectChatRequest(BaseModel):
    user_id: str
    other_user_id: str


class CreateGroupChatRequest(BaseModel):
    name: str
    member_ids: List[str]
    admin_ids: Optional[List[str]] = None


class SendMessageRequest(BaseModel):
    room_id: str
    sender_id: str
    content: str


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "ChatMind API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"⚠️ {str(e)[:80]}"
    return response


# Auth
@app.post("/auth/signup")
def signup(payload: SignupRequest):
    # check existing
    existing = db.user.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "avatar_url": None,
        "bio": "",
        "is_active": True,
    }
    user_id = create_document("user", user_doc)
    return {"user_id": user_id}


@app.post("/auth/login")
def login(payload: LoginRequest):
    user = db.user.find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # simple token = user id for demo
    return {
        "token": str(user["_id"]),
        "user": {
            "id": str(user["_id"]),
            "name": user.get("name"),
            "email": user.get("email"),
            "avatar_url": user.get("avatar_url"),
            "bio": user.get("bio", ""),
        },
    }


# User search and profile
@app.get("/users/search")
def search_users(q: str = "", limit: int = 20):
    query = {}
    if q:
        query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]}
    results = db.user.find(query).limit(min(limit, 50))
    users = [{"id": str(u["_id"]), "name": u.get("name"), "email": u.get("email"), "avatar_url": u.get("avatar_url") } for u in results]
    return {"users": users}


@app.get("/users/{user_id}")
def get_user(user_id: str):
    user = db.user.find_one({"_id": oid(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": str(user["_id"]), "name": user.get("name"), "email": user.get("email"), "avatar_url": user.get("avatar_url"), "bio": user.get("bio", "")}


@app.patch("/users/{user_id}")
def update_user(user_id: str, payload: UpdateProfileRequest):
    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
        return {"updated": False}
    modified = update_document("user", {"_id": oid(user_id)}, update)
    if not modified:
        raise HTTPException(status_code=404, detail="User not found")
    return {"updated": True}


# Chats
@app.post("/chats/direct")
def create_direct_chat(payload: CreateDirectChatRequest):
    uid1, uid2 = payload.user_id, payload.other_user_id
    if uid1 == uid2:
        raise HTTPException(status_code=400, detail="Cannot create chat with self")
    existing = db.chatroom.find_one({
        "type": "direct",
        "members": {"$all": [uid1, uid2]},
    })
    if existing:
        return {"room_id": str(existing["__id"]) if "__id" in existing else str(existing["_id"]) }
    room_doc = {
        "name": None,
        "type": "direct",
        "members": [uid1, uid2],
        "admins": [],
    }
    room_id = create_document("chatroom", room_doc)
    return {"room_id": room_id}


@app.post("/chats/group")
def create_group_chat(payload: CreateGroupChatRequest):
    if not payload.member_ids:
        raise HTTPException(status_code=400, detail="Members required")
    room_doc = {
        "name": payload.name,
        "type": "group",
        "members": payload.member_ids,
        "admins": payload.admin_ids or [],
    }
    room_id = create_document("chatroom", room_doc)
    return {"room_id": room_id}


@app.get("/chats/{user_id}")
def list_user_chats(user_id: str):
    rooms = db.chatroom.find({"members": user_id}).sort("updated_at", -1)
    res = []
    for r in rooms:
        res.append({
            "id": str(r["_id"]),
            "name": r.get("name"),
            "type": r.get("type"),
            "members": r.get("members", []),
            "admins": r.get("admins", []),
        })
    return {"rooms": res}


@app.get("/messages/{room_id}")
def get_messages(room_id: str, limit: int = 50):
    msgs = db.message.find({"room_id": room_id}).sort("created_at", -1).limit(min(limit, 200))
    res = []
    for m in msgs:
        res.append({
            "id": str(m["_id"]),
            "room_id": m.get("room_id"),
            "sender_id": m.get("sender_id"),
            "content": m.get("content"),
            "type": m.get("type", "text"),
            "created_at": m.get("created_at"),
        })
    return {"messages": list(reversed(res))}


@app.post("/messages")
def send_message(payload: SendMessageRequest):
    # ensure room exists
    room = db.chatroom.find_one({"_id": oid(payload.room_id)})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    msg_id = create_document("message", {
        "room_id": payload.room_id,
        "sender_id": payload.sender_id,
        "content": payload.content,
        "type": "text",
    })
    # update room updated_at
    update_document("chatroom", {"_id": oid(payload.room_id)}, {})
    # broadcast via websocket if connected
    manager.broadcast_to_room(payload.room_id, {
        "type": "message",
        "payload": {
            "id": msg_id,
            "room_id": payload.room_id,
            "sender_id": payload.sender_id,
            "content": payload.content,
        }
    })
    return {"message_id": msg_id}


# -----------------------------
# WebSocket Manager
# -----------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {}

    async def connect(self, room_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(room_id, []).append(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket):
        conns = self.active_connections.get(room_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and room_id in self.active_connections:
            del self.active_connections[room_id]

    async def send_json(self, websocket: WebSocket, data: dict):
        await websocket.send_json(data)

    def broadcast_to_room(self, room_id: str, data: dict):
        # schedule sending without awaiting (fire-and-forget)
        import asyncio
        conns = list(self.active_connections.get(room_id, []))
        for ws in conns:
            asyncio.create_task(self._safe_send(ws, data))

    async def _safe_send(self, ws: WebSocket, data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass


manager = ConnectionManager()


@app.websocket("/ws/rooms/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(room_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back if clients send messages directly
            await manager.send_json(websocket, {"type": "echo", "payload": data})
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
