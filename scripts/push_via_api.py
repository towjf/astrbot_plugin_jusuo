"""在 `git push` 被网络阻断时，用 GitHub Git Data API 同步提交。

适用场景：本机访问 github.com:443 超时 / 代理 `CONNECT aborted`，但 api.github.com 可达。

关键点：
- 远端 commit SHA 与本地不一定相同：GitHub 会把提交时区规范化成 UTC（+0000），
  本地是 +0800，于是同样的内容算出不同哈希（tree 完全一致）。因此脚本用
  `.git/api_push_map.json` 记录「本地 SHA → 远端 SHA」的映射，下次推送时据此
  找到分叉点，做到增量推送、不重写远端历史。
- 已知远端是本地某个提交的直接祖先（例如之前用真 git push 过）时，直接用该祖先为基点。

用法：
    python scripts/push_via_api.py                  # 推送当前分支
    python scripts/push_via_api.py --dry-run        # 只看要推哪些提交
    python scripts/push_via_api.py --mirror         # 强行全量重放并覆盖远端（会重写历史）
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
MAP_FILE = ROOT / ".git" / "api_push_map.json"


# ---------------------------------------------------------------- git / api


def git(*args: str, binary: bool = False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败: {proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def get_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password=") :]
    raise SystemExit("未取到 GitHub 凭据，请先完成一次 git 登录")


def api(path: str, token: str, method: str = "GET", payload: dict | None = None, tries: int = 4):
    data = json.dumps(payload).encode() if payload is not None else None
    last = ""
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(f"{API}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "git-push-via-api")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode()
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:300]
            if exc.code >= 500 and attempt < tries:
                last = f"HTTP {exc.code}"
                time.sleep(1.5 * attempt)
                continue
            raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail}")
        except Exception as exc:  # noqa: BLE001  代理抖动
            last = f"{type(exc).__name__}: {exc}"
            if attempt < tries:
                time.sleep(1.5 * attempt)
                continue
            raise SystemExit(f"{method} {path} 连续 {tries} 次失败: {last}")
    raise SystemExit(f"{method} {path} 失败: {last}")


# ---------------------------------------------------------------- 映射表


def load_map() -> dict[str, str]:
    if MAP_FILE.is_file():
        try:
            return json.loads(MAP_FILE.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_map(mapping: dict[str, str]) -> None:
    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAP_FILE.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")


def commit_meta(sha: str) -> tuple[str, str, str, str, str, str]:
    out = git("show", "-s", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", sha)
    parts = out.rstrip("\n").split("\x00")
    if len(parts) != 6:
        raise SystemExit(f"解析提交信息失败: {sha} -> {parts}")
    return tuple(parts)  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="", help="owner/name，默认从 origin 解析")
    parser.add_argument("--branch", default="", help="默认取当前分支")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mirror", action="store_true", help="全量重放并强制覆盖远端分支")
    args = parser.parse_args()

    branch = args.branch or git("rev-parse", "--abbrev-ref", "HEAD").strip()
    repo = args.repo
    if not repo:
        url = git("remote", "get-url", "origin").strip()
        matched = re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", url)
        if not matched:
            raise SystemExit(f"无法从 origin 解析仓库名: {url}")
        repo = f"{matched.group(1)}/{matched.group(2)}"

    token = get_token()
    local_head = git("rev-parse", "HEAD").strip()
    mapping = load_map()

    try:
        remote_head = api(f"/repos/{repo}/git/ref/heads/{branch}", token)["object"]["sha"]
    except SystemExit:
        remote_head = ""

    if remote_head == local_head:
        print(f"{repo}#{branch} 已是最新（{local_head[:8]}）")
        return 0

    # 找增量基点
    base = ""
    mirror = args.mirror or not remote_head
    if remote_head and not args.mirror:
        if remote_head in mapping.values():
            base = next(k for k, v in mapping.items() if v == remote_head)
            print(
                f"远端 {remote_head[:8]} 对应本地 {base[:8]}（来自映射表），在其后增量推送；"
                "新提交的父提交用远端 SHA"
            )
        elif subprocess.run(
            ["git", "merge-base", "--is-ancestor", remote_head, local_head],
            cwd=ROOT,
            capture_output=True,
        ).returncode == 0:
            base = remote_head
            print(f"远端 {remote_head[:8]} 是本地祖先，增量推送")
        else:
            raise SystemExit(
                f"远端 HEAD {remote_head[:8]} 与本地历史无对应关系（映射表里也没有）。\n"
                "如果确认要以本地为准重写远端分支，加 --mirror 再跑一次。"
            )
    elif remote_head:
        print(f"--mirror：以本地历史覆盖远端 {branch}")

    commits = git("rev-list", "--reverse", f"{base}..{local_head}" if base else "HEAD").split()
    if not commits:
        print("没有需要推送的提交")
        return 0
    print(f"本次推送 {len(commits)} 个提交：")
    for sha in commits:
        print("  ", sha[:8], git("log", "-1", "--pretty=%s", sha).strip()[:58])
    if args.dry_run:
        return 0

    if not remote_head:
        api(
            f"/repos/{repo}/contents/.push-init",
            token,
            method="PUT",
            payload={
                "message": "chore: 初始化仓库",
                "content": base64.b64encode(b"init\n").decode(),
            },
        )
        print("空仓库已初始化")

    blob_cache: dict[str, str] = {}
    # 第一个新提交的父提交必须是**远端**的 SHA：base 是本地 SHA，远端可能不同
    parent = None if mirror else (remote_head or None)
    for index, sha in enumerate(commits, 1):
        message = git("log", "-1", "--pretty=%B", sha).rstrip("\n")
        items = []
        for line in git("ls-tree", "-r", sha).splitlines():
            meta, path = line.split("\t", 1)
            mode, kind, blob_sha = meta.split()
            if kind != "blob":
                continue
            if blob_sha not in blob_cache:
                content = git("cat-file", "blob", blob_sha, binary=True)
                blob = api(
                    f"/repos/{repo}/git/blobs",
                    token,
                    method="POST",
                    payload={
                        "content": base64.b64encode(content).decode(),
                        "encoding": "base64",
                    },
                )
                blob_cache[blob_sha] = blob["sha"]
            items.append({"path": path, "mode": mode, "type": "blob", "sha": blob_cache[blob_sha]})

        tree = api(f"/repos/{repo}/git/trees", token, method="POST", payload={"tree": items})
        an, ae, ad, cn, ce, cd = commit_meta(sha)
        payload: dict = {
            "message": message,
            "tree": tree["sha"],
            "author": {"name": an, "email": ae, "date": ad},
            "committer": {"name": cn, "email": ce, "date": cd},
        }
        if parent:
            payload["parents"] = [parent]
        created = api(f"/repos/{repo}/git/commits", token, method="POST", payload=payload)
        parent = created["sha"]
        mapping[sha] = parent
        save_map(mapping)
        note = "SHA 相同" if parent == sha else f"本地 {sha[:8]}（远端时区规范化为 UTC，SHA 不同）"
        print(f"  [{index}/{len(commits)}] {message.splitlines()[0][:50]} -> {parent[:8]}  {note}")

    if remote_head and not mirror:
        api(
            f"/repos/{repo}/git/refs/heads/{branch}",
            token,
            method="PATCH",
            payload={"sha": parent},
        )
        print(f"已快进 {branch} -> {parent[:8]}")
    elif remote_head:
        api(
            f"/repos/{repo}/git/refs/heads/{branch}",
            token,
            method="PATCH",
            payload={"sha": parent, "force": True},
        )
        print(f"已强制更新 {branch} -> {parent[:8]}")
    else:
        api(
            f"/repos/{repo}/git/refs",
            token,
            method="POST",
            payload={"ref": f"refs/heads/{branch}", "sha": parent},
        )
        print(f"已创建 {branch} -> {parent[:8]}")

    head = api(f"/repos/{repo}/commits/{branch}", token)
    print(f"远端 HEAD {head['sha'][:8]} / 本地 HEAD {local_head[:8]}（内容一致，SHA 因时区规范化可能不同）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
