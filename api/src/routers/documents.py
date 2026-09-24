from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from ..models.documents import DocumentAccepted
from ..services.ingestion_service import IngestionService
from ..services.configservice import load_config

config = load_config()
_service = IngestionService(config)

router = APIRouter()

@router.post("/documents", response_model=DocumentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def documents(file: UploadFile | None = File(default=None), url: str | None = Form(default=None)):
    if (file is None) == (url is None):
        raise HTTPException(status_code=422, detail="provide exactly one PDF file or URL")
    try:
        document_id = await _service.accept_upload(file) if file is not None else _service.accept_url(url or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="unable to hand off document") from exc
    return DocumentAccepted(document_id=document_id)
