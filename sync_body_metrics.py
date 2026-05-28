import os
import json
import requests


WEBHOOK_SITE_URL = os.environ.get("WEBHOOK_SITE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")


def fetch_webhook_requests():
    if not WEBHOOK_SITE_URL:
        raise RuntimeError("WEBHOOK_SITE_URL is not set")

    url = WEBHOOK_SITE_URL

    headers = {
        "Accept": "application/json",
    }

    params = {
        "sorting": "newest",
        "per_page": 100,
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # Webhook.site の Get Requests API は {"data": [...], "total": N} を返す
    # data["data"] が実際のリクエスト配列
    if isinstance(data, dict) and "data" in data:
        return data["data"]

    # 万が一リストで返ってきた場合もカバー
    if isinstance(data, list):
        return data

    return []


def parse_body_metrics(requests_json):
    records = []

    for item in requests_json:
        if not isinstance(item, dict):
            continue

        # Webhook.site のドキュメント上、リクエストボディは "content" フィールドに入っている
        content = item.get("content", "")
        if not content:
            continue

        try:
            payload = json.loads(content)
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
    print(f"Fetched {len(requests_json)} requests from Webhook.site.")

    print("Parsing body_metrics records...")
    records = parse_body_metrics(requests_json)
    print(f"Parsed {len(records)} body_metrics records.")

    print("Upserting into Supabase...")
    upsert_to_supabase(records)
    print("Done.")


if __name__ == "__main__":
    main()
