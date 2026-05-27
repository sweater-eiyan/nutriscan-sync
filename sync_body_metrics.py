import os
import json
import datetime
import urllib.parse

import requests


def fetch_webhook_requests():
    """
    Webhook.site から最近のリクエスト一覧を取得して返す。
    """
    webhook_url = os.environ["WEBHOOK_SITE_URL"].rstrip("/")
    # 例: https://webhook.site/29a5237e-2734-46f1-bbc6-560353841d19

    parsed = urllib.parse.urlparse(webhook_url)
    request_list_url = f"{parsed.scheme}://{parsed.netloc}/token/{parsed.path.strip('/')}/requests"

    params = {
        "limit": 100,
        "sort": "desc"
    }

    resp = requests.get(request_list_url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data


def parse_body_metrics(requests_json):
    """
    Webhook.site のリクエスト配列から body_metrics 用のレコードを抽出。
    """
    records = []

    for item in requests_json:
        body = item.get("content") or item.get("body") or ""
        if not body:
            continue

        try:
            outer = json.loads(body)
        except Exception:
            continue

        payload_str = outer.get("payload")
        if not payload_str or not isinstance(payload_str, str):
            continue

        try:
            payload = json.loads(payload_str)
        except Exception:
            continue

        metric_type = payload.get("metric_type")
        timestamp = payload.get("timestamp")
        value = payload.get("value")
        source = payload.get("source", "shortcut")

        if not metric_type or timestamp is None or value is None:
            continue

        try:
            value_num = float(value)
        except Exception:
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


def insert_into_supabase(records):
    """
    Supabase の body_metrics テーブルにまとめて INSERT する。
    """
    if not records:
        print("No records to insert.")
        return

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["SUPABASE_ANON_KEY"]

    endpoint = f"{supabase_url}/rest/v1/body_metrics"

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    resp = requests.post(endpoint, headers=headers, json=records, timeout=15)
    if not resp.ok:
        print("Supabase insert failed:", resp.status_code, resp.text)
        resp.raise_for_status()
    else:
        print(f"Inserted {len(records)} records into Supabase.")


def main():
    print("Fetching webhook requests...")
    requests_json = fetch_webhook_requests()
    print(f"Fetched {len(requests_json)} requests from Webhook.site.")

    print("Parsing body_metrics records...")
    records = parse_body_metrics(requests_json)
    print(f"Parsed {len(records)} body_metrics records.")

    if records:
        insert_into_supabase(records)
    else:
        print("No valid body_metrics records found.")


if __name__ == "__main__":
    main()
