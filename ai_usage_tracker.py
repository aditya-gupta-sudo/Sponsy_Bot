"""SponsyBot provider-usage ledger and read-only usage summary.

This module does not change or connect to the SponsyBot application database.
It keeps app-observed usage in data/ai_usage.json. Call record_usage() at each
actual external provider request in the backend provider modules.

Quota values are account-specific. Configure them with environment variables:
  GEMINI_DAILY_LIMIT      Optional; must match the active Gemini model/project.
  GEMINI_MODEL            Optional label for the model being tracked.
  GEMINI_RESET_TIMEZONE   Defaults to America/Los_Angeles (Gemini RPD reset).
  TAVILY_MONTHLY_LIMIT    Defaults to 1000 (Tavily free-tier baseline; override
                          if the account plan differs).
  TAVILY_RESET_DAY        Defaults to 1 (Tavily says credits reset on the 1st).
  HUNTER_API_KEY          Optional; enables live Hunter account usage look-up.

The ledger counts only calls made by SponsyBot. Gemini usage in AI Studio from
other apps, keys, or services is not included in this local ledger.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv("SPONSYBOT_AI_USAGE_FILE", str(BASE_DIR / "data" / "ai_usage.json")))
_LOCK = threading.Lock()
logger = logging.getLogger("sponsybot.ai_usage")


def _positive_int_env(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
        return value if value >= 0 else default
    except ValueError:
        return default


def _zone(name: str, default: str = "UTC") -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(default)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_records() -> list[dict[str, Any]]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return [item for item in data["records"] if isinstance(item, dict)]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _write_records(records: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = DATA_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(DATA_FILE)


def record_usage(provider: str, units: float = 1, operation: str = "API request", model: str | None = None) -> None:
    """Record usage for one provider request or explicit provider-reported units.

    provider must be one of: gemini, tavily, groq, hunter. Avoid recording API keys,
    prompts, emails, request bodies, or other sensitive data here.
    """
    provider = provider.strip().lower()
    if provider not in {"gemini", "tavily", "groq", "hunter"}:
        raise ValueError("provider must be gemini, tavily, groq, or hunter")
    try:
        amount = float(units)
    except (TypeError, ValueError) as exc:
        raise ValueError("units must be a non-negative number") from exc
    if amount < 0:
        raise ValueError("units must be a non-negative number")
    if amount == 0:
        return

    record = {
        "provider": provider,
        "occurred_at": _now_utc().isoformat(),
        "units": amount,
        "operation": str(operation)[:100],
        "model": str(model)[:100] if model else None,
    }
    with _LOCK:
        try:
            records = _read_records()
            cutoff = _now_utc() - timedelta(days=400)
            retained: list[dict[str, Any]] = []
            for item in records:
                try:
                    timestamp = datetime.fromisoformat(str(item.get("occurred_at", "")).replace("Z", "+00:00"))
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    if timestamp >= cutoff:
                        retained.append(item)
                except (TypeError, ValueError):
                    continue
            retained.append(record)
            _write_records(retained)
        except OSError:
            # Quota tracking is observability only; a read-only filesystem must
            # never cause sponsor research or email generation to fail.
            logger.exception("Could not write the local AI usage ledger.")


def _record_total(records: list[dict[str, Any]], provider: str, start: datetime, end: datetime) -> float:
    total = 0.0
    for item in records:
        if item.get("provider") != provider:
            continue
        try:
            timestamp = datetime.fromisoformat(str(item.get("occurred_at", "")).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = timestamp.astimezone(start.tzinfo)
            if start <= timestamp < end:
                total += float(item.get("units", 1))
        except (TypeError, ValueError):
            continue
    return total


def _period_window(period: str, tz: ZoneInfo, reset_day: int = 1) -> tuple[datetime, datetime]:
    now = _now_utc().astimezone(tz)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    # Monthly window, supporting a configurable reset day (clamped for short months).
    def reset_date(year: int, month: int) -> datetime:
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        return now.replace(year=year, month=month, day=min(max(reset_day, 1), last_day), hour=0, minute=0, second=0, microsecond=0)

    this_reset = reset_date(now.year, now.month)
    if now >= this_reset:
        start = this_reset
        if now.month == 12:
            next_year, next_month = now.year + 1, 1
        else:
            next_year, next_month = now.year, now.month + 1
    else:
        if now.month == 1:
            prior_year, prior_month = now.year - 1, 12
        else:
            prior_year, prior_month = now.year, now.month - 1
        start = reset_date(prior_year, prior_month)
        next_year, next_month = now.year, now.month
    end = reset_date(next_year, next_month)
    if end <= start:
        end = start + timedelta(days=28)
    return start, end


def _provider_summary(
    records: list[dict[str, Any]], *, provider: str, name: str, description: str,
    unit: str, period: str, limit: int | None, tz_name: str,
    reset_day: int = 1, reset_note: str = "",
) -> dict[str, Any]:
    tz = _zone(tz_name)
    start, end = _period_window(period, tz, reset_day)
    used = _record_total(records, provider, start, end)
    remaining = max(0, limit - used) if limit is not None else None
    status = "unconfigured" if limit is None else ("exhausted" if used >= limit else "ok")
    if unit == "requests" or unit == "search requests":
        used_value = int(used) if used.is_integer() else used
        remaining_value = int(remaining) if remaining is not None and remaining.is_integer() else remaining
    else:
        used_value = int(used) if used.is_integer() else round(used, 2)
        remaining_value = int(remaining) if remaining is not None and remaining.is_integer() else (round(remaining, 2) if remaining is not None else None)

    return {
        "id": provider,
        "name": name,
        "description": description,
        "unit": unit,
        "period": period,
        "period_label": "Daily" if period == "daily" else "Monthly cycle",
        "used": used_value,
        "limit": limit,
        "remaining": remaining_value,
        "remaining_label": "App-estimated remaining",
        "status": status,
        "reset_at": end.isoformat(),
        "reset_note": reset_note or f"Cycle configured for {tz_name}",
        "source_label": "SponsyBot request ledger; does not include calls made elsewhere",
    }


def _get_live_hunter_usage() -> list[dict[str, Any]] | None:
    api_key = os.getenv("HUNTER_API_KEY", "").strip()
    if not api_key:
        return None

    url = "https://api.hunter.io/v2/usage?" + urlencode({"api_key": api_key})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "SponsyBotUsageDashboard/1.0"})
    try:
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    request_data = data.get("requests") if isinstance(data, dict) else None
    if not isinstance(request_data, dict):
        return None

    reset_date = data.get("reset_date")
    reset_at = None
    if reset_date:
        try:
            reset_at = datetime.fromisoformat(str(reset_date)).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            reset_at = None

    rows: list[dict[str, Any]] = []
    credits = request_data.get("credits")
    if isinstance(credits, dict):
        rows.append({
            "id": "hunter", "name": "Hunter.io", "description": "Live account credits from Hunter's usage API",
            "unit": "credits", "period": "billing period", "period_label": "Current billing period",
            "used": credits.get("used"), "limit": credits.get("available"),
            "remaining": credits.get("remaining"), "remaining_label": "Provider remaining",
            "status": "exhausted" if float(credits.get("remaining", 1) or 0) <= 0 else "ok",
            "reset_at": reset_at, "reset_note": f"Hunter billing reset date: {reset_date}" if reset_date else "Reset date not returned",
            "source_label": "Live Hunter usage API",
        })
        return rows

    for key, label in (("searches", "Hunter searches"), ("verifications", "Hunter verifications")):
        quota = request_data.get(key)
        if not isinstance(quota, dict):
            continue
        remaining = quota.get("remaining")
        rows.append({
            "id": f"hunter-{key}", "name": label,
            "description": "Live account quota from Hunter's usage API",
            "unit": "requests", "period": "billing period", "period_label": "Current billing period",
            "used": quota.get("used"), "limit": quota.get("available"), "remaining": remaining,
            "remaining_label": "Provider remaining",
            "status": "exhausted" if remaining is not None and float(remaining) <= 0 else "ok",
            "reset_at": reset_at, "reset_note": f"Hunter billing reset date: {reset_date}" if reset_date else "Reset date not returned",
            "source_label": "Live Hunter usage API",
        })
    return rows or None


def get_ai_usage_summary() -> dict[str, Any]:
    """Build the JSON schema consumed by frontend/ai-usage.js."""
    with _LOCK:
        records = _read_records()
    gemini_limit = _positive_int_env("GEMINI_DAILY_LIMIT")
    tavily_limit = _positive_int_env("TAVILY_MONTHLY_LIMIT", 1000)
    gemini_tz = os.getenv("GEMINI_RESET_TIMEZONE", "America/Los_Angeles")
    tavily_tz = os.getenv("TAVILY_RESET_TIMEZONE", "UTC")
    tavily_reset_day = _positive_int_env("TAVILY_RESET_DAY", 1) or 1

    tracking_ready = os.getenv("AI_USAGE_TRACKING_READY", "true").strip().lower() in {"1", "true", "yes", "on"}

    providers = [
        _provider_summary(
            records, provider="gemini", name="Google Gemini API",
            description=(f"Tracked model: {os.getenv('GEMINI_MODEL', 'set GEMINI_MODEL to label the active model')}. "
                         "Gemini rate limits can vary by model, project, and usage tier."),
            unit="requests", period="daily", limit=gemini_limit, tz_name=gemini_tz,
            reset_note="Estimated request/day reset at midnight Pacific Time; verify active model quota in AI Studio.",
        ),
        _provider_summary(
            records, provider="tavily", name="Tavily Search API",
            description="Credits reported by successful Tavily responses where available; otherwise one tracked basic-search credit per call.",
            unit="tracked credits", period="monthly", limit=tavily_limit, tz_name=tavily_tz,
            reset_day=tavily_reset_day,
            reset_note=f"Configured monthly reset on day {tavily_reset_day} ({tavily_tz}); verify the account plan.",
        ),
        _provider_summary(
            records, provider="groq", name="Groq API",
            description=f"SponsyBot-tracked Groq requests. Active models: {os.getenv('GROQ_MODEL', 'not configured')} and {os.getenv('GROQ_EMAIL_MODEL', os.getenv('GROQ_MODEL', 'not configured'))}. This is a local request budget, not provider-reported token quota.",
            unit="requests", period="daily", limit=_positive_int_env("GROQ_DAILY_LIMIT"),
            tz_name=os.getenv("GROQ_RESET_TIMEZONE", "UTC"),
            reset_note="Estimated reset at midnight in the configured Groq reset timezone.",
        ),
    ]

    # Do not expose a misleading "remaining" value until all relevant backend
    # call sites have been instrumented. Local counters otherwise start at zero.
    if not tracking_ready:
        for item in providers:
            item["limit"] = None
            item["remaining"] = None
            item["status"] = "unconfigured"
            item["source_label"] = "Waiting for provider-call instrumentation; remaining quota withheld"
            item["description"] += " Live remaining quota is not yet available from this local tracker."

    hunter_rows = _get_live_hunter_usage()
    if hunter_rows:
        providers.extend(hunter_rows)
    else:
        hunter_fallback = _provider_summary(
            records, provider="hunter", name="Hunter.io",
            description="Contact-discovery usage. Add HUNTER_API_KEY to enable a live account quota lookup.",
            unit="tracked requests", period="monthly", limit=_positive_int_env("HUNTER_MONTHLY_LIMIT"),
            tz_name=os.getenv("HUNTER_RESET_TIMEZONE", "UTC"),
            reset_day=_positive_int_env("HUNTER_RESET_DAY", 1) or 1,
            reset_note="Local tracking only until HUNTER_API_KEY is configured; billing-cycle reset may differ.",
        )
        if not tracking_ready:
            hunter_fallback["limit"] = None
            hunter_fallback["remaining"] = None
            hunter_fallback["status"] = "unconfigured"
            hunter_fallback["source_label"] = "Waiting for provider-call instrumentation; remaining quota withheld"
        providers.append(hunter_fallback)

    return {
        "generated_at": _now_utc().isoformat(),
        "tracking_ready": tracking_ready,
        "data_source": "SponsyBot usage ledger plus live Hunter usage API when configured",
        "providers": providers,
    }
