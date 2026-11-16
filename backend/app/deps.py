from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from service.auth_service import get_account_by_token, require_admin


def current_account(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = authorization.removeprefix("Bearer ").strip()
    account = get_account_by_token(token)
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    return account


def admin_account(account: Annotated[dict, Depends(current_account)]) -> dict:
    require_admin(account)
    return account
