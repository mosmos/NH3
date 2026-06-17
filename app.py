"""
NH DWG to SDE — FastAPI entry point.
Run: uvicorn app:app --host 0.0.0.0 --port 8000
"""
import importlib
import logging
import os
import time
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import parcel_writer

importlib.reload(parcel_writer)

from config import DWG_ROOT, SDE_CONNECTION
from database_updater import update_status_teina
from database_writer import verify_inserted_record, write_to_mapot_hesder


class DailyDateFileHandler(logging.Handler):
    def __init__(self, log_dir: str, encoding: str = "utf-8"):
        super().__init__()
        self.log_dir = log_dir
        self.encoding = encoding
        self.current_date = date.today()
        self._file_handler = logging.FileHandler(
            self._build_log_path(self.current_date),
            encoding=self.encoding,
        )

    def _build_log_path(self, day: date) -> str:
        return os.path.join(self.log_dir, f"{day.isoformat()}.log")

    def setFormatter(self, fmt):
        super().setFormatter(fmt)
        self._file_handler.setFormatter(fmt)

    def emit(self, record):
        today = date.today()
        if today != self.current_date:
            self._file_handler.close()
            self.current_date = today
            self._file_handler = logging.FileHandler(
                self._build_log_path(self.current_date),
                encoding=self.encoding,
            )
            if self.formatter:
                self._file_handler.setFormatter(self.formatter)

        self._file_handler.emit(record)

    def close(self):
        try:
            self._file_handler.close()
        finally:
            super().close()


LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
file_handler = DailyDateFileHandler(LOG_DIR)
stream_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[stream_handler, file_handler],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="NH DWG to SDE", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    client_host = request.client.host if request.client else "unknown"

    logger.info(
        "Request started method=%s path=%s client=%s",
        request.method,
        request.url.path,
        client_host,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "Request failed method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Request completed method=%s path=%s status_code=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


class ProcessRequest(BaseModel):
    id_hesder: str
    k_sug_mapa: int          # 0, 1, or 2
    dwg_file_name: str
    mishtamesh: Optional[str] = None


class ProcessResponse(BaseModel):
    success: bool
    id_teina: Optional[int] = None
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/process-dwg", response_model=ProcessResponse)
def process_dwg(req: ProcessRequest):
    # --- input validation ---
    try:
        int(req.id_hesder)
    except ValueError:
        raise HTTPException(status_code=422, detail="id_hesder must be numeric")

    if req.k_sug_mapa not in (0, 1, 2):
        raise HTTPException(status_code=422, detail="k_sug_mapa must be 0, 1, or 2")

    dwg_path = os.path.join(DWG_ROOT, req.dwg_file_name)
    if not os.path.exists(dwg_path):
        raise HTTPException(status_code=422, detail=f"DWG file not found: {dwg_path}")

    logger.info(
        "Starting job — id_hesder=%s k_sug_mapa=%s dwg=%s",
        req.id_hesder, req.k_sug_mapa, dwg_path,
    )

    # --- insert submission record (status=1 Started) ---
    new_id_teina = write_to_mapot_hesder(
        sde_connection=SDE_CONNECTION,
        id_hesder=req.id_hesder,
        k_sug_mapa=req.k_sug_mapa,
        dwg_path=dwg_path,
        mishtamesh=req.mishtamesh,
    )
    if new_id_teina is None:
        raise HTTPException(status_code=500, detail="Failed to create submission record")

    logger.info("Submission record created — id_teina=%s", new_id_teina)

    # --- process DWG → SDE ---
    try:
        success = parcel_writer.process_dwg_to_sde(
            dwg_path=dwg_path,
            id_hesder=req.id_hesder,
            k_sug_mapa=req.k_sug_mapa,
            sde_connection=SDE_CONNECTION,
        )
    except Exception as exc:
        logger.exception("DWG processing raised an exception for id_teina=%s", new_id_teina)
        err_msg = str(exc)
        update_status_teina(SDE_CONNECTION, new_id_teina, 5, error_msg=err_msg)
        raise HTTPException(status_code=500, detail=f"DWG processing error: {err_msg}")

    if success:
        update_status_teina(SDE_CONNECTION, new_id_teina, 4)
        logger.info("Job completed — id_teina=%s", new_id_teina)
        return ProcessResponse(
            success=True,
            id_teina=new_id_teina,
            message="Processing completed successfully",
        )

    err_msg = "DWG processing failed — see server logs for details"
    update_status_teina(SDE_CONNECTION, new_id_teina, 5, error_msg=err_msg)
    return ProcessResponse(
        success=False,
        id_teina=new_id_teina,
        message=err_msg,
    )


@app.get("/api/status/{id_teina}")
def get_status(id_teina: int):
    record = verify_inserted_record(SDE_CONNECTION, id_teina)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No record for id_teina={id_teina}")

    status_text = {1: "Job Started", 4: "Completed Successfully", 5: "Error"}
    status_val = record.get("k_status_teina")
    return {
        "id_teina": id_teina,
        "k_status_teina": status_val,
        "status_text": status_text.get(status_val, str(status_val)),
        "id_hesder": record.get("id_hesder"),
        "k_sug_mapa": record.get("k_sug_mapa"),
        "version": record.get("version"),
        "dwg_path": record.get("dwg_path"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
