import os
import time
import queue
import threading
import logging
import httpx
from pathlib import Path

logger = logging.getLogger("kizuna.cloud_db")

BUCKET_NAME = os.environ.get("SUPABASE_BUCKET_NAME", "kizuna-db")
DB_FILENAME = "kizuna.db"

def _get_clean_project_ref() -> str | None:
    ref = os.environ.get("SUPABASE_PROJECT_REF")
    if not ref:
        return None
    return ref.strip().strip("'\"")

def _get_clean_service_key() -> str | None:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        return None
    key = key.strip().strip("'\"")
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key

# Background worker queue for uploads
_upload_queue = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()

def _get_supabase_url() -> str | None:
    ref = _get_clean_project_ref()
    key = _get_clean_service_key()
    if not ref or not key:
        return None
    bucket = BUCKET_NAME.strip().strip("'\"")
    return f"https://{ref}.supabase.co/storage/v1/object/{bucket}/{DB_FILENAME}"

def download_db(local_path: str | Path) -> bool:
    """
    Downloads the database file from Supabase Storage.
    Returns True if successfully downloaded, False otherwise.
    """
    url = _get_supabase_url()
    key = _get_clean_service_key()
    if not url or not key:
        logger.info("Cloud database sync: Disabled (SUPABASE_PROJECT_REF/SERVICE_ROLE_KEY not set).")
        return False

    logger.info("Cloud database sync: Attempting to download database file from cloud storage...")
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                # Ensure parent directory exists
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"Cloud database sync: Successfully downloaded database to {local_path} ({len(response.content)} bytes).")
                return True
            elif response.status_code == 404 or response.status_code == 400:
                logger.info("Cloud database sync: Database file not found in storage bucket. Will be initialized on startup.")
            else:
                logger.warning(f"Cloud database sync: Failed to download database file. HTTP Status: {response.status_code}. Response: {response.text}")
    except Exception as e:
        logger.error(f"Cloud database sync: Unexpected error during database download: {e}")
        
    return False

def perform_upload(local_path: str | Path) -> bool:
    """
    Synchronously uploads the local database file to Supabase Storage.
    """
    url = _get_supabase_url()
    key = _get_clean_service_key()
    if not url or not key:
        return False

    local_path = Path(local_path)
    if not local_path.exists():
        logger.warning(f"Cloud database sync: Local database file {local_path} does not exist. Cannot upload.")
        return False

    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "x-upsert": "true",
        "Content-Type": "application/x-sqlite3"
    }

    logger.info("Cloud database sync: Starting database upload to Supabase Storage...")
    try:
        with open(local_path, "rb") as f:
            data = f.read()

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, content=data)
            if response.status_code == 200:
                logger.info(f"Cloud database sync: Successfully uploaded database to storage bucket ({len(data)} bytes).")
                return True
            else:
                logger.error(f"Cloud database sync: Failed to upload database file. HTTP Status: {response.status_code}. Response: {response.text}")
    except Exception as e:
        logger.error(f"Cloud database sync: Unexpected error during database upload: {e}")

    return False

def _upload_worker():
    """
    Background worker thread that processes uploads from the queue.
    Includes debouncing to group consecutive rapid write operations.
    """
    while True:
        local_path = _upload_queue.get()
        if local_path is None:
            _upload_queue.task_done()
            break
            
        try:
            # Wait a short duration to debounce subsequent changes
            time.sleep(0.5)
            # Drain queue to only upload the absolute latest state
            while not _upload_queue.empty():
                try:
                    next_path = _upload_queue.get_nowait()
                    if next_path is None:
                        # Put it back to exit the thread on the next iteration
                        _upload_queue.put(None)
                    else:
                        local_path = next_path
                    _upload_queue.task_done()
                except queue.Empty:
                    break
            
            perform_upload(local_path)
        except Exception as e:
            logger.error(f"Cloud database sync: Error in upload background worker: {e}")
        finally:
            _upload_queue.task_done()

def trigger_upload(local_path: str | Path):
    """
    Triggers an asynchronous upload of the database file.
    Queues the request to be processed by a background worker thread.
    """
    global _worker_started
    ref = _get_clean_project_ref()
    key = _get_clean_service_key()
    if not ref or not key:
        return

    # Start the worker thread lazily on first trigger
    if not _worker_started:
        with _worker_lock:
            if not _worker_started:
                worker_thread = threading.Thread(target=_upload_worker, name="CloudDBUploadWorker", daemon=True)
                worker_thread.start()
                _worker_started = True
                logger.info("Cloud database sync: Background upload worker thread started.")

    _upload_queue.put(local_path)
