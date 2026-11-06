"""在 `git push` 被网络阻断时，用 GitHub Git Data API 同步提交。

适用场景：本机访问 github.com:443 超时 / 代理 `CONNECT aborted`，但 api.github.com 可达。

特性：
- **增量**：先读远端 `refs/heads/{branch}`，只重放它之后的提交，不重写已有历史；
- **保 SHA**：把原提交的 author / committer 与时间戳一并提交，tree 内容一致，
  因此远端生成的 commit SHA 与本地的相同；
- **快进优先**：远端是本地祖先时用非强制更新（`PATCH refs` 不带 force）。

认证复用本机 git 凭据（Git Credential Manager），不读取、不打印 token。

用法：
    python scripts/push_via_api.py                     # 推当前分支到 origin
    python scripts/push_via_api.py --repo towjf/x --branch main
    python scripts/push_via_api.py --dry-run           # 只看要推哪些提交
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


# ---------------------------------------------------------------- 主体


def commit_meta(sha: str) -> tuple[str, str, str, str, str, str]:
    """取 author/committer 的名字、邮箱、时间（保持远端 SHA 与本地一致）。"""
    out = git("show", "-s", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", sha)
    parts = out.strip().split("\x00")
    if len(parts) != 6:
        raise SystemExit(f"解析提交信息失败: {sha} -> {parts}")
    return tuple(parts)  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="", help="owner/name，默认从 origin 解析")
    parser.add_argument("--branch", default="", help="默认取当前分支")
    parser.add_argument("--dry-run", action="store_true")
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

    try:
        remote = api(f"/repos/{repo}/git/ref/heads/{branch}", token)
        remote_head = remote["object"]["sha"]
    except SystemExit:
        remote_head = ""

    if remote_head == local_head:
        print(f"{repo}#{branch} 已是最新（{local_head[:8]}），无需推送")
        return 0

    if remote_head:
        is_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", remote_head, local_head], cwd=ROOT
        ).returncode
        if is_ancestor != 0:
            raise SystemExit(
                f"远端 {remote_head[:8]} 不是本地 HEAD 的祖先，直接重放会破坏历史；"
                "请先 git pull / 处理分叉后再推"
            )
        commits = git("rev-list", "--reverse", f"{remote_head}..{local_head}").split()
        print(f"远端已有 {remote_head[:8]}，本次增量推送 {len(commits)} 个提交")
    else:
        commits = git("rev-list", "--reverse", "HEAD").split()
        print(f"远端为空，全量推送 {len(commits)} 个提交")

    if args.dry_run:
        for sha in commits:
            print("  ", sha[:8], git("log", "-1", "--pretty=%s", sha).strip()[:60])
        return 0

    if not remote_head:
        # 空仓库不允许建 blob，先塞一个占位提交
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
    parent = remote_head or None
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
        same = "SHA 一致" if parent == sha else f"本地 {sha[:8]}"
        print(f"  [{index}/{len(commits)}] {message.splitlines()[0][:52]} -> {parent[:8]} ({same})")

    if remote_head:
        api(
            f"/repos/{repo}/git/refs/heads/{branch}",
            token,
            method="PATCH",
            payload={"sha": parent},
        )
        print(f"已快进 {branch} -> {parent[:8]}")
    else:
        api(
            f"/repos/{repo}/git/refs",
            token,
            method="POST",
            payload={"ref": f"refs/heads/{branch}", "sha": parent},
        )
        print(f"已创建 {branch} -> {parent[:8]}")

    head = api(f"/repos/{repo}/commits/{branch}", token)
    print(f"远端 HEAD: {head['sha'][:8]}  本地 HEAD: {local_head[:8]}  一致: {head['sha'] == local_head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
