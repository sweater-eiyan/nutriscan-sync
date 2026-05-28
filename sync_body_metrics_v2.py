import os
import json
import requests


WEBHOOK_SITE_URL = os.environ.get("WEBHOOK_SITE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")


def fetch_webhook_requests():
    """
    Webhook.site の Requests API から最新リクエスト一覧を取得して、
    各リクエストを表す dict のリストとして返す。
    """
    if not WEBHOOK_SITE_URL:
        raise RuntimeError("WEBHOOK_SITE_URL is not set")

    # ここには「/token/<token>/requests」まで含んだ URL を想定
    url = WEBHOOK_SITE_URL

    headers = {
        "Accept": "application/json",
    }

    # per_page / sorting は公式サンプルに合わせて指定[web:130]
    params = {
        "per_page": 100,
        "sorting": "newest",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # パターン1: {"data": [...], "total": N}
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]

    # パターン2: いきなり配列が返るケース
    if isinstance(data, list):
        return data

    # 想定外の形は空にしておく（後段で len=0 として扱う）
    return []


def parse_body_metrics(request_items):
    """
    Webhook.site のリクエスト一覧から、body_metrics テーブル用のレコードを組み立てる。
    """
    records = []

    for item in request_items:
        # 各要素は dict 前提
        if not isinstance(item, dict):
            continue

        # Webhook.site では request body は content フィールドに入る[web:130]
        content = item.get("content")
        if not content:
            continue

        # content は JSON 文字列（Shortcut から送った payload）
        try:
            payload = json.loads(content)
        except Exception:
            # JSON でないものはスキップ
            continue

        metric_type = payload.get("metric_type")
        timestamp = payload.get("timestamp")
        value = payload.get("value")
        source = payload.get("source", "shortcut")

        # 必須フィールドが欠けているものは捨てる
        if not metric_type or timestamp is None or value is None:
            continue

        # value は文字列 or 数値どちらでも float にして扱う
        try:
            value_num = float(value)
        except Exception:
            continue

        # 小数点2桁に丸め
        rounded_value = round(value_num, 2)

        records.append(
            {
                "metric_type": metric_type,
                "value": rounded_value,
                "recorded_at": timestamp,
                "source": source,
            }
        )

    return records


def upsert_to_supabase(records):
    """
    Supabase の body_metrics テーブルにレコードを挿入する。
    """
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
        "Prefer": "return=representation",
    }

    resp = requests.post(url, headers=headers, data=json.dumps(records), timeout=30)

    if not resp.ok:
        print("Supabase error status:", resp.status_code)
        print("Supabase error body:", resp.text)
        resp.raise_for_status()

    print(f"Inserted {len(records)} records into Supabase.")


def main():
    print("Fetching webhook requests...")
    items = fetch_webhook_requests()
    print(f"Fetched {len(items)} requests from Webhook.site.")

    print("Parsing body_metrics records...")
    records = parse_body_metrics(items)
    print(f"Parsed {len(records)} body_metrics records.")

    print("Upserting into Supabase...")
    upsert_to_supabase(records)
    print("Done.")


if __name__ == "__main__":
    main()
