import json
import os
import urllib.request
import urllib.parse

APP_TOKEN = os.environ.get("LARK_BASE_TOKEN", "").strip()
TABLE_ID = os.environ.get("LARK_TABLE_ID", "").strip()
OUTPUT_FILE = os.path.join("api", "videos.json")

def get_tenant_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read())
            if res.get("code") == 0:
                return res.get("tenant_access_token")
            else:
                print(f"Failed to get tenant token: {res}")
    except Exception as e:
        print(f"Auth request exception: {e}")
    return None

def get_bitable_records(token):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
    all_records = []
    has_more = True
    page_token = ""

    while has_more:
        try:
            params = "page_size=100"
            if page_token:
                params += f"&page_token={page_token}"
            page_url = f"{url}?{params}"
            print(f"  Requesting: {page_url}")
            req = urllib.request.Request(page_url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read())
                if res.get("code") == 0:
                    data = res.get("data", {})
                    all_records.extend(data.get("items", []))
                    has_more = data.get("has_more", False)
                    page_token = data.get("page_token", "")
                else:
                    print(f"Failed to fetch records: code={res.get('code')} msg={res.get('msg')}")
                    break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"Bitable API exception: HTTP {e.code} - {body}")
            break
        except Exception as e:
            print(f"Bitable API exception: {e}")
            break
    return all_records

def fetch_media_urls(token, batch):
    url = "https://open.feishu.cn/open-apis/drive/v1/medias/batch_get_tmp_download_url"
    extra_json = json.dumps({"bitablePerm": {"tableId": TABLE_ID}})
    params = f"extra={urllib.parse.quote(extra_json)}"
    for t in batch:
        params += f"&file_tokens={t}"

    full_url = f"{url}?{params}"
    req = urllib.request.Request(full_url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Failed to fetch URLs: {e}")
    return None

def extract_text(field_value):
    """Extract text from various Feishu field formats."""
    if field_value is None:
        return ""
    if isinstance(field_value, str):
        return field_value.strip()
    if isinstance(field_value, list):
        parts = []
        for item in field_value:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    if isinstance(field_value, dict):
        return field_value.get("text", "")
    return str(field_value)

def extract_tags(field_value):
    """Extract tag list from select/multi-select fields."""
    if field_value is None:
        return []
    if isinstance(field_value, list):
        return [t.strip() for t in field_value if isinstance(t, str) and t.strip()]
    if isinstance(field_value, str) and field_value.strip():
        return [field_value.strip()]
    return []

def main():
    app_id = os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("LARK_APP_SECRET")

    if not app_id or not app_secret or not APP_TOKEN or not TABLE_ID:
        print("Missing env vars: LARK_APP_ID, LARK_APP_SECRET, LARK_BASE_TOKEN, LARK_TABLE_ID")
        return

    print("Authenticating...")
    tenant_token = get_tenant_token(app_id, app_secret)
    if not tenant_token:
        print("Could not obtain tenant access token. Aborting.")
        return

    print("Fetching records from Bitable...")
    records = get_bitable_records(tenant_token)
    print(f"Found {len(records)} records.")

    # Collect file tokens from attachment field
    ATTACHMENT_FIELD = os.environ.get("LARK_ATTACHMENT_FIELD", "附件")
    tokens_to_fetch = []
    for r in records:
        fields = r.get("fields", {})
        # Try multiple possible attachment field names
        attachments = fields.get(ATTACHMENT_FIELD) or fields.get("附件/视频") or fields.get("样片") or fields.get("视频") or []
        if attachments and isinstance(attachments, list) and len(attachments) > 0:
            ft = attachments[0].get("file_token")
            if ft:
                tokens_to_fetch.append(ft)

    print(f"Found {len(tokens_to_fetch)} video tokens to resolve.")

    # Batch resolve URLs (max 5 per request)
    mapped_urls = {}
    for i in range(0, len(tokens_to_fetch), 5):
        batch = tokens_to_fetch[i:i+5]
        print(f"Fetching batch {i//5 + 1}...")
        response_data = fetch_media_urls(tenant_token, batch)
        if response_data and response_data.get("code") == 0:
            tmp_urls = response_data.get("data", {}).get("tmp_download_urls", [])
            for item in tmp_urls:
                mapped_urls[item["file_token"]] = item["tmp_download_url"]

    # Build output
    final_output = []
    for r in records:
        fields = r.get("fields", {})
        attachments = fields.get(ATTACHMENT_FIELD) or fields.get("附件/视频") or fields.get("样片") or fields.get("视频") or []
        if not attachments or not isinstance(attachments, list) or len(attachments) == 0:
            continue

        ft = attachments[0].get("file_token")
        if ft not in mapped_urls:
            continue

        title = extract_text(fields.get("文本") or fields.get("标题") or fields.get("内容") or "")
        if not title:
            continue

        categories = extract_tags(fields.get("分类") or fields.get("类型") or [])

        final_output.append({
            "title": title,
            "category": categories,
            "URL": mapped_urls[ft]
        })

    os.makedirs("api", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print(f"Generated api/videos.json with {len(final_output)} items.")

if __name__ == "__main__":
    main()
