from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from ontherecord.schemas.user import DisplayName

Token = Annotated[str, StringConstraints(min_length=1, max_length=10_000)]


class AppleSignIn(BaseModel):
    identity_token: Token = Field(description="The JWT from ASAuthorizationAppleIDCredential")
    nonce: Token = Field(description="The raw nonce; its SHA-256 hex was sent to Apple")
    display_name: DisplayName | None = Field(
        None, description="Apple shares the name on the first sign-in only"
    )


class RefreshRequest(BaseModel):
    refresh_token: Token


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = Field(description="Single use: each refresh returns a new one")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
