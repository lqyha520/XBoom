from pathlib import Path

from src.ai_write_x.utils.path_manager import PathManager


def test_development_paths_remain_inside_repository():
    root = PathManager.get_root_dir().resolve()
    package_root = Path(__file__).resolve().parents[1]

    assert root == package_root
    assert PathManager.get_output_dir().resolve().is_relative_to(root)
    assert PathManager.get_image_dir().resolve().is_relative_to(root)
    assert PathManager.get_log_dir().resolve().is_relative_to(root)
