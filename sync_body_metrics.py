def parse_body_metrics(requests_json):
    records = []

    for item in requests_json:
        # Webhook.site の各リクエストは dict 前提
        if not isinstance(item, dict):
            continue

        # Webhook.site のレスポンス仕様に合わせて body/content を取得
        # 参考: docs.webhook.site の Requests API [web:107]
        body = item.get("content") or item.get("body") or ""
        if not body:
            continue

        # body がすでに dict で来ている可能性と、文字列 JSON の可能性の両方を見る
        if isinstance(body, dict):
            outer = body
        else:
            try:
                outer = json.loads(body)
            except Exception:
                continue

        payload_str = outer.get("payload")
        if not payload_str:
            continue

        # payload が dict か文字列か両方を見る
        if isinstance(payload_str, dict):
            payload = payload_str
        else:
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
