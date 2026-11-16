from typing import Any

from fastapi import HTTPException, status

from utils.db import get_connection, row_to_dict
from utils.security import new_token, verify_password


_TOKENS: dict[str, dict[str, Any]] = {}


def login(username: str, password: str) -> dict[str, Any]:
    with get_connection() as conn:
        account = row_to_dict(conn.execute("SELECT * FROM accounts WHERE username = ?", (username,)).fetchone())
    if not account or not account["enabled"] or not verify_password(password, account["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = new_token()
    public_account = _public_account(account)
    _TOKENS[token] = public_account
    return {"token": token, "account": public_account}


def logout(token: str) -> None:
    _TOKENS.pop(token, None)


def get_account_by_token(token: str) -> dict[str, Any] | None:
    return _TOKENS.get(token)


def require_admin(account: dict[str, Any]) -> None:
    if account.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")


def _public_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": account["id"],
        "username": account["username"],
        "role": account["role"],
        "enabled": bool(account["enabled"]),
        "created_at": account["created_at"],
    }
