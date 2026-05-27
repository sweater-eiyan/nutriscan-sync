import os
import json
import requests


WEBHOOK_SITE_URL = os.environ.get("WEBHOOK_SITE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")


def fetch_webhook_requests():
    if not WEBHOOK_SITE_URL:
        raise RuntimeError("WEBHOOK_SITE_URL is not set")

    # Webhook.site の「Get Requests」エンドポイントを叩く
    # ここでは URL 全体を Secret に入れてもらっている前提
    url = WEBHOOK_SITE_URL

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    params = {
        "sorting": "newest",
        "limit": 100,
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # Webhook.site の API は通常、リストを返すか、{"data": [...]} の形
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]

    # それ以外の形ならそのまま返す（後段で防御的に扱う）
    return data


def parse_body_metrics(requests_json):
    records = []

    for item in requests_json:
        # ここが今回の修正ポイント:
        # Webhook.site から返ってきている要素が「文字列」であるケースを前提にする
        if not isinstance(item, str):
            # dict や他の型が紛れていても、とりあえず無視する
            continue

        body = item
        if not body:
            continue

        # 1段目の JSON: Shortcut が送っている外側の JSON 文字列
        try:
            outer = json.loads(body)
        except Exception:
            # JSON でなければスキップ
            continue

        payload_str = outer.get("payload")
        if not payload_str or not isinstance(payload_str, str):
            # payload がなければスキップ
            continue

        # 2段目の JSON: payload の中身（これも JSON 文字列）
        try:
            payload = json.loads(payload_str)
        except Exception:
            continue

        metric_type = payload.get("metric_type")
        timestamp = payload.get("timestamp")
        value = payload.get("value")
        source = payload.get("source", "shortcut")

        if not metric_type or timestamp is None or value is None:
            # 必須フィールドが足りないものはスキップ
            continue

        try:
            value_num = float(value)
        except Exception:
            # 数値に変換できなければスキップ
            continue

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
    requests_json = fetch_webhook_requests()
    print(
        f"Fetched {len(requests_json) if hasattr(requests_json, '__len__') else 'unknown number of'} requests from Webhook.site."
    )

    print("Parsing body_metrics records...")
    records = parse_body_metrics(requests_json)
    print(f"Parsed {len(records)} body_metrics records.")

    print("Upserting into Supabase...")
    upsert_to_supabase(records)
    print("Done.")


if __name__ == "__main__":
    main()
