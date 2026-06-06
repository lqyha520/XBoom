import asyncio
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils import log, utils
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.branding.install import APP_SLUG, APP_BRAND, EXE_NAME, INSTALLER_NAME
from src.ai_write_x.version import get_version

router = APIRouter(prefix="/api/system", tags=["System Update"])

DEFAULT_UPDATE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "startup_check": True,
    "mandatory_update_enabled": True,
    "auto_update_on_startup": True,
    "auto_update_silent": True,
    "provider": "gitee_release",
    "gitee_owner": "lqyha520",
    "gitee_repo": "XBoom",
    "gitee_branch": "master",
    "gitee_release_path": "releases",
    "gitee_token": "",
    "github_owner": "lqyha520",
    "github_repo": "XBoom",
    "allow_prerelease": False,
    "manifest_url": "https://updates.bcxtech.cn/updates/version-policy.json",
    "manifest_asset_name": "version-policy.json",
    "installer_asset_name": INSTALLER_NAME,
    "installer_silent_args": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS",
    "restart_executable": EXE_NAME,
    "check_timeout_seconds": 15,
    "download_timeout_seconds": 600,
    "min_supported_version": "",
    "latest_version": "",
    "manual_download_url": "",
    "update_mirror_base": "https://updates.bcxtech.cn/updates",
    "prefer_mirror": True,
    "fallback_github": False,
}

_update_progress: Dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "error": "",
    "logs": [],
    "download_path": "",
    "helper_script": "",
    "log_file": "",
}

_download_lock = threading.Lock()


class UpdatePolicyResponse(BaseModel):
    enabled: bool
    startup_check: bool
    current_version: str
    latest_version: str
    min_supported_version: str
    has_update: bool
    force_update: bool
    can_update: bool
    download_url: str
    release_notes: str
    published_at: str = ""
    source: str = ""
    auto_update_on_startup: bool = True
    auto_update_silent: bool = True
    is_release_build: bool = False
    should_auto_update: bool = False


class UpdateRequest(BaseModel):
    download_url: Optional[str] = None


def _safe_version(value: str) -> Version:
    cleaned = str(value or "").strip().lstrip("vV")
    if not cleaned:
        raise InvalidVersion("empty version")
    return Version(cleaned)


def _is_version_less(left: str, right: str) -> bool:
    try:
        return _safe_version(left) < _safe_version(right)
    except InvalidVersion:
        def _parts(text: str) -> list[int]:
            return [int(part) if part.isdigit() else 0 for part in str(text).strip().lstrip("vV").split(".")]

        left_parts = _parts(left)
        right_parts = _parts(right)
        size = max(len(left_parts), len(right_parts))
        left_parts.extend([0] * (size - len(left_parts)))
        right_parts.extend([0] * (size - len(right_parts)))
        return left_parts < right_parts


def _merge_update_config() -> Dict[str, Any]:
    config = Config.get_instance().config or {}
    merged = dict(DEFAULT_UPDATE_CONFIG)
    merged.update(config.get("update", {}) or {})
    return merged


def _release_tag_version(item: dict) -> Version:
    tag = str(item.get("tag_name", "")).strip().lstrip("vV")
    try:
        return _safe_version(tag)
    except InvalidVersion:
        return Version("0")


def _select_release(data: list[dict], allow_prerelease: bool) -> Optional[dict]:
    """Gitee/GitHub 鍒楄〃椤哄簭涓嶄繚璇佹渶鏂板湪鍓嶏紝鎸?tag 鐗堟湰鍙峰彇鏈€澶с€?""
    candidates: list[dict] = []
    for item in data:
        if item.get("draft"):
            continue
        if not allow_prerelease and item.get("prerelease"):
            continue
        candidates.append(item)
    if not candidates:
        return None
    return max(candidates, key=_release_tag_version)


def _find_asset(assets: list[dict], preferred_name: str, suffix: str) -> Optional[dict]:
    preferred_name = (preferred_name or "").strip().lower()
    for asset in assets:
        if asset.get("name", "").strip().lower() == preferred_name:
            return asset
    for asset in assets:
        name = asset.get("name", "").strip().lower()
        if preferred_name and preferred_name in name:
            return asset
    for asset in assets:
        if asset.get("name", "").strip().lower().endswith(suffix):
            return asset
    return None


def _asset_download_url(asset: Optional[dict]) -> str:
    if not asset:
        return ""
    return str(asset.get("browser_download_url") or asset.get("url") or "").strip()


def _release_assets(release: dict) -> list[dict]:
    assets = release.get("assets")
    if isinstance(assets, list) and assets:
        return assets
    attach = release.get("attach_files") or release.get("attachments")
    if isinstance(attach, list):
        return attach
    return []


async def _fetch_json(url: str, timeout_seconds: int, headers: Optional[dict] = None) -> dict:
    request_headers = dict(headers or {})
    request_headers.setdefault("User-Agent", "AIWriteX-Updater")
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.get(url, headers=request_headers)
        response.raise_for_status()
        return response.json()


def _gitee_auth_params(settings: Dict[str, Any]) -> Dict[str, str]:
    token = str(settings.get("gitee_token") or os.environ.get("GITEE_TOKEN") or "").strip()
    if token:
        return {"access_token": token}
    return {}


def _gitee_auth_url(url: str, settings: Dict[str, Any]) -> str:
    if "gitee.com" not in (url or ""):
        return url
    params = _gitee_auth_params(settings)
    if not params:
        return url
    token = params["access_token"]
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}access_token={token}"


def _installer_filename(settings: Dict[str, Any]) -> str:
    return str(settings.get("installer_asset_name") or INSTALLER_NAME)


def _resolve_gitee_raw_urls(settings: Dict[str, Any]) -> Dict[str, str]:
    """Gitee 浠撳簱 raw 鐩撮摼锛坴ersion-policy + 瀹夎鍖咃紝閫傚悎灏忔枃浠舵垨 LFS锛夈€?""
    owner = str(settings.get("gitee_owner") or settings.get("github_owner") or "").strip()
    repo = str(settings.get("gitee_repo") or settings.get("github_repo") or "").strip()
    branch = str(settings.get("gitee_branch") or "master").strip() or "master"
    subdir = str(settings.get("gitee_release_path") or "releases").strip().strip("/") or "releases"
    if not owner or not repo:
        return {}
    base = f"https://gitee.com/{owner}/{repo}/raw/{branch}/{subdir}"
    installer = _installer_filename(settings)
    return {
        "manifest_url": f"{base}/version-policy.json",
        "download_url": f"{base}/{installer}",
        "html_url": f"https://gitee.com/{owner}/{repo}/releases",
    }


def _resolve_mirror_urls(settings: Dict[str, Any]) -> Dict[str, str]:
    """浠?update_mirror_base 鎺ㄥ鍥藉唴闀滃儚鍦板潃銆?""
    base = str(settings.get("update_mirror_base", "") or "").strip().rstrip("/")
    if not base:
        return {}
    installer = _installer_filename(settings)
    return {
        "manifest_url": f"{base}/version-policy.json",
        "download_url": f"{base}/{installer}",
    }


async def _load_update_sources(settings: Dict[str, Any]) -> tuple[dict, dict, str]:
    """浠庤吘璁簯闀滃儚鑾峰彇鏇存柊淇℃伅锛堜紭鍏堬級锛屼笉鍐嶄緷璧?Gitee Release銆?""
    timeout = int(settings.get("check_timeout_seconds", 15))
    prefer_mirror = bool(settings.get("prefer_mirror", True))

    gitee_raw = _resolve_gitee_raw_urls(settings)
    mirror_urls = _resolve_mirror_urls(settings)
    explicit_manifest = str(settings.get("manifest_url", "") or "").strip()

    def _finalize_manifest(manifest: dict, source: str) -> dict:
        if not manifest:
            return manifest
        cleaned = dict(manifest)
        cleaned["download_url"] = _resolve_download_url(
            str(cleaned.get("download_url") or ""),
            settings,
            gitee_raw=gitee_raw,
            mirror_urls=mirror_urls,
        )
        return cleaned

    if prefer_mirror:
        for url in (explicit_manifest, mirror_urls.get("manifest_url", ""), gitee_raw.get("manifest_url", "")):
            if not url:
                continue
            manifest = _finalize_manifest(await _load_manifest(url, timeout, settings), url)
            if manifest:
                return manifest, {}, "mirror"

    manual_download = _resolve_download_url(
        str(settings.get("manual_download_url", "") or ""),
        settings,
        gitee_raw=gitee_raw,
        mirror_urls=mirror_urls,
    )
    configured_latest = str(settings.get("latest_version", "") or "").strip()
    if manual_download and configured_latest:
        return (
            {
                "latest_version": configured_latest,
                "download_url": manual_download,
                "min_supported_version": settings.get("min_supported_version", ""),
            },
            {},
            "manual_download_url",
        )

    return {}, {}, "none"


async def _load_manifest(manifest_url: str, timeout_seconds: int, settings: Optional[Dict[str, Any]] = None) -> dict:
    if not manifest_url:
        return {}
    settings = settings or _merge_update_config()
    try:
        url = _gitee_auth_url(manifest_url, settings)
        return await _fetch_json(url, timeout_seconds)
    except Exception as exc:
        log.print_log(f"[Updater] 鍔犺浇鐗堟湰绛栫暐澶辫触: {exc}", "warning")
        return {}


async def _load_gitee_release_info(settings: Dict[str, Any]) -> dict:
    owner = str(settings.get("gitee_owner") or settings.get("github_owner") or "").strip()
    repo = str(settings.get("gitee_repo") or settings.get("github_repo") or "").strip()
    if not owner or not repo:
        return {}

    api_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    params: Dict[str, str] = {}
    token = str(settings.get("gitee_token") or os.environ.get("GITEE_TOKEN") or "").strip()
    if token:
        params["access_token"] = token
    headers = {"User-Agent": "AIWriteX-Updater"}

    try:
        timeout = int(settings.get("check_timeout_seconds", 15))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(api_url, params=params, headers=headers)
            response.raise_for_status()
            releases = response.json()
        if not isinstance(releases, list):
            return {}
        release = _select_release(releases, bool(settings.get("allow_prerelease")))
        if not release:
            return {}

        assets = _release_assets(release)
        installer_asset = _find_asset(assets, settings.get("installer_asset_name", ""), ".exe")
        manifest_asset = _find_asset(assets, settings.get("manifest_asset_name", ""), ".json")
        tag = str(release.get("tag_name", "")).lstrip("vV")
        tag_name = str(release.get("tag_name", tag) or tag)

        download_url = _asset_download_url(installer_asset)
        if not download_url and tag_name:
            installer_name = settings.get("installer_asset_name", INSTALLER_NAME)
            has_installer = any(
                (a.get("name") or "").strip().lower() == installer_name.strip().lower()
                for a in assets
            )
            if has_installer:
                download_url = (
                    f"https://gitee.com/{owner}/{repo}/releases/download/"
                    f"{tag_name}/{installer_name}"
                )
            else:
                gh_owner = str(settings.get("github_owner") or owner).strip()
                gh_repo = str(settings.get("github_repo") or repo).strip()
                installer_name = str(settings.get("installer_asset_name", INSTALLER_NAME))
                direct_github = (
                    f"https://github.com/{gh_owner}/{gh_repo}/releases/download/"
                    f"{tag_name}/{installer_name}"
                )
                mirrors = _expand_download_urls(direct_github)
                download_url = mirrors[0] if mirrors else ""

        download_url = _resolve_download_url(
            download_url,
            settings,
            gitee_raw=_resolve_gitee_raw_urls(settings),
            mirror_urls=_resolve_mirror_urls(settings),
        )

        return {
            "latest_version": tag,
            "release_notes": release.get("body") or release.get("name") or "",
            "published_at": release.get("created_at") or release.get("published_at") or "",
            "download_url": download_url,
            "manifest_url": _asset_download_url(manifest_asset),
            "html_url": release.get("html_url") or f"https://gitee.com/{owner}/{repo}/releases",
        }
    except Exception as exc:
        log.print_log(f"[Updater] 鑾峰彇 Gitee Release 澶辫触: {exc}", "warning")
        return {}


async def _build_update_policy() -> UpdatePolicyResponse:
    from src.ai_write_x.utils import utils as app_utils

    settings = _merge_update_config()
    current_version = get_version()
    is_release_build = app_utils.get_is_release_ver()

    if not settings.get("enabled", True):
        return UpdatePolicyResponse(
            enabled=False,
            startup_check=False,
            current_version=current_version,
            latest_version=current_version,
            min_supported_version=current_version,
            has_update=False,
            force_update=False,
            can_update=False,
            download_url="",
            release_notes="鏇存柊鍔熻兘宸茬鐢?,
            source="disabled",
            auto_update_on_startup=False,
            auto_update_silent=False,
            is_release_build=is_release_build,
            should_auto_update=False,
        )

    manifest, release_info, source = await _load_update_sources(settings)
    mirror_urls = _resolve_mirror_urls(settings)

    latest_version = (
        manifest.get("latest_version")
        or release_info.get("latest_version")
        or settings.get("latest_version")
        or current_version
    )
    min_supported_version = (
        manifest.get("min_supported_version")
        or settings.get("min_supported_version")
        or ""
    )
    download_url = _resolve_download_url(
        str(manifest.get("download_url") or release_info.get("download_url") or ""),
        settings,
        gitee_raw=_resolve_gitee_raw_urls(settings),
        mirror_urls=mirror_urls,
    ) or _resolve_download_url(
        str(settings.get("manual_download_url") or ""),
        settings,
        gitee_raw=_resolve_gitee_raw_urls(settings),
        mirror_urls=mirror_urls,
    )
    release_notes = (
        manifest.get("release_notes")
        or release_info.get("release_notes")
        or "鏆傛棤鏇存柊璇存槑"
    )

    has_update = False
    if latest_version:
        has_update = _is_version_less(current_version, latest_version)

    force_update = False
    if settings.get("mandatory_update_enabled", True) and min_supported_version:
        force_update = _is_version_less(current_version, min_supported_version)

    auto_update_on_startup = settings.get("auto_update_on_startup", True)
    if manifest.get("auto_update_on_startup") is not None:
        auto_update_on_startup = bool(manifest.get("auto_update_on_startup"))

    auto_update_silent = settings.get("auto_update_silent", True)
    if manifest.get("auto_update_silent") is not None:
        auto_update_silent = bool(manifest.get("auto_update_silent"))

    startup_check = bool(settings.get("startup_check", True))
    can_update = bool(download_url)
    should_auto_update = bool(
        is_release_build
        and startup_check
        and auto_update_on_startup
        and auto_update_silent
        and has_update
        and can_update
    )

    return UpdatePolicyResponse(
        enabled=True,
        startup_check=startup_check,
        current_version=current_version,
        latest_version=latest_version,
        min_supported_version=min_supported_version,
        has_update=has_update,
        force_update=force_update,
        can_update=can_update,
        download_url=download_url,
        release_notes=release_notes,
        published_at=manifest.get("published_at") or release_info.get("published_at") or "",
        source=source or release_info.get("html_url") or "config",
        auto_update_on_startup=bool(auto_update_on_startup),
        auto_update_silent=bool(auto_update_silent),
        is_release_build=is_release_build,
        should_auto_update=should_auto_update,
    )


def _reset_progress() -> None:
    _update_progress.update({
        "status": "idle",
        "progress": 0,
        "message": "",
        "error": "",
        "logs": [],
        "download_path": "",
        "helper_script": "",
    })


def _append_log(message: str) -> None:
    _update_progress["logs"].append(message)


def _humanize_update_error(exc: Exception) -> str:
    text = str(exc or "").strip()
    lowered = text.lower()
    if "all connection attempts failed" in lowered or "connecterror" in lowered:
        return "鏃犳硶杩炴帴鏇存柊鏈嶅姟鍣紝璇锋鏌ョ綉缁滄垨閰嶇疆绯荤粺浠ｇ悊鍚庨噸璇?
    if "timeout" in lowered or "timed out" in lowered:
        return "杩炴帴鏇存柊鏈嶅姟鍣ㄨ秴鏃讹紝璇风◢鍚庨噸璇?
    if "name or service not known" in lowered or "getaddrinfo" in lowered:
        return "鏃犳硶瑙ｆ瀽鏇存柊鏈嶅姟鍣ㄥ湴鍧€锛岃妫€鏌?DNS 鎴栫綉缁?
    if "certificate" in lowered or "ssl" in lowered:
        return "鏇存柊鏈嶅姟鍣?SSL 璇佷功鏍￠獙澶辫触"
    if text.startswith("鏇存柊澶辫触:") or text.startswith("妫€鏌ユ洿鏂板け璐?"):
        return text.split(":", 1)[-1].strip()
    return text or "鏈煡閿欒"


def _get_http_client_kwargs(settings: Dict[str, Any]) -> Dict[str, Any]:
    connect_timeout = float(settings.get("check_timeout_seconds", 15))
    download_timeout = float(settings.get("download_timeout_seconds", 600))
    timeout = httpx.Timeout(download_timeout, connect=min(connect_timeout, 30.0))
    kwargs: Dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
    proxy = str(settings.get("proxy") or Config.get_instance().proxy or "").strip()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def _expand_download_urls(url: str) -> list[str]:
    """杩斿洖鍙敤涓嬭浇鍦板潃锛涗紭鍏堜娇鐢?policy / 鑵捐浜戦暅鍍忛厤缃腑鐨勭洿閾俱€?""
    cleaned = str(url or "").strip()
    return [cleaned] if cleaned else []


def _resolve_download_url(
    url: str,
    settings: Dict[str, Any],
    *,
    gitee_raw: Optional[Dict[str, str]] = None,
    mirror_urls: Optional[Dict[str, str]] = None,
) -> str:
    gitee_raw = gitee_raw if gitee_raw is not None else _resolve_gitee_raw_urls(settings)
    mirror_urls = mirror_urls if mirror_urls is not None else _resolve_mirror_urls(settings)

    for candidate in (
        url,
        mirror_urls.get("download_url", ""),
        gitee_raw.get("download_url", ""),
        str(settings.get("manual_download_url", "") or ""),
    ):
        expanded = _expand_download_urls(str(candidate or "").strip())
        if expanded:
            return expanded[0]
    return ""


def _build_download_candidates(primary_url: str, settings: Dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(url: str) -> None:
        for item in _expand_download_urls(url):
            if item and item not in seen:
                seen.add(item)
                candidates.append(item)

    add(primary_url)
    mirror_urls = _resolve_mirror_urls(settings)
    gitee_raw = _resolve_gitee_raw_urls(settings)
    add(mirror_urls.get("download_url", ""))
    add(gitee_raw.get("download_url", ""))
    add(str(settings.get("manual_download_url", "") or ""))

    return candidates


async def _stream_download_with_fallback(
    candidates: list[str],
    installer_path: Path,
    settings: Dict[str, Any],
) -> str:
    if not candidates:
        raise RuntimeError("娌℃湁鍙敤鐨勬洿鏂颁笅杞藉湴鍧€")

    client_kwargs = _get_http_client_kwargs(settings)
    errors: list[str] = []

    async with httpx.AsyncClient(**client_kwargs) as client:
        for index, url in enumerate(candidates, start=1):
            for attempt in range(1, 3):
                try:
                    _append_log(f"姝ｅ湪涓嬭浇 ({index}/{len(candidates)}) 绗?{attempt} 娆″皾璇?..")
                    _append_log(url)
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        total_size = int(response.headers.get("content-length", 0))
                        downloaded = 0
                        installer_path.parent.mkdir(parents=True, exist_ok=True)
                        last_ui_update = 0.0
                        with installer_path.open("wb") as file_obj:
                            async for chunk in response.aiter_bytes():
                                file_obj.write(chunk)
                                downloaded += len(chunk)
                                now = time.monotonic()
                                if now - last_ui_update >= 0.3:
                                    if total_size > 0:
                                        progress = min(95, int(downloaded * 100 / total_size))
                                    else:
                                        mb = downloaded / (1024 * 1024)
                                        progress = min(92, max(3, int(mb * 0.75)))
                                    _update_progress["progress"] = progress
                                    _update_progress["message"] = (
                                        f"姝ｅ湪涓嬭浇鏇存柊瀹夎鍖?.. {progress}%"
                                    )
                                    last_ui_update = now
                    return url
                except Exception as exc:
                    detail = _humanize_update_error(exc)
                    errors.append(f"{url} -> {detail}")
                    log.print_log(f"[Updater] 涓嬭浇澶辫触: {url} ({detail})", "warning")

    raise RuntimeError(errors[-1] if errors else "鎵€鏈変笅杞藉湴鍧€鍧囦笉鍙敤")


def _get_update_workspace() -> Path:
    workspace = PathManager.get_temp_dir() / "updates"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _ps_single_quoted(path: Path | str) -> str:
    return str(path).replace("'", "''")


def _resolve_installed_executable(settings: Dict[str, Any]) -> Path:
    """瑙ｆ瀽瀹夎鐩綍涓殑涓荤▼搴忓彲鎵ц鏂囦欢銆?""
    preferred = str(settings.get("restart_executable", EXE_NAME) or EXE_NAME).strip()
    candidates: list[Path] = [PathManager.get_base_dir() / preferred]
    if os.name == "nt":
        for root in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ):
            candidates.append(root / APP_BRAND / EXE_NAME)

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _build_helper_script(installer_path: Path) -> Path:
    settings = _merge_update_config()
    script_path = _get_update_workspace() / "run_update.ps1"
    log_path = _get_update_workspace() / "update-helper.log"
    status_path = _get_update_workspace() / "update-status.json"
    current_pid = os.getpid()
    app_exe = _resolve_installed_executable(settings)
    install_dir = app_exe.parent.resolve()

    if not utils.get_is_release_ver():
        raise RuntimeError("褰撳墠鏄紑鍙戠幆澧冿紝涓嶈兘鎵ц瀹夎鍖呮洿鏂?)

    installer_ps = _ps_single_quoted(installer_path)
    log_ps = _ps_single_quoted(log_path)
    status_ps = _ps_single_quoted(status_path)
    install_dir_ps = _ps_single_quoted(str(install_dir))

    script_content = f"""$ErrorActionPreference = 'Continue'
$logFile = '{log_ps}'
$statusFile = '{status_ps}'

function Write-UpdateLog([string]$Message) {{
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}}

function Write-Status([string]$Status, [int]$Progress, [string]$Message) {{
    @{{ status=$Status; progress=$Progress; message=$Message; time=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') }} | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
}}

$installerPath = '{installer_ps}'
$targetPid = {current_pid}
$targetInstallDir = '{install_dir_ps}'
$appExe = Join-Path $targetInstallDir '{EXE_NAME}'
$argumentList = @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS',
    "/DIR=$targetInstallDir"
)

Write-UpdateLog "鏇存柊鍔╂墜鍚姩锛岀洰鏍囪繘绋?PID=$targetPid"
Write-UpdateLog "瀹夎鍖? $installerPath"
Write-UpdateLog "瀹夎鐩綍: $targetInstallDir"
Write-UpdateLog "涓荤▼搴? $appExe"

# ===== 绗浂姝ワ細涓诲姩鍏抽棴鏃х増鏈繘绋?=====
Write-Status 'waiting' 2 '姝ｅ湪鍏抽棴鏃х増鏈?..'
$oldProc = Get-Process -Name '{APP_BRAND}' -ErrorAction SilentlyContinue
if ($oldProc) {{
    Write-UpdateLog "妫€娴嬪埌鏃х増鏈繘绋?(PID=$($oldProc.Id -join ','))锛屾鍦ㄥ叧闂?.."
    try {{
        $oldProc | Stop-Process -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
        # 纭杩涚▼宸插叧闂?        $stillRunning = Get-Process -Name '{APP_BRAND}' -ErrorAction SilentlyContinue
        if ($stillRunning) {{
            Write-UpdateLog "鏃х増鏈繘绋嬫湭鍝嶅簲鍏抽棴锛屽啀娆″皾璇?.."
            $stillRunning | Stop-Process -Force
            Start-Sleep -Seconds 2
        }}
        Write-UpdateLog "鏃х増鏈凡鍏抽棴"
    }} catch {{
        Write-UpdateLog "鍏抽棴鏃х増鏈け璐? $($_.Exception.Message)锛屽皢鐢卞畨瑁呯▼搴忓鐞?
    }}
}} else {{
    Write-UpdateLog "鏈娴嬪埌鏃х増鏈繘绋?
}}

# ===== 绗竴姝ワ細鍚姩瀹夎绋嬪簭 =====
Write-Status 'installing' 5 '姝ｅ湪鍚姩瀹夎绋嬪簭...'

try {{
    Write-UpdateLog "鍚姩瀹夎绋嬪簭锛堣姹傜鐞嗗憳鏉冮檺锛?.."
    Write-Status 'installing' 8 '绛夊緟绠＄悊鍛樻潈闄愮‘璁?..'
    Start-Process -FilePath $installerPath -ArgumentList $argumentList -Verb RunAs
    Write-UpdateLog "瀹夎绋嬪簭宸插惎鍔紙RunAs锛?
}} catch {{
    Write-UpdateLog "RunAs 澶辫触: $($_.Exception.Message)锛屽皾璇曟櫘閫氭潈闄?.."
    Write-Status 'installing' 9 '灏濊瘯鏅€氭ā寮忓畨瑁?..'
    try {{
        Start-Process -FilePath $installerPath -ArgumentList $argumentList
        Write-UpdateLog "瀹夎绋嬪簭宸插惎鍔紙鏅€氭潈闄愶級"
    }} catch {{
        Write-UpdateLog "瀹夎澶辫触: $($_.Exception.Message)"
        Write-Status 'error' 0 '瀹夎绋嬪簭鎵ц澶辫触'
        exit 1
    }}
}}

# 绛夊緟瀹夎绋嬪簭瀹屾垚锛堥€氳繃妫€娴嬪畨瑁呯▼搴忚繘绋嬶級
Write-Status 'installing' 15 '瀹夎绋嬪簭姝ｅ湪杩愯...'
$totalWait = 0
$installerRunning = $true
while ($installerRunning -and $totalWait -lt 180) {{
    Start-Sleep -Seconds 1
    $totalWait++
    # 妫€娴?Inno Setup 瀹夎绋嬪簭杩涚▼锛圴ERYSILENT妯″紡涓嬭繘绋嬪悕鍙兘鏄复鏃跺悕绉帮級
    $setupProc = Get-Process | Where-Object {{
        try {{
            $_.Path -and ($_.Path -like '*Temp*\is-*' -or $_.Path -like '*Temp*\InnoSetup*')
        }} catch {{ $false }}
    }}
    if (-not $setupProc) {{
        # 澶囬€夛細妫€娴嬫枃浠舵槸鍚﹁繕鍦ㄨ鍐欏叆锛堟鏌?_internal 鐩綍鐨勪慨鏀规椂闂达級
        $internalDir = Join-Path $targetInstallDir '_internal'
        if (Test-Path -LiteralPath $internalDir) {{
            $dirWrite = (Get-Item -LiteralPath $internalDir).LastWriteTime
            $span = (Get-Date) - $dirWrite
            if ($span.TotalSeconds -lt 5) {{
                # 鐩綍鏈€杩戣淇敼锛屽畨瑁呭彲鑳借繕鍦ㄨ繘琛?                $setupProc = $true
            }}
        }}
    }}
    if (-not $setupProc) {{
        $installerRunning = $false
    }}
    $pct = [Math]::Min(90, 15 + [Math]::Floor($totalWait * 0.5))
    $msg = "姝ｅ湪瀹夎涓?($totalWait绉?..."
    if ($totalWait -gt 30) {{ $msg += " 瀹夎鍖呰緝澶ц鑰愬績绛夊緟" }}
    Write-Status 'installing' $pct $msg
    if ($totalWait % 5 -eq 0) {{
        Write-UpdateLog "瀹夎杩涜涓? $totalWait绉?杩涘害=$pct%"
    }}
}}

Write-UpdateLog "瀹夎绋嬪簭宸茬粨鏉燂紝绛夊緟=$totalWait绉?

# ===== 绗簩姝ワ細鍚姩鏂扮増鏈?=====
Write-Status 'installed' 95 '瀹夎瀹屾垚锛屾鍦ㄥ惎鍔ㄦ柊鐗堟湰...'

Start-Sleep -Seconds 3

$running = Get-Process -Name '{APP_BRAND}' -ErrorAction SilentlyContinue
if ($running) {{
    Write-UpdateLog "妫€娴嬪埌鏂扮増鏈凡杩愯 (PID=$($running.Id -join ','))"
    Write-Status 'done' 100 '鏇存柊瀹屾垚'
    exit 0
}}

if (-not (Test-Path -LiteralPath $appExe)) {{
    $pf = Join-Path $env:ProgramFiles '{APP_BRAND}'
    $candidate = Join-Path $pf '{EXE_NAME}'
    if (Test-Path -LiteralPath $candidate) {{
        $appExe = $candidate
        $targetInstallDir = $pf
    }}
}}

if (Test-Path -LiteralPath $appExe) {{
    Write-UpdateLog "鍚姩鏂扮増鏈? $appExe"
    try {{
        $started = Start-Process -FilePath $appExe -WorkingDirectory $targetInstallDir -PassThru
        Write-UpdateLog "宸插惎鍔ㄦ柊鐗堟湰 PID=$($started.Id)"
        Write-Status 'done' 100 '鏇存柊瀹屾垚'
    }} catch {{
        Write-UpdateLog "鍚姩澶辫触: $($_.Exception.Message)"
        Write-Status 'error' 100 '瀹夎鎴愬姛浣嗗惎鍔ㄥけ璐?
        exit 2
    }}
}} else {{
    Write-UpdateLog "鏈壘鍒板彲鎵ц鏂囦欢: $appExe"
    Write-Status 'error' 100 '鏈壘鍒版柊鐗堟湰鍙墽琛屾枃浠?
    exit 2
}}
"""
    script_path.write_text(script_content, encoding="utf-8-sig")
    _update_progress["log_file"] = str(log_path)
    _update_progress["status_file"] = str(status_path)
    return script_path


async def _run_download_update(
    download_url: str,
    latest_version: str,
    installer_path: Path,
    settings: Dict[str, Any],
) -> None:
    try:
        candidates = _build_download_candidates(download_url, settings)
        used_url = await _stream_download_with_fallback(candidates, installer_path, settings)
        _append_log(f"涓嬭浇婧? {used_url}")
        helper_script = _build_helper_script(installer_path)
        _update_progress.update({
            "status": "ready_to_install",
            "progress": 100,
            "message": "鏇存柊宸插噯澶囧畬鎴愶紝姝ｅ湪鍚姩瀹夎鈥?,
            "download_path": str(installer_path),
            "helper_script": str(helper_script),
        })
        _append_log("鏇存柊鍔╂墜宸茬敓鎴?)
        _append_log("涓嬭浇瀹屾垚锛屽嵆灏嗚嚜鍔ㄥ畨瑁呭苟閲嶅惎鈥?)
    except Exception as exc:
        detail = _humanize_update_error(exc)
        _update_progress.update({
            "status": "error",
            "progress": 0,
            "message": detail,
            "error": detail,
        })
        _append_log(f"鏇存柊澶辫触: {detail}")
        log.print_log(f"[Updater] 涓嬭浇鏇存柊澶辫触: {exc}", "error")


@router.get("/update-policy", response_model=UpdatePolicyResponse)
async def get_update_policy():
    try:
        return await _build_update_policy()
    except Exception as exc:
        log.print_log(f"[Updater] 鑾峰彇鏇存柊绛栫暐澶辫触: {exc}", "error")
        raise HTTPException(status_code=500, detail=_humanize_update_error(exc))


@router.get("/check-update", response_model=UpdatePolicyResponse)
async def check_update():
    return await get_update_policy()


@router.get("/update-progress")
async def get_update_progress():
    return _update_progress


@router.post("/update")
async def prepare_update(request: UpdateRequest):
    policy = await _build_update_policy()
    download_url = request.download_url or policy.download_url

    if not download_url:
        raise HTTPException(status_code=400, detail="娌℃湁鍙敤鐨勬洿鏂板畨瑁呭寘鍦板潃")
    if not utils.get_is_release_ver():
        raise HTTPException(status_code=400, detail="寮€鍙戠幆澧冧笉鏀寔瀹夎鍖呮洿鏂?)

    with _download_lock:
        current_status = _update_progress.get("status")
        if current_status == "downloading":
            return {"status": "downloading", "message": "姝ｅ湪涓嬭浇鏇存柊瀹夎鍖?.."}
        if current_status == "ready_to_install":
            return {"status": "ready_to_install", "message": "鏇存柊宸插噯澶囧畬鎴?}

        _reset_progress()
        _update_progress["status"] = "downloading"
        _update_progress["progress"] = 1
        _update_progress["message"] = "姝ｅ湪涓嬭浇鏇存柊瀹夎鍖?.."
        _append_log("寮€濮嬩笅杞芥洿鏂板畨瑁呭寘")
        _append_log(f"鐩爣鐗堟湰: v{policy.latest_version}")

        workspace = _get_update_workspace()
        installer_path = workspace / _installer_filename(_merge_update_config())
        settings = _merge_update_config()

    asyncio.create_task(
        _run_download_update(
            download_url,
            policy.latest_version,
            installer_path,
            settings,
        )
    )
    return {"status": "downloading", "message": "姝ｅ湪鍚庡彴涓嬭浇鏇存柊瀹夎鍖?}


def _spawn_detached_powershell(script_path: Path) -> None:
    """鐙珛鍚姩鏇存柊鍔╂墜锛岄伩鍏嶄富杩涚▼閫€鍑烘椂杩炲甫缁撴潫瀛愯繘绋嬨€?""
    script = str(script_path.resolve())
    if os.name == "nt":
        cmdline = (
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
            f'-File "{script}"'
        )
        subprocess.Popen(
            f'cmd.exe /c start "" /min {cmdline}',
            shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        return
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            script,
        ],
        close_fds=True,
    )


@router.post("/start-install")
async def start_install():
    helper_script = _update_progress.get("helper_script", "")
    if not helper_script or not Path(helper_script).exists():
        raise HTTPException(status_code=404, detail="鏈壘鍒版洿鏂板姪鎵嬶紝璇峰厛涓嬭浇鏇存柊")

    try:
        _append_log("姝ｅ湪鍚姩瀹夎绋嬪簭鈥?)
        _spawn_detached_powershell(Path(helper_script))
        _update_progress["status"] = "installing"
        _append_log("瀹夎绋嬪簭宸插惎鍔紝绛夊緟瀹夎瀹屾垚...")
        return {
            "status": "installing",
            "message": "瀹夎绋嬪簭宸插惎鍔紝姝ｅ湪瀹夎涓紙绐楀彛鍙兘鍥犳洿鏂拌嚜鍔ㄥ叧闂級",
            "log_file": _update_progress.get("log_file", ""),
            "status_file": _update_progress.get("status_file", ""),
        }
    except Exception as exc:
        log.print_log(f"[Updater] 鍚姩瀹夎绋嬪簭澶辫触: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"鍚姩瀹夎绋嬪簭澶辫触: {exc}")


@router.get("/install-status")
async def get_install_status():
    status_file = _update_progress.get("status_file", "")
    if not status_file or not Path(status_file).exists():
        return {"status": "not_started", "message": ""}
    try:
        data = json.loads(Path(status_file).read_text(encoding="utf-8"))
        return data
    except Exception:
        return {"status": "unknown", "message": ""}


@router.post("/restart-and-update")
async def restart_and_update():
    return await start_install()


@router.post("/bring-to-front")
async def bring_to_front():
    """灏嗙▼搴忕獥鍙ｆ縺娲诲埌鍓嶅彴锛堢敤浜庡崟瀹炰緥鎺у埗鏃舵縺娲诲凡鏈夊疄渚嬶級"""
    try:
        from src.ai_write_x.web.state import get_app_state
        app_state = get_app_state()
        window_manager = app_state.get("window_manager")
        if window_manager and hasattr(window_manager, "show_window"):
            window_manager.show_window()
            return {"status": "ok", "message": "绐楀彛宸叉縺娲?}
        return {"status": "error", "message": "绐楀彛绠＄悊鍣ㄤ笉鍙敤"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

