import asyncio
import hashlib
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
from src.ai_write_x.branding.install import APP_SLUG, EXE_NAME, INSTALLER_NAME
from src.ai_write_x.version import get_version

router = APIRouter(prefix="/api/system", tags=["System Update"])

DEFAULT_UPDATE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "startup_check": True,
    "mandatory_update_enabled": True,
    "auto_update_on_startup": True,
    "auto_update_silent": True,
    "auto_download": True,
    "auto_install": False,
    "install_mode": "on_exit",
    "update_level": "normal",
    "rollout_percent": 100,
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
    "installer_silent_args": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /FORCECLOSEAPPLICATIONS",
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
    sha256: str = ""
    release_notes: str
    published_at: str = ""
    source: str = ""
    auto_update_on_startup: bool = True
    auto_update_silent: bool = True
    auto_download: bool = True
    auto_install: bool = False
    install_mode: str = "on_exit"
    update_level: str = "normal"
    rollout_percent: int = 100
    update_ready: bool = False
    is_release_build: bool = False
    should_auto_update: bool = False


class UpdateRequest(BaseModel):
    download_url: Optional[str] = None
    sha256: Optional[str] = None


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
    """Gitee/GitHub 列表顺序不保证最新在前，按 tag 版本号取最大。"""
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
    """Gitee 仓库 raw 直链（version-policy + 安装包，适合小文件或 LFS）。"""
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
    """从 update_mirror_base 推导国内镜像地址。"""
    base = str(settings.get("update_mirror_base", "") or "").strip().rstrip("/")
    if not base:
        return {}
    installer = _installer_filename(settings)
    return {
        "manifest_url": f"{base}/version-policy.json",
        "download_url": f"{base}/{installer}",
    }


async def _load_update_sources(settings: Dict[str, Any]) -> tuple[dict, dict, str]:
    """仅从 Gitee Release / 国内镜像 / 手动配置获取更新信息，不使用 GitHub。"""
    timeout = int(settings.get("check_timeout_seconds", 15))
    prefer_mirror = bool(settings.get("prefer_mirror", True))
    provider = str(settings.get("provider") or "gitee_release").strip().lower()

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

    manifest_urls: list[str] = []
    # 优先 Gitee Release 上的策略（最权威），再镜像直链，避免镜像文件过期
    for url in (
        explicit_manifest,
        gitee_raw.get("manifest_url", ""),
        mirror_urls.get("manifest_url", ""),
    ):
        if url and url not in manifest_urls:
            manifest_urls.append(url)

    if prefer_mirror:
        release_info = await _load_gitee_release_info(settings)
        if release_info:
            manifest: dict = {}
            manifest_url = release_info.get("manifest_url", "")
            if manifest_url:
                manifest = _finalize_manifest(
                    await _load_manifest(manifest_url, timeout, settings), manifest_url
                )
            if manifest:
                if not manifest.get("download_url") and release_info.get("download_url"):
                    manifest = dict(manifest)
                    manifest["download_url"] = _resolve_download_url(
                        release_info["download_url"],
                        settings,
                        gitee_raw=gitee_raw,
                        mirror_urls=mirror_urls,
                    )
                return manifest, release_info, release_info.get("html_url") or "gitee"

        for manifest_url in manifest_urls:
            manifest = _finalize_manifest(await _load_manifest(manifest_url, timeout, settings), manifest_url)
            if manifest:
                if not manifest.get("download_url"):
                    download_url = _resolve_download_url(
                        "",
                        settings,
                        gitee_raw=gitee_raw,
                        mirror_urls=mirror_urls,
                    )
                    if download_url:
                        manifest = dict(manifest)
                        manifest["download_url"] = download_url
                return manifest, {}, manifest_url

        manual_download = _resolve_download_url(
            str(settings.get("manual_download_url", "") or ""),
            settings,
            gitee_raw=gitee_raw,
            mirror_urls=mirror_urls,
        )
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
    if provider in ("gitee_release", "gitee", "gitee_only", "auto", "mirror", "github_release"):
        release_info = await _load_gitee_release_info(settings)
        if release_info:
            manifest: dict = {}
            manifest_url = release_info.get("manifest_url", "")
            if manifest_url:
                manifest = _finalize_manifest(await _load_manifest(manifest_url, timeout, settings), manifest_url)
            if not manifest and release_info.get("latest_version"):
                manifest = _finalize_manifest(
                    {
                        "latest_version": release_info.get("latest_version", ""),
                        "download_url": release_info.get("download_url", ""),
                        "min_supported_version": "",
                    },
                    "gitee_release",
                )
            if manifest:
                if not manifest.get("download_url") and release_info.get("download_url"):
                    manifest = dict(manifest)
                    manifest["download_url"] = _resolve_download_url(
                        release_info["download_url"],
                        settings,
                        gitee_raw=gitee_raw,
                        mirror_urls=mirror_urls,
                    )
                return manifest, release_info, release_info.get("html_url") or "gitee"
            if release_info.get("download_url"):
                return {}, release_info, release_info.get("html_url") or "gitee"

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
        log.print_log(f"[Updater] 获取 Gitee Release 失败: {exc}", "warning")
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
            sha256="",
            release_notes="更新功能已禁用",
            source="disabled",
            auto_update_on_startup=False,
            auto_update_silent=False,
            auto_download=False,
            auto_install=False,
            install_mode="manual",
            update_level="normal",
            rollout_percent=0,
            update_ready=False,
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
        or "暂无更新说明"
    )
    sha256 = str(manifest.get("sha256") or release_info.get("sha256") or "").strip().lower()

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

    update_level = str(manifest.get("update_level") or settings.get("update_level") or "normal").strip().lower()
    if update_level not in {"normal", "important", "critical"}:
        update_level = "normal"
    if update_level == "critical" or bool(manifest.get("force_update", False)):
        force_update = True

    install_mode = str(manifest.get("install_mode") or settings.get("install_mode") or "on_exit").strip().lower()
    if install_mode not in {"manual", "on_exit", "on_next_start", "immediate"}:
        install_mode = "on_exit"

    auto_download = bool(manifest.get("auto_download", settings.get("auto_download", True)))
    auto_install = bool(manifest.get("auto_install", settings.get("auto_install", False)))
    try:
        rollout_percent = int(manifest.get("rollout_percent", settings.get("rollout_percent", 100)))
    except (TypeError, ValueError):
        rollout_percent = 100
    rollout_percent = max(0, min(100, rollout_percent))
    if rollout_percent <= 0:
        auto_download = False
        auto_install = False

    startup_check = bool(settings.get("startup_check", True))
    can_update = bool(download_url)
    should_auto_update = bool(
        is_release_build
        and startup_check
        and has_update
        and can_update
        and (
            force_update
            or (
                auto_update_on_startup
                and auto_update_silent
                and auto_install
                and install_mode == "immediate"
            )
        )
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
        sha256=sha256,
        release_notes=release_notes,
        published_at=manifest.get("published_at") or release_info.get("published_at") or "",
        source=source or release_info.get("html_url") or "config",
        auto_update_on_startup=bool(auto_update_on_startup),
        auto_update_silent=bool(auto_update_silent),
        auto_download=bool(auto_download),
        auto_install=bool(auto_install),
        install_mode=install_mode,
        update_level=update_level,
        rollout_percent=rollout_percent,
        update_ready=has_prepared_update(),
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
        return "无法连接更新服务器，请检查网络或配置系统代理后重试"
    if "timeout" in lowered or "timed out" in lowered:
        return "连接更新服务器超时，请稍后重试"
    if "name or service not known" in lowered or "getaddrinfo" in lowered:
        return "无法解析更新服务器地址，请检查 DNS 或网络"
    if "certificate" in lowered or "ssl" in lowered:
        return "更新服务器 SSL 证书校验失败"
    if text.startswith("更新失败:") or text.startswith("检查更新失败:"):
        return text.split(":", 1)[-1].strip()
    return text or "未知错误"


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
    """返回可用下载地址；优先使用 policy / 腾讯云镜像配置中的直链。"""
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
        raise RuntimeError("没有可用的更新下载地址")

    client_kwargs = _get_http_client_kwargs(settings)
    errors: list[str] = []

    async with httpx.AsyncClient(**client_kwargs) as client:
        for index, url in enumerate(candidates, start=1):
            for attempt in range(1, 3):
                try:
                    _append_log(f"正在下载 ({index}/{len(candidates)}) 第 {attempt} 次尝试...")
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
                                if total_size > 0:
                                    progress = min(95, int(downloaded * 100 / total_size))
                                else:
                                    # 镜像/CDN 常无 Content-Length，按已下载体积估算
                                    mb = downloaded / (1024 * 1024)
                                    progress = min(92, max(3, int(mb * 0.75)))
                                if now - last_ui_update >= 0.25:
                                    _update_progress["progress"] = progress
                                    _update_progress["message"] = (
                                        f"正在下载更新安装包... {progress}%"
                                    )
                                    last_ui_update = now
                    return url
                except Exception as exc:
                    detail = _humanize_update_error(exc)
                    errors.append(f"{url} -> {detail}")
                    log.print_log(f"[Updater] 下载失败: {url} ({detail})", "warning")

    raise RuntimeError(errors[-1] if errors else "所有下载地址均不可用")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_installer_sha256(installer_path: Path, expected_sha256: str) -> None:
    expected = str(expected_sha256 or "").strip().lower()
    if not expected:
        return
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise RuntimeError("更新策略中的安装包校验值格式不正确")
    actual = _file_sha256(installer_path)
    if actual != expected:
        try:
            installer_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError("安装包校验失败，请重新下载或联系发布方")
    _append_log("安装包 SHA256 校验通过")


def _get_update_workspace() -> Path:
    workspace = PathManager.get_temp_dir() / "updates"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _prepared_update_state_path() -> Path:
    return _get_update_workspace() / "prepared_update.json"


def _load_prepared_update_state() -> Dict[str, Any]:
    path = _prepared_update_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    installer_path = Path(str(data.get("download_path") or ""))
    helper_script = Path(str(data.get("helper_script") or ""))
    if not installer_path.exists() or not helper_script.exists():
        return {}
    return data if isinstance(data, dict) else {}


def _save_prepared_update_state(
    *, latest_version: str, installer_path: Path, helper_script: Path, log_file: str = ""
) -> None:
    state = {
        "latest_version": latest_version,
        "download_path": str(installer_path),
        "helper_script": str(helper_script),
        "log_file": log_file,
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _prepared_update_state_path().write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _clear_prepared_update_state() -> None:
    try:
        _prepared_update_state_path().unlink(missing_ok=True)
    except Exception:
        pass


def has_prepared_update() -> bool:
    return bool(_load_prepared_update_state())


def start_prepared_update(reason: str = "manual") -> bool:
    state = _load_prepared_update_state()
    installer_path = Path(str(state.get("download_path") or ""))
    if not installer_path.exists():
        return False
    helper_script = _build_helper_script(installer_path)
    _save_prepared_update_state(
        latest_version=str(state.get("latest_version") or ""),
        installer_path=installer_path,
        helper_script=helper_script,
        log_file=_update_progress.get("log_file", ""),
    )
    _append_log(f"正在启动安装助手: {reason}")
    _spawn_detached_powershell(helper_script)
    _clear_prepared_update_state()
    return True


def _ps_single_quoted(path: Path | str) -> str:
    return str(path).replace("'", "''")


def _resolve_installed_executable(settings: Dict[str, Any]) -> Path:
    """解析安装目录中的主程序 XBoom.exe。"""
    preferred = str(settings.get("restart_executable", EXE_NAME) or EXE_NAME).strip()
    candidates: list[Path] = [PathManager.get_base_dir() / preferred]
    if os.name == "nt":
        for root in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ):
            candidates.append(root / APP_SLUG / EXE_NAME)

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _build_helper_script(installer_path: Path) -> Path:
    settings = _merge_update_config()
    script_path = _get_update_workspace() / "run_update.ps1"
    log_path = _get_update_workspace() / "update-helper.log"
    current_pid = os.getpid()
    app_exe = _resolve_installed_executable(settings)
    install_dir = app_exe.parent.resolve()

    if not utils.get_is_release_ver():
        raise RuntimeError("当前是开发环境，不能执行安装包更新")

    installer_ps = _ps_single_quoted(installer_path)
    log_ps = _ps_single_quoted(log_path)
    install_dir_ps = _ps_single_quoted(str(install_dir))

    script_content = f"""$ErrorActionPreference = 'Continue'
$logFile = '{log_ps}'
function Write-UpdateLog([string]$Message) {{
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}}

$installerPath = '{installer_ps}'
$targetPid = {current_pid}
$targetInstallDir = '{install_dir_ps}'
$appExe = Join-Path $targetInstallDir '{EXE_NAME}'
$argumentList = @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/FORCECLOSEAPPLICATIONS',
    "/DIR=$targetInstallDir"
)

Write-UpdateLog "更新助手启动，目标进程 PID=$targetPid"
Write-UpdateLog "安装包: $installerPath"
Write-UpdateLog "安装目录: $targetInstallDir"
Write-UpdateLog "主程序: $appExe"

# 先短等优雅退出，超时则强杀，避免空等最多 90 秒
for ($i = 0; $i -lt 25; $i++) {{
    if (-not (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {{
        break
    }}
    Start-Sleep -Milliseconds 200
}}
if (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {{
    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    Write-UpdateLog "主进程未在时限内退出，已强制结束 PID=$targetPid"
}}

Get-Process -Name '{APP_SLUG}' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300

$installerExit = $null
try {{
    Write-UpdateLog "开始静默安装（请求管理员权限）..."
    $proc = Start-Process -FilePath $installerPath -ArgumentList $argumentList -Verb RunAs -Wait -PassThru
    $installerExit = $proc.ExitCode
    Write-UpdateLog "安装完成，退出码=$installerExit"
}} catch {{
    Write-UpdateLog "RunAs 安装失败: $($_.Exception.Message)，尝试普通权限..."
    try {{
        $proc = Start-Process -FilePath $installerPath -ArgumentList $argumentList -Wait -PassThru
        $installerExit = $proc.ExitCode
        Write-UpdateLog "普通权限安装完成，退出码=$installerExit"
    }} catch {{
        Write-UpdateLog "安装失败: $($_.Exception.Message)"
        exit 1
    }}
}}

if ($installerExit -ne 0) {{
    Write-UpdateLog "安装程序返回非零退出码: $installerExit"
}}

Start-Sleep -Seconds 1
$running = Get-Process -Name '{APP_SLUG}' -ErrorAction SilentlyContinue
if ($running) {{
    Write-UpdateLog "检测到 {APP_SLUG} 已由安装程序自动拉起 (PID=$($running.Id -join ','))"
    exit 0
}}

if (-not (Test-Path -LiteralPath $appExe)) {{
    $pf = Join-Path $env:ProgramFiles '{APP_SLUG}'
    $candidate = Join-Path $pf '{EXE_NAME}'
    if (Test-Path -LiteralPath $candidate) {{
        $appExe = $candidate
        $targetInstallDir = $pf
    }}
}}

if (Test-Path -LiteralPath $appExe) {{
    Write-UpdateLog "安装程序未自动重启，手动启动: $appExe"
  try {{
    $started = Start-Process -FilePath $appExe -WorkingDirectory $targetInstallDir -PassThru
    Write-UpdateLog "已启动应用 PID=$($started.Id)"
  }} catch {{
    Write-UpdateLog "手动启动失败: $($_.Exception.Message)"
    exit 2
  }}
}} else {{
    Write-UpdateLog "未找到可执行文件: $appExe"
    exit 2
}}
"""
    script_path.write_text(script_content, encoding="utf-8-sig")
    _update_progress["log_file"] = str(log_path)
    return script_path


async def _run_download_update(
    download_url: str,
    latest_version: str,
    expected_sha256: str,
    installer_path: Path,
    settings: Dict[str, Any],
) -> None:
    try:
        candidates = _build_download_candidates(download_url, settings)
        used_url = await _stream_download_with_fallback(candidates, installer_path, settings)
        _append_log(f"下载源: {used_url}")
        _verify_installer_sha256(installer_path, expected_sha256)
        helper_script = _build_helper_script(installer_path)
        _save_prepared_update_state(
            latest_version=latest_version,
            installer_path=installer_path,
            helper_script=helper_script,
            log_file=_update_progress.get("log_file", ""),
        )
        _update_progress.update({
            "status": "ready_to_install",
            "progress": 100,
            "message": "更新已准备完成，正在启动安装…",
            "download_path": str(installer_path),
            "helper_script": str(helper_script),
        })
        _append_log("更新助手已生成")
        _append_log("下载完成，即将自动安装并重启…")
    except Exception as exc:
        detail = _humanize_update_error(exc)
        _update_progress.update({
            "status": "error",
            "progress": 0,
            "message": detail,
            "error": detail,
        })
        _append_log(f"更新失败: {detail}")
        log.print_log(f"[Updater] 下载更新失败: {exc}", "error")


@router.get("/update-policy", response_model=UpdatePolicyResponse)
async def get_update_policy():
    try:
        return await _build_update_policy()
    except Exception as exc:
        log.print_log(f"[Updater] 获取更新策略失败: {exc}", "error")
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
    expected_sha256 = (request.sha256 or policy.sha256 or "").strip()

    if not download_url:
        raise HTTPException(status_code=400, detail="没有可用的更新安装包地址")
    if not utils.get_is_release_ver():
        raise HTTPException(status_code=400, detail="开发环境不支持安装包更新")

    with _download_lock:
        current_status = _update_progress.get("status")
        if current_status == "downloading":
            return {"status": "downloading", "message": "正在下载更新安装包..."}
        if current_status == "ready_to_install":
            return {"status": "ready_to_install", "message": "更新已准备完成"}

        _reset_progress()
        _update_progress["status"] = "downloading"
        _update_progress["progress"] = 1
        _update_progress["message"] = "正在下载更新安装包..."
        _append_log("开始下载更新安装包")
        _append_log(f"目标版本: v{policy.latest_version}")

        workspace = _get_update_workspace()
        installer_path = workspace / _installer_filename(_merge_update_config())
        settings = _merge_update_config()

    asyncio.create_task(
        _run_download_update(
            download_url,
            policy.latest_version,
            expected_sha256,
            installer_path,
            settings,
        )
    )
    return {"status": "downloading", "message": "正在后台下载更新安装包"}


def _spawn_detached_powershell(script_path: Path) -> None:
    """独立启动更新助手，避免主进程退出时连带结束子进程。"""
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


@router.post("/restart-and-update")
async def restart_and_update():
    helper_script = _update_progress.get("helper_script", "")
    if not helper_script or not Path(helper_script).exists():
        if not start_prepared_update("restart-and-update"):
            raise HTTPException(status_code=404, detail="未找到更新助手，请先下载更新")
        threading.Timer(1.2, os._exit, args=(0,)).start()
        return {
            "status": "restarting",
            "message": "正在退出并安装更新",
            "log_file": _update_progress.get("log_file", ""),
        }

    try:
        _append_log("正在启动安装助手…")
        _spawn_detached_powershell(Path(helper_script))
        _clear_prepared_update_state()
        # 留出时间让 PowerShell 独立进程启动，再退出主程序
        threading.Timer(1.2, os._exit, args=(0,)).start()
        return {
            "status": "restarting",
            "message": "正在退出并安装更新",
            "log_file": _update_progress.get("log_file", ""),
        }
    except Exception as exc:
        log.print_log(f"[Updater] 启动更新助手失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=f"启动更新助手失败: {exc}")
