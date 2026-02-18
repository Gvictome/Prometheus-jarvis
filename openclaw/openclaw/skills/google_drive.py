"""Google Drive skill — create folders, list files, upload files via Drive REST API."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, ClassVar

import httpx

from openclaw.config import settings
from openclaw.gateway.schemas import SkillContext, SkillResponse
from openclaw.skills.base import BaseSkill

logger = logging.getLogger(__name__)

_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
_MULTIPART_BOUNDARY = "boundary_openclaw_drive"


class GoogleDriveSkill(BaseSkill):
    name: ClassVar[str] = "google_drive"
    description: ClassVar[str] = (
        "Create folders, list files, and upload files to Google Drive"
    )
    min_tier: ClassVar[int] = 1
    examples: ClassVar[list[str]] = [
        "create a folder called Projects in Google Drive",
        "list my Google Drive files",
        "upload report.pdf to Google Drive",
    ]

    # ── Tool schema ───────────────────────────────────────

    @classmethod
    def get_tool_schema(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "google_drive",
                "description": (
                    "Interact with Google Drive: create folders, list recent files, "
                    "or upload a local file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create_folder", "list_files", "upload_file"],
                            "description": "Action to perform on Google Drive.",
                        },
                        "name": {
                            "type": "string",
                            "description": (
                                "Folder or destination file name. "
                                "Required for create_folder; optional for upload_file."
                            ),
                        },
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Absolute path to the local file to upload. "
                                "Required for upload_file."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute_tool(self, action: str, **kwargs: Any) -> str:
        """Dispatch a tool call from the agentic loop and return plain text."""
        if not settings.GOOGLE_DRIVE_CREDENTIALS_JSON:
            return "Error: Google Drive is not configured (GOOGLE_DRIVE_CREDENTIALS_JSON missing)."
        if action == "create_folder":
            result = await self._create_folder(kwargs.get("name") or "Untitled Folder")
        elif action == "list_files":
            result = await self._list_files()
        elif action == "upload_file":
            file_path = kwargs.get("file_path", "")
            result = await self._upload_file(file_path, name=kwargs.get("name"))
        else:
            return f"Unknown Google Drive action: {action}"
        return result.text

    # ── Auth ──────────────────────────────────────────────

    def _get_token_sync(self) -> str:
        """Load service account credentials and return a fresh access token (sync)."""
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        if not settings.GOOGLE_DRIVE_CREDENTIALS_JSON:
            raise ValueError("GOOGLE_DRIVE_CREDENTIALS_JSON is not configured")

        info = json.loads(settings.GOOGLE_DRIVE_CREDENTIALS_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[_DRIVE_SCOPE]
        )
        creds.refresh(Request())
        return creds.token

    async def _authorized_client(self) -> httpx.AsyncClient:
        """Return an httpx.AsyncClient with a valid Bearer token."""
        token = await asyncio.to_thread(self._get_token_sync)
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    # ── Intent dispatch ───────────────────────────────────

    async def execute(self, ctx: SkillContext) -> SkillResponse:
        if not settings.GOOGLE_DRIVE_CREDENTIALS_JSON:
            return self._error(
                "Google Drive is not configured. "
                "Set GOOGLE_DRIVE_CREDENTIALS_JSON in your environment."
            )

        text_lower = ctx.message.content.lower()

        if any(w in text_lower for w in ("list", "show", "ls")):
            return await self._list_files()

        if any(w in text_lower for w in ("upload", "save", "put")):
            # Best-effort: extract a file path or name from the message
            name = ctx.match.entities.get("name", "").strip()
            file_path = ctx.match.entities.get("file_path", "").strip()
            return await self._upload_file(file_path, name=name or None)

        # Default: create_folder
        name = ctx.match.entities.get("name", "").strip()
        if not name:
            for marker in ("folder called ", "folder named ", "folder "):
                idx = text_lower.find(marker)
                if idx != -1:
                    name = ctx.message.content[idx + len(marker) :].strip().strip("\"'")
                    break

        if not name:
            return self._error("What should I name the folder?")

        return await self._create_folder(name)

    # ── Actions ───────────────────────────────────────────

    async def _create_folder(self, name: str) -> SkillResponse:
        """POST /drive/v3/files with folder mimeType."""
        try:
            client = await self._authorized_client()
            async with client:
                body: dict[str, Any] = {
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if settings.GOOGLE_DRIVE_DEFAULT_PARENT_ID:
                    body["parents"] = [settings.GOOGLE_DRIVE_DEFAULT_PARENT_ID]

                resp = await client.post(
                    _FILES_URL,
                    json=body,
                    params={"fields": "id,name,webViewLink"},
                )
                resp.raise_for_status()
                data = resp.json()
                folder_id = data.get("id", "")
                link = data.get("webViewLink", "")
                return self._reply(
                    f"Created folder **{name}** in Google Drive.\n"
                    f"ID: `{folder_id}`\nLink: {link}"
                )
        except ValueError as exc:
            return self._error(str(exc))
        except httpx.HTTPStatusError as exc:
            logger.exception("Drive API error creating folder")
            return self._error(f"Google Drive API error: {exc.response.status_code}")
        except Exception:
            logger.exception("Failed to create Google Drive folder")
            return self._error("Failed to create folder in Google Drive.")

    async def _list_files(self) -> SkillResponse:
        """GET /drive/v3/files — top 10 by modifiedTime."""
        try:
            client = await self._authorized_client()
            async with client:
                resp = await client.get(
                    _FILES_URL,
                    params={
                        "pageSize": 10,
                        "orderBy": "modifiedTime desc",
                        "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
                    },
                )
                resp.raise_for_status()
                files = resp.json().get("files", [])

            if not files:
                return self._reply("No files found in Google Drive.")

            lines = ["**Recent Google Drive files:**\n"]
            for f in files:
                icon = (
                    "\U0001f4c1"
                    if f.get("mimeType") == "application/vnd.google-apps.folder"
                    else "\U0001f4c4"
                )
                link = f.get("webViewLink", "")
                fname = f.get("name", "untitled")
                lines.append(f"{icon} [{fname}]({link})" if link else f"{icon} {fname}")

            return self._reply("\n".join(lines))
        except ValueError as exc:
            return self._error(str(exc))
        except httpx.HTTPStatusError as exc:
            logger.exception("Drive API error listing files")
            return self._error(f"Google Drive API error: {exc.response.status_code}")
        except Exception:
            logger.exception("Failed to list Google Drive files")
            return self._error("Failed to list files from Google Drive.")

    async def _upload_file(
        self, file_path: str, name: str | None = None
    ) -> SkillResponse:
        """Upload a local file using Drive multipart upload."""
        if not file_path:
            return self._error(
                "Please provide the path of the file to upload, e.g. "
                "\"upload /tmp/report.pdf to Google Drive\"."
            )

        path = Path(file_path)
        if not path.exists():
            return self._error(f"File not found: {file_path}")

        file_name = name or path.name
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        try:
            client = await self._authorized_client()
            async with client:
                metadata: dict[str, Any] = {"name": file_name}
                if settings.GOOGLE_DRIVE_DEFAULT_PARENT_ID:
                    metadata["parents"] = [settings.GOOGLE_DRIVE_DEFAULT_PARENT_ID]

                meta_bytes = json.dumps(metadata).encode()
                file_bytes = path.read_bytes()

                # Build multipart/related body
                boundary = _MULTIPART_BOUNDARY
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                ).encode() + meta_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode() + file_bytes + f"\r\n--{boundary}--".encode()

                resp = await client.post(
                    _UPLOAD_URL,
                    content=body,
                    headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                    params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                )
                resp.raise_for_status()
                data = resp.json()
                file_id = data.get("id", "")
                link = data.get("webViewLink", "")
                return self._reply(
                    f"Uploaded **{file_name}** to Google Drive.\n"
                    f"ID: `{file_id}`\nLink: {link}"
                )
        except ValueError as exc:
            return self._error(str(exc))
        except httpx.HTTPStatusError as exc:
            logger.exception("Drive API error uploading file")
            return self._error(f"Google Drive API error: {exc.response.status_code}")
        except Exception:
            logger.exception("Failed to upload file to Google Drive")
            return self._error("Failed to upload file to Google Drive.")
