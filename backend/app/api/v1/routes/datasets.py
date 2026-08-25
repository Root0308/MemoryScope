import sqlite3

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.embeddings.provider import (
    EmbeddingGenerationError,
    EmbeddingModelLoadError,
)

from app.repositories.datasets import (
    delete_dataset,
    get_dataset,
    import_dataset,
    list_datasets,
    list_memories,
)
from app.schemas.datasets import (
    DatasetImport,
    DatasetListResponse,
    DatasetSummary,
    MAX_FILE_BYTES,
    MemoryPageResponse,
)
from app.schemas.search import (
    BM25SearchResponse,
    CompareSearchRequest,
    CompareSearchResponse,
    DenseSearchResponse,
    HybridSearchResponse,
    SearchRequest,
)
from app.search.bm25 import DatasetNotFoundError, search_bm25
from app.search.compare import DatasetSnapshotChangedError, search_compare
from app.search.dense import EmptyDatasetError, EmbeddingPersistenceError
from app.search.hybrid import search_hybrid


router = APIRouter(prefix="/datasets", tags=["datasets"])


def _validation_detail(error: ValidationError) -> dict[str, object]:
    errors = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "$"
        message = item["msg"]
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        errors.append(
            {
                "path": location,
                "message": message,
                "code": item["type"],
            }
        )

    invalid_json = any(item["type"] == "json_invalid" for item in error.errors())
    return {
        "code": "invalid_json" if invalid_json else "validation_error",
        "message": (
            "The request body is not valid JSON."
            if invalid_json
            else "The dataset does not match the MemoryScope 0.1 schema."
        ),
        "errors": errors,
    }


async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail={
                        "code": "file_too_large",
                        "message": "JSON file exceeds the 20 MB limit.",
                        "errors": [],
                    },
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "file_too_large",
                    "message": "JSON file exceeds the 20 MB limit.",
                    "errors": [],
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/import",
    response_model=DatasetSummary,
    status_code=status.HTTP_201_CREATED,
)
async def import_dataset_route(request: Request) -> DatasetSummary:
    body = await _read_limited_body(request)
    try:
        payload = DatasetImport.model_validate_json(body)
    except ValidationError as error:
        invalid_json = any(item["type"] == "json_invalid" for item in error.errors())
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
                if invalid_json
                else status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=_validation_detail(error),
        ) from error

    try:
        dataset = import_dataset(
            request.app.state.settings.database_path,
            payload,
        )
        request.app.state.bm25_cache.clear()
        return dataset
    except sqlite3.DatabaseError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "database_error",
                "message": "The dataset transaction was rolled back.",
                "errors": [],
            },
        ) from error


@router.get("", response_model=DatasetListResponse)
async def list_datasets_route(request: Request) -> DatasetListResponse:
    items = list_datasets(request.app.state.settings.database_path)
    return DatasetListResponse(items=items, total=len(items))


@router.get("/{dataset_id}", response_model=DatasetSummary)
async def get_dataset_route(request: Request, dataset_id: str) -> DatasetSummary:
    dataset = get_dataset(request.app.state.settings.database_path, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


@router.get("/{dataset_id}/memories", response_model=MemoryPageResponse)
async def list_memories_route(
    request: Request,
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MemoryPageResponse:
    memory_page = list_memories(
        request.app.state.settings.database_path,
        dataset_id,
        page,
        page_size,
    )
    if memory_page is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return memory_page


@router.post(
    "/{dataset_id}/search",
    response_model=BM25SearchResponse | DenseSearchResponse | HybridSearchResponse,
)
async def search_dataset_route(
    request: Request,
    dataset_id: str,
    payload: SearchRequest,
) -> BM25SearchResponse | DenseSearchResponse | HybridSearchResponse:
    unsupported = sorted(set(payload.methods) - {"bm25", "dense", "hybrid"})
    if unsupported:
        requested = ", ".join(unsupported)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "method_not_supported",
                "message": (
                    f"Search method(s) {requested} are not supported in M5. "
                    "Supported methods are bm25, dense, and hybrid."
                ),
            },
        )
    if payload.methods not in (["bm25"], ["dense"], ["hybrid"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_methods",
                "message": (
                    "M5 accepts exactly one search method: bm25, dense, or hybrid."
                ),
            },
        )

    try:
        if payload.methods == ["bm25"]:
            return search_bm25(
                request.app.state.settings.database_path,
                dataset_id,
                payload.query,
                payload.top_k,
                request.app.state.bm25_cache,
            )
        if payload.methods == ["dense"]:
            return await run_in_threadpool(
                request.app.state.dense_search.search,
                request.app.state.settings.database_path,
                dataset_id,
                payload.query,
                payload.top_k,
            )
        return await run_in_threadpool(
            search_hybrid,
            request.app.state.settings.database_path,
            dataset_id,
            payload.query,
            payload.top_k,
            request.app.state.bm25_cache,
            request.app.state.dense_search,
        )
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    except EmptyDatasetError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "empty_dataset",
                "message": "Dense and Hybrid search require at least one memory.",
            },
        ) from error
    except EmbeddingModelLoadError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "model_initialization_failed",
                "message": str(error),
            },
        ) from error
    except EmbeddingGenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "embedding_generation_failed",
                "message": str(error),
            },
        ) from error
    except EmbeddingPersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "embedding_persistence_failed",
                "message": str(error),
            },
        ) from error


@router.post(
    "/{dataset_id}/search/compare",
    response_model=CompareSearchResponse,
)
async def compare_search_methods_route(
    request: Request,
    dataset_id: str,
    payload: CompareSearchRequest,
) -> CompareSearchResponse:
    try:
        return await run_in_threadpool(
            search_compare,
            request.app.state.settings.database_path,
            dataset_id,
            payload.query,
            payload.top_k,
            request.app.state.bm25_cache,
            request.app.state.dense_search,
        )
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    except EmptyDatasetError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "empty_dataset",
                "message": "Compare search requires at least one memory.",
            },
        ) from error
    except DatasetSnapshotChangedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "dataset_snapshot_changed",
                "message": str(error),
            },
        ) from error
    except EmbeddingModelLoadError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "model_initialization_failed",
                "message": str(error),
            },
        ) from error
    except EmbeddingGenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "embedding_generation_failed",
                "message": str(error),
            },
        ) from error
    except EmbeddingPersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "embedding_persistence_failed",
                "message": str(error),
            },
        ) from error


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset_route(request: Request, dataset_id: str) -> Response:
    deleted = delete_dataset(
        request.app.state.settings.database_path,
        dataset_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    request.app.state.bm25_cache.invalidate(dataset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
