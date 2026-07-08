"""FastAPI-приложение демона: GET /health, POST /transcribe.

Коды ошибок соответствуют CONTRACT.md.
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from molva import audio
from molva.config import Config, load_config
from molva.service import BadRequestError, NotReadyError, MolvaService
from molva.transcriber.base import Transcriber
from molva.transcriber.stub import StubTranscriber

logger = logging.getLogger("molva.api")


class TranscribeRequest(BaseModel):
    path: str
    formats: list[str] = Field(default_factory=lambda: ["txt"])
    language: str = "ru"


class SegmentOut(BaseModel):
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    status: str = "done"
    source: str
    outputs: list[str]
    duration_sec: float
    segments: list[SegmentOut]


class HealthResponse(BaseModel):
    status: str
    backend: str
    model_loaded: bool
    version: str


class UploadTranscribeResponse(BaseModel):
    status: str = "done"
    language: str
    text: str
    segments: list[SegmentOut]


class ErrorResponse(BaseModel):
    error: str
    detail: str


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "detail": detail})


def _make_transcriber(cfg: Config) -> Transcriber:
    if cfg.backend == "gigaam":
        from molva.transcriber.gigaam import GigaAMTranscriber
        logger.info("Загружаю GigaAM-v3 (revision=%s)…", cfg.model_revision)
        t = GigaAMTranscriber(model_path=cfg.model_path, revision=cfg.model_revision)
        logger.info("Модель готова.")
        return t
    return StubTranscriber()


def _make_auth(api_key: str):
    """Возвращает FastAPI Depends-зависимость для проверки X-API-Key."""
    def check(x_api_key: str | None = Header(default=None)) -> None:
        if api_key and x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return Depends(check)


def create_app(service: MolvaService, api_key: str = "", cors_origins: tuple[str, ...] = ()) -> FastAPI:
    app = FastAPI(title="Molva", version="0.1.0")
    app.state.service = service

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Content-Type"],
        )

    auth = _make_auth(api_key)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        h = service.health()
        return HealthResponse(
            status=h.status, backend=h.backend, model_loaded=h.model_loaded, version=h.version
        )

    @app.post("/transcribe", response_model=TranscribeResponse, dependencies=[auth])
    def transcribe(req: TranscribeRequest) -> TranscribeResponse:
        result = service.transcribe(req.path, req.formats, req.language)
        return TranscribeResponse(
            source=result.source,
            outputs=result.outputs,
            duration_sec=result.duration_sec,
            segments=[SegmentOut(start=s.start, end=s.end, text=s.text) for s in result.segments],
        )

    @app.post("/transcribe/upload", response_model=UploadTranscribeResponse, dependencies=[auth])
    async def transcribe_upload(
        file: UploadFile = File(..., description="WAV/MP3/MP4 аудиофайл"),
        language: str = "ru",
        vad: bool = True,
    ) -> UploadTranscribeResponse:
        data = await file.read()
        segments = service.transcribe_bytes(data, language=language, use_vad=vad)
        text = " ".join(s.text for s in segments).strip()
        return UploadTranscribeResponse(
            language=language,
            text=text,
            segments=[SegmentOut(start=s.start, end=s.end, text=s.text) for s in segments],
        )

    @app.exception_handler(BadRequestError)
    def handle_bad_request(request: Request, exc: BadRequestError) -> JSONResponse:
        return _error_response(400, "bad_request", str(exc))

    @app.exception_handler(FileNotFoundError)
    def handle_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
        return _error_response(404, "file_not_found", str(exc))

    @app.exception_handler(audio.UnsupportedMediaError)
    def handle_unsupported(request: Request, exc: audio.UnsupportedMediaError) -> JSONResponse:
        return _error_response(415, "unsupported_media", str(exc))

    @app.exception_handler(audio.PreprocessingError)
    def handle_preprocessing(request: Request, exc: audio.PreprocessingError) -> JSONResponse:
        return _error_response(422, "preprocessing_failed", str(exc))

    @app.exception_handler(NotReadyError)
    def handle_not_ready(request: Request, exc: NotReadyError) -> JSONResponse:
        return _error_response(503, "not_ready", str(exc))

    @app.exception_handler(Exception)
    def handle_internal(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "internal_error", str(exc))

    return app


def build_default_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()
    transcriber = _make_transcriber(cfg)
    service = MolvaService(
        transcriber=transcriber,
        backend=cfg.backend,
        notify=cfg.notify,
        clipboard=cfg.clipboard,
    )
    return create_app(service, api_key=cfg.api_key, cors_origins=cfg.cors_origins)


def _setup_logging(cfg: Config) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = cfg.log_dir / "daemon.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    cfg = load_config()
    _setup_logging(cfg)
    logger.info("Запускаю демон на %s:%d (backend=%s)", cfg.host, cfg.port, cfg.backend)
    app = build_default_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_config=None)
