from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.authorization.exceptions import (
    AuthorizationServiceUnavailableError,
    InvalidAuthorizationRequestError,
)
from app.authorization.service import AuthorizationService, get_authorization_service
from app.db.database import get_db
from app.schemas.authorization import CheckResponse, GrantRequest, GrantResponse, Permission, ResourceType
from app.schemas.common import SLUG_PATTERN, USER_ID_PATTERN
from app.services import access_service
from app.services.exceptions import ResourceNotFoundError

router = APIRouter(prefix="/authorization", tags=["authorization"])


@router.get(
    "/check",
    response_model=CheckResponse,
    summary="Check whether a user has a permission on a resource",
    responses={
        400: {"description": "Invalid request"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def check(
    user: str = Query(..., pattern=USER_ID_PATTERN, examples=["user:parth"]),
    resource_type: ResourceType = Query(...),
    resource_id: str = Query(..., pattern=SLUG_PATTERN),
    permission: Permission = Query("viewer"),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> CheckResponse:
    try:
        allowed = await access_service.check_access(auth, user, resource_type, resource_id, permission)
    except InvalidAuthorizationRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return CheckResponse(allowed=allowed)


@router.post(
    "/grant",
    response_model=GrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a user a permission on a resource",
    responses={
        404: {"description": "Resource does not exist"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def grant(
    payload: GrantRequest,
    response: Response,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> GrantResponse:
    try:
        created = await access_service.grant_access(
            db, auth, payload.user, payload.resource_type, payload.resource_id, payload.permission
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    return GrantResponse(
        user=payload.user,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        permission=payload.permission,
    )


@router.delete(
    "/grant",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a user's permission on a resource",
    responses={503: {"description": "Authorization engine unavailable"}},
)
async def revoke(
    user: str = Query(..., pattern=USER_ID_PATTERN, examples=["user:parth"]),
    resource_type: ResourceType = Query(...),
    resource_id: str = Query(..., pattern=SLUG_PATTERN),
    permission: Permission = Query("viewer"),
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> Response:
    try:
        await access_service.revoke_access(db, auth, user, resource_type, resource_id, permission)
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
