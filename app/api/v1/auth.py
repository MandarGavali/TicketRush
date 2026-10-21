from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthServiceDep, client_ip
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, service: AuthServiceDep) -> UserOut:
    return UserOut.model_validate(service.register(data))


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest, service: AuthServiceDep, ip: Annotated[str, Depends(client_ip)]
) -> TokenResponse:
    return service.login(data, client_ip=ip)
