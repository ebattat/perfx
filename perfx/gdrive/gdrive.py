import json
import re
import urllib.request
from pathlib import Path

_CREDS_FILE = Path.home() / ".gdrive-server-credentials.json"


def _token() -> str:
    if not _CREDS_FILE.exists():
        raise EnvironmentError("Google Drive credentials not found at ~/.gdrive-server-credentials.json")
    creds = json.loads(_CREDS_FILE.read_text())
    token = creds.get("access_token")
    if not token:
        raise EnvironmentError("No access token found. Run /refresh-gdrive first.")
    return token


def _extract_id(value: str, kind: str = "file") -> str:
    """Extract file or folder ID from a URL or return as-is if already an ID."""
    if kind == "folder":
        m = re.search(r'folders/([a-zA-Z0-9_-]+)', value)
        if m:
            return m.group(1)
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', value)
    if m:
        return m.group(1)
    m = re.search(r'id=([a-zA-Z0-9_-]+)', value)
    if m:
        return m.group(1)
    return value


def _get(url: str) -> dict:
    token = _token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _get_raw(url: str) -> str:
    token = _token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="replace")


def list_gdrive_folder(folder_id: str) -> dict:
    """List all files in a Google Drive folder by folder ID or URL."""
    try:
        fid = _extract_id(folder_id, kind="folder")
        url = (
            f"https://www.googleapis.com/drive/v3/files"
            f"?q='{fid}'+in+parents"
            f"&fields=files(id,name,mimeType,size,modifiedTime)"
            f"&supportsAllDrives=true&includeItemsFromAllDrives=true&pageSize=100"
        )
        data = _get(url)
        files = data.get("files", [])
        return {"folder_id": fid, "count": len(files), "files": files}
    except Exception as e:
        return {"error": str(e)}


def read_gdrive(file_id: str, max_chars: int = 5000) -> dict:
    """Read a file from Google Drive by file ID or URL."""
    try:
        fid = _extract_id(file_id)

        # get metadata
        meta = _get(
            f"https://www.googleapis.com/drive/v3/files/{fid}"
            f"?fields=name,mimeType,size&supportsAllDrives=true"
        )
        name = meta.get("name", fid)
        mime = meta.get("mimeType", "")

        # export Google Workspace files as plain text
        if "google-apps" in mime:
            content = _get_raw(
                f"https://www.googleapis.com/drive/v3/files/{fid}/export?mimeType=text/plain"
            )
        else:
            content = _get_raw(
                f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media&supportsAllDrives=true"
            )

        return {
            "name": name,
            "file_id": fid,
            "mime_type": mime,
            "content": content[:max_chars],
            "truncated": len(content) > max_chars,
        }
    except Exception as e:
        return {"error": str(e)}


def search_gdrive(query: str, max_results: int = 20) -> dict:
    """Search for files in Google Drive by name or content."""
    try:
        encoded = urllib.parse.quote(query) if hasattr(urllib, 'parse') else query.replace(' ', '+')
        url = (
            f"https://www.googleapis.com/drive/v3/files"
            f"?q=fullText+contains+'{query}'+or+name+contains+'{query}'"
            f"&fields=files(id,name,mimeType,modifiedTime)"
            f"&supportsAllDrives=true&includeItemsFromAllDrives=true"
            f"&pageSize={max_results}"
        )
        data = _get(url)
        return {"query": query, "count": len(data.get("files", [])), "files": data.get("files", [])}
    except Exception as e:
        return {"error": str(e)}
