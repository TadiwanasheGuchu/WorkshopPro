import uuid
from typing import Literal

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, Storage
from app.core.errors import NotFoundError
from app.integrations.storage import StorageError
from app.models import StoredFile
from app.services.inspections import authorise_file

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{file_id}",
    summary="Download a stored file",
    description=(
        "Streams the file after checking that the caller may see the record it belongs to. "
        "`variant=thumb` returns the thumbnail for photos."
    ),
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_file(
    file_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    storage: Storage,
    variant: Literal["full", "thumb"] = "full",
) -> Response:
    stored = db.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id, StoredFile.organisation_id == principal.organisation_id
        )
    )
    if stored is None:
        raise NotFoundError("File not found.")
    authorise_file(db, principal, stored)
    key = (
        stored.thumbnail_key if variant == "thumb" and stored.thumbnail_key else stored.storage_key
    )
    try:
        data = storage.get(key)
    except StorageError as exc:
        raise NotFoundError("File not available.") from exc
    return Response(
        content=data,
        media_type=stored.content_type,
        headers={
            # Private: never cached by shared proxies. Files are immutable, so browsers may
            # keep them for the session.
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )
