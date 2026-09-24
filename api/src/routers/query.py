import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from ..models.query import QueryRequest, QueryResponse
from ..services.query_service import QueryService
from ..services.configservice import load_config
from ..telemetry import trace_span

router = APIRouter()
config = load_config()

_service = QueryService(config)

def get_query_service() -> QueryService:
    return _service


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, service: QueryService = Depends(get_query_service)):
    try:
        with trace_span("query", query=request.query, search_type=request.search_type.value):
            return service.query(request)
    except Exception as exc:        
        raise HTTPException(status_code=502, detail="query backend failed") from exc


@router.post("/query/stream")
def query_stream(request: QueryRequest, service: QueryService = Depends(get_query_service)):
    def events():
        try:
            with trace_span("query.stream", search_type=request.search_type.value):
                for event, payload in service.stream(request):
                    if event == "completed":
                        payload = payload.model_dump()
                    yield f"event: {event}\ndata: {json.dumps({'text': payload} if event == 'answer_delta' else payload)}\n\n"
        except Exception:
            yield 'event: error\ndata: {"detail":"query backend failed"}\n\n'
    return StreamingResponse(events(), media_type="text/event-stream")
