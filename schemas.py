from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    bio: Optional[str] = Field("", description="Short bio")
    is_active: bool = Field(True, description="Whether user is active")

class Chatroom(BaseModel):
    name: Optional[str] = Field(None, description="Room name for groups")
    type: str = Field(..., description="direct or group")
    members: List[str] = Field(default_factory=list, description="User IDs")
    admins: List[str] = Field(default_factory=list, description="Admin user IDs for groups")

class Message(BaseModel):
    room_id: str = Field(..., description="Chatroom ID")
    sender_id: str = Field(..., description="User ID of sender")
    content: str = Field(..., description="Message text content")
    type: str = Field("text", description="Message type")
