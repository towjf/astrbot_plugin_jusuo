"""构建插件市场发布包：python scripts/build_release.py

产物：dist/astrbot_plugin_jusuo.zip（只含运行所需文件，可直接上传到插件市场）
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ZIP = DIST / "astrbot_plugin_jusuo.zip"

RUNTIME_FILES = (
    "main.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "logo.png",
)
RUNTIME_DIRS = ("core",)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    ZIP.unlink(missing_ok=True)

    written: list[str] = []
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in RUNTIME_FILES:
            path = ROOT / name
            if path.is_file():
                archive.write(path, name)
                written.append(name)
        for dirname in RUNTIME_DIRS:
            for path in sorted((ROOT / dirname).rglob("*.py")):
                rel = path.relative_to(ROOT).as_posix()
                if "__pycache__" in rel:
                    continue
                archive.write(path, rel)
                written.append(rel)

    size_kb = ZIP.stat().st_size / 1024
    print(f"已生成 {ZIP}（{len(written)} 个文件，{size_kb:.1f} KB）")
    if size_kb > 16 * 1024:
        raise SystemExit("警告：超过插件市场 16MB 限制")
    for name in written:
        print("  ", name)


if __name__ == "__main__":
    main()
