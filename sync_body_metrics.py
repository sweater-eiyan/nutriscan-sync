def parse_body_metrics(requests_json):
    records = []

    for item in requests_json:
        # Webhook.site の各リクエストは dict 前提
        if not isinstance(item, dict):
            continue

        # docs と実データを見る限り、body にそのまま JSON 文字列が入っている [web:107]
        body = item.get("body") or item.get("content") or ""
        if not body:
            continue

        # body は JSON 文字列（例: {"metric_type":"weight","value":63.4,"timestamp":"..."}）
        try:
            payload = json.loads(body)
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
