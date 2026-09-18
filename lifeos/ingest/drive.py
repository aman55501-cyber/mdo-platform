"""Google Drive sync — pull the per-entity ERP exports into the local drop folder.

Delivery model (chosen with Aman): he drops each ERP's CSV/XLSX into a Google
Drive folder "LIFEOS Sales Exports" with a subfolder per entity. The 06:30 run
mirrors that folder into LIFEOS_ERP_DIR/<slug>/ so the erp_sales parser reads plain
local files — the parser never talks to Drive directly.

This is deliberately a thin, fault-isolated seam:
  - It needs a service account with read access to the folder (GOOGLE_SERVICE_ACCOUNT
    JSON in .env) and the folder id (LIFEOS_GDRIVE_FOLDER_ID). Both read lazily.
  - Until those are set it raises DriveNotConfigured, which the run records as a
    normal degraded state — the drop folder still works if files arrive another way
    (manual copy, rclone), so Sales is never blocked *on Drive specifically*.

The subfolder name is matched to an entity by slug (case/space-insensitive) or by a
label match, so "Dadu Developers/" maps to slug dadu_developers.
"""

from __future__ import annotations

import os
from pathlib import Path

from .entities import ENTITIES


class DriveNotConfigured(RuntimeError):
    pass


def _slug_for_folder(name: str) -> str | None:
    norm = name.strip().lower().replace(" ", "_").replace("-", "_")
    for e in ENTITIES:
        if norm == e.slug or name.strip().lower() == e.label.lower():
            return e.slug
    return None


def sync_to_drop(drop_root: Path) -> dict:
    """Mirror the Drive folder into drop_root/<slug>/. Returns a small report.
    Raises DriveNotConfigured when creds/folder are absent."""
    folder_id = os.environ.get("LIFEOS_GDRIVE_FOLDER_ID", "").strip()
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "").strip()
    if not folder_id or not sa_json:
        raise DriveNotConfigured(
            "set LIFEOS_GDRIVE_FOLDER_ID and GOOGLE_SERVICE_ACCOUNT in .env to enable Drive sync"
        )

    # Imported lazily so the whole app doesn't hard-depend on Google libs at boot.
    import json

    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    pulled: dict[str, int] = {}
    # list entity subfolders
    subfolders = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id,name)",
    ).execute().get("files", [])
    for sub in subfolders:
        slug = _slug_for_folder(sub["name"])
        if not slug:
            continue
        dest = drop_root / slug
        dest.mkdir(parents=True, exist_ok=True)
        files = service.files().list(
            q=f"'{sub['id']}' in parents and trashed=false",
            fields="files(id,name,mimeType)",
        ).execute().get("files", [])
        for f in files:
            if not f["name"].lower().endswith((".csv", ".xlsx", ".xlsm")):
                continue
            data = service.files().get_media(fileId=f["id"]).execute()
            (dest / f["name"]).write_bytes(data)
            pulled[slug] = pulled.get(slug, 0) + 1
    return {"folders": len(subfolders), "pulled": pulled}
