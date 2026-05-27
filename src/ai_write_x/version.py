# -*- coding: UTF-8 -*-
"""小爆来咯 版本信息"""

from datetime import datetime

__version__ = "1.0.2"
__author__ = "小爆来咯"
__build_time__ = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_version():
    return __version__


def get_author():
    return __author__


def get_version_with_prefix():
    return f"v{__version__}"


def get_build_info():
    """V23: 返回完整构建信息字典"""
    return {
        "version": __version__,
        "version_display": f"v{__version__}",
        "author": __author__,
        "build_time": __build_time__,
        "codename": "Cognitive Singularity",
        "features": [
            "Autonomous Agent Swarms",
            "Collective Consciousness",
            "Distributed Consensus",
            "Knowledge Organism",
            "Self-Healing System",
            "Cognitive Architecture",
            "Neural Resonance",
            "Multi-Modal Fusion",
            "Predictive Intelligence",
            "Quantum Flux Architecture",
        ]
    }
