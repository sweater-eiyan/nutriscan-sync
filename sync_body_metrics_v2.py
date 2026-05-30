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
    headers = {"Accept": "application/json"}
    params = {"per_page": 100, "sorting": "newest"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def parse_payload(item):
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if not content:
        return None
    try:
        outer = json.loads(content)
    except Exception:
        return None
    if not isinstance(outer, dict):
        return None
    payload_raw = outer.get("payload")
    if payload_raw is None:
        return None
    if isinstance(payload_raw, dict):
        return payload_raw
    try:
        payload = json.loads(payload_raw)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return None


def group_by_date(request_items):
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
        try:
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
    records = []
    for date_str, metrics in day_data.items():
        weight_kg = metrics.get("weight_kg")
        body_fat_pct = metrics.get("body_fat_pct")
        source = metrics.get("source", "shortcut")
        if weight_kg is None and body_fat_pct is None:
            continue
        lbm_kg = None
        if weight_kg is not None and body_fat_pct is not None:
            lbm_kg = round(weight_kg * (1 - body_fat_pct / 100), 2)
        # PGRST102 対応: 全レコードで同じキーセットを保持する (None を明示的に入れる)
        record = {
            "date": date_str,
            "source": source,
            "weight_kg": weight_kg,
            "body_fat_pct": body_fat_pct,
            "lbm_kg": lbm_kg,
        }
        records.append(record)
    return records


def filter_latest_date_only(records):
    """
    records の中で一番新しい date のものだけに絞る。
    通常運用では「直近1日分だけ同期」するためのフィルタ。
    """
    if not records:
        return records
    latest_date = max(r["date"] for r in records)
    return [r for r in records if r["date"] == latest_date]


def upsert_to_supabase(records):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is not set")
    if not records:
        print("No records to upsert into Supabase.")
        return

    # date を conflict target にして UPSERT（同一日付は上書き）
    url = f"{SUPABASE_URL}/rest/v1/body_metrics?on_conflict=date"
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

    # ★ 直近1日分だけに絞る
    records = filter_latest_date_only(records)
    print(f"Using {len(records)} record(s) for upsert (latest date only):")
    for r in records:
        print(" -", r)

    print("Upserting into Supabase...")
    upsert_to_supabase(records)
    print("Done.")


if __name__ == "__main__":
    main()
