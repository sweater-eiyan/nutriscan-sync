import os
import json
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WEBHOOK_SITE_URL = os.environ.get("WEBHOOK_SITE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

JST = timezone(timedelta(hours=9))


def fetch_webhook_requests():
    if not WEBHOOK_SITE_URL:
        raise RuntimeError("WEBHOOK_SITE_URL is not set")
    url = WEBHOOK_SITE_URL
    headers = {
        "Accept": "application/json",
    }
    params = {
        "per_page": 100,
        "sorting": "newest",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def parse_payload(item):
    """Webhook.site の1リクエストから payload dict を返す。失敗時は None。"""
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if not content:
        return None
    # 1段目: content が JSON 文字列かどうか試みる
    try:
        outer = json.loads(content)
    except Exception:
        return None
    if not isinstance(outer, dict):
        return None
    # 2段目: payload フィールドを取り出す
    payload_raw = outer.get("payload")
    if payload_raw is None:
        return None
    if isinstance(payload_raw, dict):
        return payload_raw
    # payload が文字列の場合はさらに JSON パース
    try:
        payload = json.loads(payload_raw)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return None


def group_by_date(request_items):
    """
    各リクエストから metric_type / value / timestamp を取り出し、
    JST 日付をキーに {weight, body_fat} を集約する。
    戻り値: {"YYYY-MM-DD": {"weight_kg": float|None, "body_fat_pct": float|None, "source": str}}
    """
    day_data = defaultdict(lambda: {"weight_kg": None, "body_fat_pct": None, "source": "shortcut"})

    for item in request_items:
        payload = parse_payload(item)
        if payload is None:
            continue
        metric_type = payload.get("metric_type")
        timestamp_str = payload.get("timestamp")
        value = payload.get("value")
        source = payload.get("source", "shortcut")

        if not metric_type or timestamp_str is None or value is None:
            continue
        try:
            value_num = round(float(value), 2)
        except Exception:
            continue

        # timestamp を JST 日付に変換
        try:
            # +0900 などのオフセット付き文字列に対応
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            dt_jst = dt.astimezone(JST)
            date_key = dt_jst.strftime("%Y-%m-%d")
        except Exception:
            continue

        if metric_type == "weight":
            day_data[date_key]["weight_kg"] = value_num
            day_data[date_key]["source"] = source
        elif metric_type == "body_fat":
            day_data[date_key]["body_fat_pct"] = value_num
            day_data[date_key]["source"] = source

    return day_data


def build_records(day_data):
    """
    day_data を nutriscan-cloud の body_metrics スキーマに変換する。
    lbm_kg = weight_kg * (1 - body_fat_pct / 100)
    """
    records = []
    for date_str, metrics in day_data.items():
        weight_kg = metrics.get("weight_kg")
        body_fat_pct = metrics.get("body_fat_pct")
        source = metrics.get("source", "shortcut")

        # weight か body_fat のどちらか一方でもあればレコード作成
        if weight_kg is None and body_fat_pct is None:
            continue

        lbm_kg = None
        if weight_kg is not None and body_fat_pct is not None:
            lbm_kg = round(weight_kg * (1 - body_fat_pct / 100), 2)

        record = {
            "date": date_str,
            "source": source,
        }
        if weight_kg is not None:
            record["weight_kg"] = weight_kg
        if body_fat_pct is not None:
            record["body_fat_pct"] = body_fat_pct
        if lbm_kg is not None:
            record["lbm_kg"] = lbm_kg

        records.append(record)
    return records


def upsert_to_supabase(records):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is not set")
    if not records:
        print("No records to upsert into Supabase.")
        return
    url = f"{SUPABASE_URL}/rest/v1/body_metrics"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    resp = requests.post(url, headers=headers, data=json.dumps(records), timeout=30)
    if not resp.ok:
        print("Supabase error status:", resp.status_code)
        print("Supabase error body:", resp.text)
        resp.raise_for_status()
    result = resp.json()
    print(f"Upserted {len(result)} record(s) into Supabase body_metrics.")
    for r in result:
        print(" -", r)


def main():
    print("Fetching webhook requests...")
    items = fetch_webhook_requests()
    print(f"Fetched {len(items)} requests from Webhook.site.")

    print("Grouping by date...")
    day_data = group_by_date(items)
    print(f"Found data for {len(day_data)} date(s): {list(day_data.keys())}")

    print("Building records...")
    records = build_records(day_data)
    print(f"Built {len(records)} record(s):")
    for r in records:
        print(" -", r)

    print("Upserting into Supabase...")
    upsert_to_supabase(records)
    print("Done.")


if __name__ == "__main__":
    main()
