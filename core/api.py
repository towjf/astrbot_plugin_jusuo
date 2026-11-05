"""居所助手数据接口（Supabase REST）。

站点 https://jusuo.playmmo.cn 是纯前端 SPA，数据全部存放在 Supabase
（db.playmmo.cn）里，公开可读（anon key）。这里直接对接 REST 接口，
不依赖网页渲染，速度快且稳定。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "https://db.playmmo.cn"
# 站点前端内置的公开 anon key（仅具备 RLS 允许的只读权限）
DEFAULT_ANON_KEY = (
    "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJyb2xlIjogImFub24iLCJpc3MiOiAic3VwYWJhc2UtZGVtbyIsImlhdCI6IDE3ODcxNjIzNjMsImV4cCI6IDIxMDI1MjIzNjN9.Qe7GD4i5-auaMmvL73gbasJLdjo8-tPUHWQ2KmztXek"
)


class JusuoAPIError(RuntimeError):
    """接口调用失败。"""


class JusuoAPI:
    """居所助手只读数据客户端。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        anon_key: str = DEFAULT_ANON_KEY,
        *,
        timeout: float = 15.0,
        cache_ttl: int = 90,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.anon_key = anon_key or DEFAULT_ANON_KEY
        self.timeout = timeout
        self.cache_ttl = max(0, cache_ttl)
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    # ---------------- 基础设施 ----------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.anon_key}",
                "Accept": "application/json",
            }
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                trust_env=True,
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retries: int = 2,
    ) -> Any:
        url = f"{self.base_url}{path}"
        session = await self._get_session()
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with session.get(url, params=params) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        if not text.strip():
                            return []
                        return await resp.json(content_type=None)
                    raise JusuoAPIError(
                        f"HTTP {resp.status}: {text[:200]}"
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError, JusuoAPIError) as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
                raise JusuoAPIError(f"请求失败: {exc}") from exc
        raise JusuoAPIError(f"请求失败: {last_error}")

    async def _table(self, table: str, params: dict[str, Any]) -> list[dict]:
        data = await self._request(f"/rest/v1/{table}", params)
        if isinstance(data, dict):
            return [data]
        return list(data or [])

    def _cached(self, key: str) -> Any | None:
        item = self._cache.get(key)
        if not item:
            return None
        ts, value = item
        if self.cache_ttl and time.time() - ts < self.cache_ttl:
            return value
        if not self.cache_ttl:
            return None
        return None

    def _store(self, key: str, value: Any) -> Any:
        self._cache[key] = (time.time(), value)
        return value

    # ---------------- 基础数据 ----------------

    async def unit_prices(self) -> dict[str, dict[str, float]]:
        """返回 {"crop": {名称: 单价}, "ranch": {名称: 单价}}。"""
        cached = self._cached("unit_prices")
        if cached is not None:
            return cached
        rows = await self._table(
            "unit_prices",
            {"select": "name,category,unit_price", "order": "category.asc,name.asc"},
        )
        result: dict[str, dict[str, float]] = {"crop": {}, "ranch": {}}
        for row in rows:
            category = row.get("category") or "crop"
            result.setdefault(category, {})[row.get("name", "")] = float(
                row.get("unit_price") or 0
            )
        return self._store("unit_prices", result)

    async def ranch_presets(self) -> dict[str, str]:
        """牧场产物预设 id -> 名称。"""
        cached = self._cached("ranch_presets")
        if cached is not None:
            return cached
        rows = await self._table(
            "ranch_product_presets",
            {"select": "id,name", "limit": 500},
        )
        return self._store("ranch_presets", {r["id"]: r["name"] for r in rows})

    async def furniture_presets(self) -> dict[str, dict]:
        """家具预设 id -> {name, quality, merchant_name}。"""
        cached = self._cached("furniture_presets")
        if cached is not None:
            return cached
        rows = await self._table(
            "furniture_presets",
            {"select": "id,name,quality,merchant_name", "limit": 1000},
        )
        return self._store(
            "furniture_presets",
            {r["id"]: r for r in rows},
        )

    async def page_settings(self) -> dict[str, bool]:
        """各页面开关（居所/牧场/模板等）。"""
        cached = self._cached("page_settings")
        if cached is not None:
            return cached
        rows = await self._table("page_settings", {"select": "key,enabled"})
        return self._store(
            "page_settings", {r["key"]: bool(r.get("enabled")) for r in rows}
        )

    # ---------------- 业务数据 ----------------

    async def residence_entries(self, limit: int = 300) -> list[dict]:
        """居所作物高倍收购条目（仅在售）。"""
        return await self._table(
            "residence_entries",
            {
                "select": (
                    "id,uid,crop_name,quantity,price_multiplier,merchant_name,"
                    "residence_level,expires_at,created_at,like_count,"
                    "is_limit_reached,guild_maxed,sale_price"
                ),
                "expires_at": "gt.now()",
                "is_reported": "eq.false",
                "order": "price_multiplier.desc,expires_at.desc",
                "limit": limit,
            },
        )

    async def ranch_entries(self, limit: int = 300) -> list[dict]:
        """牧场动物产物高倍收购条目（仅在售）。"""
        return await self._table(
            "ranch_entries",
            {
                "select": (
                    "id,uid,product_preset_id,quantity,price_multiplier,merchant_name,"
                    "animal_stall_level,expires_at,created_at,like_count,"
                    "is_limit_reached,guild_maxed,sale_price"
                ),
                "expires_at": "gt.now()",
                "is_reported": "eq.false",
                "order": "price_multiplier.desc,expires_at.desc",
                "limit": limit,
            },
        )

    async def furniture_entries(self, limit: int = 200) -> list[dict]:
        """家具商人分享条目（仅在售）。"""
        return await self._table(
            "furniture_entries",
            {
                "select": (
                    "id,merchant_name,furniture_names,furniture_ids,expires_at,"
                    "created_at,like_count,is_limit_reached"
                ),
                "expires_at": "gt.now()",
                "is_reported": "eq.false",
                "order": "expires_at.desc",
                "limit": limit,
            },
        )

    async def template_entries(self, limit: int = 60) -> list[dict]:
        """居所模板分享条目（按热度排序）。"""
        return await self._table(
            "template_entries",
            {
                "select": (
                    "id,title,description,region,like_count,favorite_count,"
                    "heat_score,video_platform,video_url,cover_url,is_featured,"
                    "is_timed,timed_expires_at,created_at"
                ),
                "is_active": "eq.true",
                "order": "heat_score.desc,like_count.desc",
                "limit": limit,
            },
        )

    async def market_matrix(
        self,
        source: str = "crop",
        metric: str = "price",
        hours: int = 24,
    ) -> dict:
        """行情矩阵（站点自带的 edge function）。"""
        return await self._request(
            "/functions/v1/market-matrix",
            {
                "source": source,
                "metric": metric,
                "hours": hours,
                "_t": int(time.time() * 1000),
            },
        )
