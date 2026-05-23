import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils import log, utils
from src.ai_write_x.utils.path_manager import PathManager
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
    "gitee_repo": "AIWriteX-main",
    "gitee_branch": "master",
    "gitee_release_path": "releases",
    "gitee_token": "",
    "github_owner": "lqyha520",
    "github_repo": "AIWriteX-main",
    "allow_prerelease": False,
    "manifest_url": "https://gitee.com/lqyha520/AIWriteX-main/raw/master/releases/version-policy.json",
    "manifest_asset_name": "version-policy.json",
    "installer_asset_name": "AIWriteX-Setup.exe",
    "installer_silent_args": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART",
    "restart_executable": "AIWriteX.exe",
    "check_timeout_seconds": 15,
    "download_timeout_seconds": 600,
    "min_supported_version": "",
    "latest_version": "",
    "manual_download_url": "",
    "update_mirror_base": "",
    "prefer_mirror": True,
    "fallback_github": True,
}

_update_progress: Dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "error": "",
    "logs": [],
    "download_path": "",
    "helper_script": "",
}


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


def _select_release(data: list[dict], allow_prerelease: bool) -> Optional[dict]:
    for item in data:
        if item.get("draft"):
            continue
        if not allow_prerelease and item.get("prerelease"):
            continue
        return item
    return None


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


def _resolve_gitee_raw_urls(settings: Dict[str, Any]) -> Dict[str, str]:
    """Gitee 仓库 raw 直链（version-policy + 安装包，适合小文件或 LFS）。"""
    owner = str(settings.get("gitee_owner") or settings.get("github_owner") or "").strip()
    repo = str(settings.get("gitee_repo") or settings.get("github_repo") or "").strip()
    branch = str(settings.get("gitee_branch") or "master").strip() or "master"
    subdir = str(settings.get("gitee_release_path") or "releases").strip().strip("/") or "releases"
    if not owner or not repo:
        return {}
    base = f"https://gitee.com/{owner}/{repo}/raw/{branch}/{subdir}"
    return {
        "manifest_url": f"{base}/version-policy.json",
        "download_url": f"{base}/AIWriteX-Setup.exe",
        "html_url": f"https://gitee.com/{owner}/{repo}/releases",
    }


def _resolve_mirror_urls(settings: Dict[str, Any]) -> Dict[str, str]:
    """从 update_mirror_base 推导国内镜像地址。"""
    base = str(settings.get("update_mirror_base", "") or "").strip().rstrip("/")
    if not base:
        return {}
    return {
        "manifest_url": f"{base}/version-policy.json",
        "download_url": f"{base}/AIWriteX-Setup.exe",
    }


async def _load_update_sources(settings: Dict[str, Any]) -> tuple[dict, dict, str]:
    """优先 Gitee（Release / raw），可选回退 GitHub。"""
    timeout = int(settings.get("check_timeout_seconds", 15))
    prefer_mirror = bool(settings.get("prefer_mirror", True))
    provider = str(settings.get("provider") or "gitee_release").strip().lower()
    fallback_github = bool(settings.get("fallback_github", True))

    gitee_raw = _resolve_gitee_raw_urls(settings)
    mirror_urls = _resolve_mirror_urls(settings)
    explicit_manifest = str(settings.get("manifest_url", "") or "").strip()

    manifest_urls: list[str] = []
    for url in (explicit_manifest, mirror_urls.get("manifest_url", ""), gitee_raw.get("manifest_url", "")):
        if url and url not in manifest_urls:
            manifest_urls.append(url)

    if prefer_mirror:
        for manifest_url in manifest_urls:
            manifest = await _load_manifest(manifest_url, timeout, settings)
            if manifest:
                if not manifest.get("download_url"):
                    download_url = (
                        gitee_raw.get("download_url")
                        or mirror_urls.get("download_url")
                        or str(settings.get("manual_download_url", "") or "")
                    )
                    if download_url:
                        manifest = dict(manifest)
                        manifest["download_url"] = download_url
                return manifest, {}, manifest_url

        manual_download = str(settings.get("manual_download_url", "") or "").strip()
        configured_latest = str(settings.get("latest_version", "") or "").strip()
        if manual_download and configured_latest and not manifest_urls:
            return (
                {
                    "latest_version": configured_latest,
                    "download_url": manual_download,
                    "min_supported_version": settings.get("min_supported_version", ""),
                },
                {},
                "manual_download_url",
            )

    release_info: dict = {}
    if provider in ("gitee_release", "gitee", "auto", "mirror"):
        release_info = await _load_gitee_release_info(settings)
        if release_info:
            manifest: dict = {}
            manifest_url = release_info.get("manifest_url", "")
            if manifest_url:
                manifest = await _load_manifest(manifest_url, timeout, settings)
            if not manifest and release_info.get("latest_version"):
                manifest = {
                    "latest_version": release_info.get("latest_version", ""),
                    "download_url": release_info.get("download_url", ""),
                    "min_supported_version": "",
                }
            if manifest:
                if not manifest.get("download_url") and release_info.get("download_url"):
                    manifest = dict(manifest)
                    manifest["download_url"] = release_info["download_url"]
                return manifest, release_info, release_info.get("html_url") or "gitee"
            if release_info.get("download_url"):
                return {}, release_info, release_info.get("html_url") or "gitee"

    if fallback_github and provider != "gitee_only":
        release_info = await _load_github_release_info(settings)
        github_manifest_url = release_info.get("manifest_url", "") or explicit_manifest
        manifest = {}
        if github_manifest_url:
            manifest = await _load_manifest(github_manifest_url, timeout, settings)
        if manifest:
            if not manifest.get("download_url") and release_info.get("download_url"):
                manifest = dict(manifest)
                manifest["download_url"] = release_info["download_url"]
            return manifest, release_info, github_manifest_url or "github"
        if release_info:
            return manifest, release_info, release_info.get("html_url") or "github"

    return {}, release_info, "config"


async def _load_manifest(manifest_url: str, timeout_seconds: int, settings: Optional[Dict[str, Any]] = None) -> dict:
    if not manifest_url:
        return {}
    settings = settings or _merge_update_config()
    try:
        url = _gitee_auth_url(manifest_url, settings)
        return await _fetch_json(url, timeout_seconds)
    except Exception as exc:
        log.print_log(f"[Updater] 加载版本策略失败: {exc}", "warning")
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
            installer_name = settings.get("installer_asset_name", "AIWriteX-Setup.exe")
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
                download_url = (
                    f"https://ghfast.top/https://github.com/{gh_owner}/{gh_repo}"
                    f"/releases/download/{tag_name}/{settings.get('installer_asset_name', 'AIWriteX-Setup.exe')}"
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
        log.print_log(f"[Updater] 获取 Gitee Release 失败: {exc}", "warning")
        return {}


async def _load_github_release_info(settings: Dict[str, Any]) -> dict:
    owner = settings.get("github_owner", "").strip()
    repo = settings.get("github_repo", "").strip()
    if not owner or not repo:
        return {}

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AIWriteX-Updater",
    }

    try:
        releases = await _fetch_json(api_url, int(settings.get("check_timeout_seconds", 15)), headers=headers)
        if not isinstance(releases, list):
            return {}
        release = _select_release(releases, bool(settings.get("allow_prerelease")))
        if not release:
            return {}

        assets = _release_assets(release)
        installer_asset = _find_asset(assets, settings.get("installer_asset_name", ""), ".exe")
        manifest_asset = _find_asset(assets, settings.get("manifest_asset_name", ""), ".json")

        return {
            "latest_version": str(release.get("tag_name", "")).lstrip("vV"),
            "release_notes": release.get("body") or "",
            "published_at": release.get("published_at") or "",
            "download_url": _asset_download_url(installer_asset),
            "manifest_url": _asset_download_url(manifest_asset),
            "html_url": release.get("html_url") or "",
        }
    except Exception as exc:
        log.print_log(f"[Updater] 获取 GitHub Release 失败: {exc}", "warning")
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
            release_notes="更新功能已禁用",
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
    download_url = (
        manifest.get("download_url")
        or release_info.get("download_url")
        or _resolve_gitee_raw_urls(settings).get("download_url")
        or mirror_urls.get("download_url")
        or settings.get("manual_download_url")
        or ""
    )
    release_notes = (
        manifest.get("release_notes")
        or release_info.get("release_notes")
        or "暂无更新说明"
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


def _get_update_workspace() -> Path:
    workspace = PathManager.get_temp_dir() / "updates"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _build_helper_script(installer_path: Path) -> Path:
    settings = _merge_update_config()
    script_path = _get_update_workspace() / "run_update.ps1"
    current_pid = os.getpid()
    app_exe = PathManager.get_base_dir() / settings.get("restart_executable", "AIWriteX.exe")
    installer_args = settings.get("installer_silent_args", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART")

    if not utils.get_is_release_ver():
        raise RuntimeError("当前是开发环境，不能执行安装包更新")

    script_content = f"""$ErrorActionPreference = 'Stop'
$installerPath = "{installer_path}"
$targetPid = {current_pid}
$appExe = "{app_exe}"
$installerArgs = "{installer_args}"

for ($i = 0; $i -lt 180; $i++) {{
    $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if (-not $process) {{
        break
    }}
    Start-Sleep -Milliseconds 500
}}

Get-Process -Name 'AIWriteX' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

$argumentList = @()
if ($installerArgs) {{
    $argumentList = $installerArgs.Split(' ') | Where-Object {{ $_ -and $_.Trim() -ne '' }}
}}

Start-Process -FilePath $installerPath -ArgumentList $argumentList -Wait

Start-Sleep -Seconds 2
if (Test-Path $appExe) {{
    Start-Process -FilePath $appExe
}}
"""
    script_path.write_text(script_content, encoding="utf-8")
    return script_path


@router.get("/update-policy", response_model=UpdatePolicyResponse)
async def get_update_policy():
    try:
        return await _build_update_policy()
    except Exception as exc:
        log.print_log(f"[Updater] 获取更新策略失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"检查更新失败: {exc}")


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
        raise HTTPException(status_code=400, detail="没有可用的更新安装包地址")
    if not utils.get_is_release_ver():
        raise HTTPException(status_code=400, detail="开发环境不支持安装包更新")

    _reset_progress()
    _update_progress["status"] = "downloading"
    _update_progress["message"] = "正在下载更新安装包..."
    _append_log("开始下载更新安装包")
    _append_log(f"目标版本: v{policy.latest_version}")

    workspace = _get_update_workspace()
    installer_path = workspace / "AIWriteX-Setup.exe"

    try:
        async with httpx.AsyncClient(
            timeout=int(_merge_update_config().get("download_timeout_seconds", 600)),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with installer_path.open("wb") as file_obj:
                    async for chunk in response.aiter_bytes():
                        file_obj.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = min(95, int(downloaded * 100 / total_size))
                            _update_progress["progress"] = progress
                            _update_progress["message"] = f"正在下载更新安装包... {progress}%"

        _append_log("安装包下载完成")
        helper_script = _build_helper_script(installer_path)
        _update_progress.update({
            "status": "ready_to_install",
            "progress": 100,
            "message": "更新已准备完成，重启后开始安装",
            "download_path": str(installer_path),
            "helper_script": str(helper_script),
        })
        _append_log("更新助手已生成")
        _append_log("下载完成，即将自动重启并安装...")
        return {"status": "success", "message": "更新准备完成"}
    except Exception as exc:
        _update_progress.update({
            "status": "error",
            "progress": 0,
            "message": f"更新失败: {exc}",
            "error": str(exc),
        })
        _append_log(f"更新失败: {exc}")
        log.print_log(f"[Updater] 下载更新失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"更新失败: {exc}")


@router.post("/restart-and-update")
async def restart_and_update():
    helper_script = _update_progress.get("helper_script", "")
    if not helper_script or not Path(helper_script).exists():
        raise HTTPException(status_code=404, detail="未找到更新助手，请先下载更新")

    try:
        subprocess.Popen(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                helper_script,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Timer(0.6, os._exit, args=(0,)).start()
        return {"status": "restarting", "message": "正在退出并安装更新"}
    except Exception as exc:
        log.print_log(f"[Updater] 启动更新助手失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"启动更新助手失败: {exc}")
