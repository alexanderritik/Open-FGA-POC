from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService, get_authorization_service
from app.db.database import get_db
from app.schemas.common import USER_ID_PATTERN
from app.schemas.tree import TreeNode
from app.services import tree_service
from app.services.exceptions import ResourceNotFoundError

router = APIRouter(tags=["tree"])


@router.get(
    "/clients/{client_id}/tree",
    response_model=TreeNode,
    summary="Get the authorization-pruned resource tree rooted at a client",
    description=(
        "Returns only the branches `user` can view (directly or by inheritance). "
        "A client that doesn't exist and a client the user has no visibility into "
        "produce the identical 404 — existence is not revealed to an unauthorized caller."
    ),
    responses={
        404: {"description": "Client not found or not visible to this user"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def get_client_tree(
    client_id: str,
    user: str = Query(..., pattern=USER_ID_PATTERN, examples=["user:parth"]),
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> TreeNode:
    try:
        return await tree_service.get_client_tree(db, auth, client_id, user)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/clients/{client_id}/tree/full",
    response_model=TreeNode,
    summary="Get the complete, unpruned resource tree rooted at a client",
    description=(
        "Returns every project, zone, and structure under the client with "
        "no authorization check and no `user` parameter — unlike "
        "GET /clients/{client_id}/tree, nothing here is filtered by who "
        "can view it. Intended for trusted/internal callers only."
    ),
    responses={
        404: {"description": "Client not found"},
        503: {"description": "Authorization engine unavailable"},
    },
)
async def get_client_tree_full(
    client_id: str,
    db: Session = Depends(get_db),
    auth: AuthorizationService = Depends(get_authorization_service),
) -> TreeNode:
    try:
        return await tree_service.get_client_tree_full(db, auth, client_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuthorizationServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
