# -*- coding: utf-8 -*-
"""Shared request/response models for web API routers."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ReferenceConfig(BaseModel):
    """Reference-mode options for content generation."""

    template_category: Optional[str] = None
    template_name: Optional[str] = None
    reference_urls: Optional[str] = None
    reference_ratio: Optional[int] = 30
    reference_article_id: Optional[str] = None


class GenerateRequest(BaseModel):
    """Content generation request payload."""

    topic: Optional[str] = ""
    platform: Optional[str] = ""
    reference: Optional[ReferenceConfig] = None
    article_count: Optional[int] = 1
    post_action: Optional[str] = "none"
    ai_beautify: Optional[bool] = False
    filter_processed: Optional[bool] = False
    fast_mode: Optional[bool] = False
    collection_mode: Optional[bool] = False
