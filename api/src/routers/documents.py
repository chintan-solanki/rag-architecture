from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status, Header
from ..models.documents import DocumentAccepted
from ..services.ingestion_service import IngestionService
from common.helpers.configservice import load_config


SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent

config = load_config('api/config/config.yml')
fetched_dir = Path(config['staging']['fetched_dir_path'])

_service = IngestionService(config, fetched_dir)

router = APIRouter()

@router.post("/documents", response_model=DocumentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def documents(file: UploadFile | None = File(default=None), url: str | None = Form(default=None), x_client_id: Annotated[str | None, Header()] = None):

    if (file is None) == (url is None):
        raise HTTPException(status_code=422, detail="provide exactly one PDF file or URL")
    try:
        ingestion_id = await _service.accept_upload(file, x_client_id) if file is not None else _service.accept_url(url or "", x_client_id)
    except ValueError as exc:
        print(exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        print(exc)
        raise HTTPException(status_code=502, detail="unable to hand off document") from exc
    
    return DocumentAccepted(ingestion_id=ingestion_id)

@router.get('/documents/events')
def events(document_id: str, x_client_id: Annotated[str | None, Header()] = None):
    
    return