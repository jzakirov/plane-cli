"""Configuration management for plane-cli."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import tomlkit

CONFIG_PATH = Path.home() / ".config" / "plane-cli" / "config.toml"
DEFAULT_BASE_URL = "https://api.plane.so"


@dataclass
class Config:
    api_key: Optional[str] = None
    workspace_slug: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    project: Optional[str] = None
    per_page: int = 20
    # Runtime-only (not persisted)
    pretty: bool = False


def load_config(
    api_key_flag: Optional[str] = None,
    workspace_flag: Optional[str] = None,
    base_url_flag: Optional[str] = None,
    project_flag: Optional[str] = None,
) -> Config:
    """Load config with priority: config.toml < env vars < CLI flags."""
    cfg = Config()

    # 1. Load from config file
    if CONFIG_PATH.exists():
        try:
            doc = tomlkit.parse(CONFIG_PATH.read_text())
            core = doc.get("core", {})
            defaults = doc.get("defaults", {})

            if core.get("api_key"):
                cfg.api_key = str(core["api_key"])
            if core.get("workspace_slug"):
                cfg.workspace_slug = str(core["workspace_slug"])
            if core.get("base_url"):
                cfg.base_url = str(core["base_url"])
            if defaults.get("project"):
                cfg.project = str(defaults["project"])
            if defaults.get("per_page"):
                cfg.per_page = int(defaults["per_page"])
        except Exception:
            pass  # Corrupt config file — silently ignore, use defaults

    # 2. Override with environment variables
    if os.environ.get("PLANE_API_KEY"):
        cfg.api_key = os.environ["PLANE_API_KEY"]
    if os.environ.get("PLANE_WORKSPACE_SLUG"):
        cfg.workspace_slug = os.environ["PLANE_WORKSPACE_SLUG"]
    if os.environ.get("PLANE_BASE_URL"):
        cfg.base_url = os.environ["PLANE_BASE_URL"]
    if os.environ.get("PLANE_PROJECT"):
        cfg.project = os.environ["PLANE_PROJECT"]

    # 3. Override with CLI flags (highest priority)
    if api_key_flag is not None:
        cfg.api_key = api_key_flag
    if workspace_flag is not None:
        cfg.workspace_slug = workspace_flag
    if base_url_flag is not None:
        cfg.base_url = base_url_flag
    if project_flag is not None:
        cfg.project = project_flag

    return cfg


def save_config_key(dotted_key: str, value: str) -> None:
    """Write a dotted config key (e.g. 'defaults.project') to the config file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        doc = tomlkit.parse(CONFIG_PATH.read_text())
    else:
        doc = tomlkit.document()

    parts = dotted_key.split(".", 1)
    if len(parts) == 2:
        section, key = parts
        if section not in doc:
            doc[section] = tomlkit.table()
        doc[section][key] = value
    else:
        doc[dotted_key] = value

    CONFIG_PATH.write_text(tomlkit.dumps(doc))


def save_config(cfg: Config) -> None:
    """Persist a full Config object to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        doc = tomlkit.parse(CONFIG_PATH.read_text())
    else:
        doc = tomlkit.document()

    if "core" not in doc:
        doc["core"] = tomlkit.table()
    if "defaults" not in doc:
        doc["defaults"] = tomlkit.table()

    if cfg.api_key:
        doc["core"]["api_key"] = cfg.api_key
    if cfg.workspace_slug:
        doc["core"]["workspace_slug"] = cfg.workspace_slug
    doc["core"]["base_url"] = cfg.base_url
    if cfg.project:
        doc["defaults"]["project"] = cfg.project
    doc["defaults"]["per_page"] = cfg.per_page

    CONFIG_PATH.write_text(tomlkit.dumps(doc))


def config_as_dict(cfg: Config, reveal: bool = False) -> dict:
    """Return config as a dict, masking api_key unless reveal=True."""
    api_key = cfg.api_key
    if api_key and not reveal:
        # Show first 8 chars + mask
        visible = api_key[:8] if len(api_key) >= 8 else api_key
        api_key = visible + "..." + "*" * 8

    return {
        "core": {
            "api_key": api_key,
            "workspace_slug": cfg.workspace_slug,
            "base_url": cfg.base_url,
        },
        "defaults": {
            "project": cfg.project,
            "per_page": cfg.per_page,
        },
    }
