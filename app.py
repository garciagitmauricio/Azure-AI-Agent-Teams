"""
Simple Azure AI Foundry Agent App
No Teams SDK, no complexity — just a clean agent interface
"""

from azure.identity import DefaultAzureCredential
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# -------------------------------
# Azure AI Foundry (Agents) config
# -------------------------------
# Example project endpoint:
#   https://<ai-services-id>.services.ai.azure.com/api/projects/<project-name>
# Sanitize values to avoid hidden whitespace/newlines
ENDPOINT = (os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") or "").strip().rstrip("/")
API_KEY  = (os.getenv("AZURE_AI_API_KEY", "") or "").strip()
AGENT_ID = (os.getenv("AZURE_AI_AGENT_ID", "") or "").strip() or "your-agent-id"
API_VERSION = "v1"

# Auth objects
credential = DefaultAzureCredential()

# Reuse one HTTP session (lower overhead)
session = requests.Session()

# Keep a single thread id per process for simplicity
current_thread_id = None


# ---------- helpers ----------
def _mask(s: str, show_last: int = 4) -> str:
    if not s:
        return ""
    return "*" * max(0, len(s) - show_last) + s[-show_last:]


def _http_error_details(resp: requests.Response) -> str:
    try:
        j = resp.json()
        if isinstance(j, dict) and "error" in j:
            err = j["error"] or {}
            return f"Status={resp.status_code} Code={err.get('code')} Message={err.get('message')}"
        return f"Status={resp.status_code} Raw={resp.text}"
    except Exception:
        return f"Status={resp.status_code} Raw={resp.text}"


def get_auth_headers():
    """
    Prefer the Project API key for Agents data-plane calls.
    Falls back to AAD token only if AZURE_AI_API_KEY is not set.
    """
    if API_KEY:
        print("🔑 Using API key auth")
        return {"api-key": API_KEY, "Content-Type": "application/json"}

    print("🔐 AZURE_AI_API_KEY not set; using Azure AD token")
    token = credential.get_token("https://ai.azure.com/.default").token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- core calls ----------
def create_thread():
    """Create a new conversation thread. Returns thread_id or {'_error': ...}."""
    try:
        url = f"{ENDPOINT}/threads?api-version={API_VERSION}"
        print(f"🔗 Creating thread: {url}")
        headers = get_auth_headers()
        resp = session.post(url, headers=headers, json={}, timeout=30)
        print(f"📡 thread.create status={resp.status_code}")

        if resp.status_code in (200, 201):
            tid = resp.json().get("id")
            print(f"✅ Thread created: {tid}")
            return tid

        detail = _http_error_details(resp)
        print(f"❌ thread.create failed: {detail}")
        return {"_error": detail}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"_error": f"Exception in create_thread: {e} ({type(e).__name__})"}


def send_message(thread_id: str, message: str):
    """
    Send a user message to the thread, run the agent, and return the latest assistant text.
    Returns None on failure (caller returns an error to client).
    """
    headers = get_auth_headers()

    # 1) Add message to the thread
    msg_url = f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
    msg_body = {"role": "user", "content": message}
    msg_resp = session.post(msg_url, headers=headers, json=msg_body, timeout=30)
    if msg_resp.status_code not in (200, 201):
        print(f"❌ messages.create failed: {_http_error_details(msg_resp)}")
        return None

    # 2) Create a run
    run_url = f"{ENDPOINT}/threads/{thread_id}/runs?api-version={API_VERSION}"
    run_body = {"assistant_id": AGENT_ID}
    run_resp = session.post(run_url, headers=headers, json=run_body, timeout=30)
    if run_resp.status_code not in (200, 201):
        print(f"❌ runs.create failed: {_http_error_details(run_resp)}")
        return None

    run_id = run_resp.json().get("id")
    if not run_id:
        print("❌ runs.create returned no run id")
        return None

    # 3) Poll for completion (≈45s max)
    status_url = f"{ENDPOINT}/threads/{thread_id}/runs/{run_id}?api-version={API_VERSION}"
    for _ in range(45):
        status_resp = session.get(status_url, headers=headers, timeout=30)
        if status_resp.status_code != 200:
            print(f"❌ runs.get failed: {_http_error_details(status_resp)}")
            return None

        body = status_resp.json() or {}
        status = body.get("status")
        print(f"⏳ Run status: {status}")

        if status == "completed":
            # 4) Fetch the latest assistant message text
            messages_url = f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
            messages_resp = session.get(messages_url, headers=headers, timeout=30)
            if messages_resp.status_code != 200:
                print(f"❌ messages.list failed: {_http_error_details(messages_resp)}")
                return None

            data = (messages_resp.json() or {}).get("data", [])

            def _created_at(msg):
                return msg.get("created_at", 0)

            for msg in sorted(data, key=_created_at, reverse=True):
                if msg.get("role") == "assistant":
                    for block in msg.get("content", []) or []:
                        # Most common: block["text"]["value"]
                        txt = None
                        if isinstance(block, dict):
                            if "text" in block and isinstance(block["text"], dict):
                                txt = block["text"].get("value")
                            elif "value" in block:
                                txt = block.get("value")
                        if txt:
                            return txt
            return "Run completed, but no assistant text was found."

        if status in ("failed", "cancelled", "expired"):
            last_error = (body or {}).get("last_error") or {}
            print(
                f"❌ Run ended: status={status} code={last_error.get('code')} message={last_error.get('message')}"
            )
            return None

        time.sleep(1)

    return "Sorry, I couldn't process your request at the moment."


# ---------- routes ----------
@app.after_request
def add_no_cache_headers(resp):
    # Helps during debugging and avoids stale HTML in some hosts/CDNs
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/privacy")
def privacy():
    return """
    <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - HR Policy Assistant</title>
    <style>body{font-family:'Segoe UI',sans-serif;max-width:800px;margin:50px auto;padding:20px}h1{color:#464775}</style>
    </head><body>
    <h1>Privacy Policy - HR Policy Assistant</h1>
    <p><strong>Data Processing:</strong> HR queries are processed securely by Azure AI Foundry services.</p>
    <p><strong>Storage:</strong> No personal information is stored permanently on our servers.</p>
    <p><strong>Privacy:</strong> All conversations are processed through Microsoft Azure's secure infrastructure.</p>
    <p><strong>Compliance:</strong> This app follows Microsoft Teams app privacy guidelines.</p>
    </body></html>
    """


@app.route("/terms")
def terms():
    return """
    <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Use - HR Policy Assistant</title>
    <style>body{font-family:'Segoe UI',sans-serif;max-width:800px;margin:50px auto;padding:20px}h1{color:#464775}</style>
    </head><body>
    <h1>Terms of Use - HR Policy Assistant</h1>
    <p><strong>Usage:</strong> This HR Policy Assistant is for informational purposes only.</p>
    <p><strong>Accuracy:</strong> While powered by advanced AI, responses should be verified with HR professionals.</p>
    <p><strong>Support:</strong> For official HR matters, contact your HR department directly.</p>
    <p><strong>Technology:</strong> Built with Azure AI Foundry and Microsoft Teams integration.</p>
    </body></html>
    """


@app.route("/chat", methods=["POST"])
def chat():
    """Handle chat messages"""
    global current_thread_id
    try:
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "No message provided"}), 400

        # Ensure a thread exists
        if not current_thread_id:
            result = create_thread()
            if isinstance(result, dict) and result.get("_error"):
                return jsonify({"error": f"Create thread failed: {result['_error']}"}), 502
            current_thread_id = result
            if not current_thread_id:
                return jsonify({"error": "Create thread failed: unknown"}), 502

        # Send message and return response
        reply = send_message(current_thread_id, message)
        if reply:
            return jsonify({"response": reply, "thread_id": current_thread_id})
        return jsonify({"error": "Failed to get response from agent"}), 502

    except Exception as e:
        return jsonify({"error": f"{e} ({type(e).__name__})"}), 500


@app.route("/new-conversation", methods=["POST"])
def new_conversation():
    """Start a new conversation"""
    global current_thread_id
    current_thread_id = None
    return jsonify({"message": "New conversation started"})


@app.route("/health")
def health():
    """Health check endpoint (safe, redacted)"""
    return jsonify(
        {
            "status": "healthy",
            "endpoint": ENDPOINT,
            "api_version": API_VERSION,
            "agent_id_set": bool(AGENT_ID and AGENT_ID != "your-agent-id"),
            "api_key_present": bool(API_KEY),
            "api_key_len": len(API_KEY) if API_KEY else 0,
            "api_key_masked": _mask(API_KEY),
        }
    )


# ---------- Diagnostics (safe to expose) ----------
@app.route("/diag/config")
def diag_config():
    """Show redacted config values to verify environment is correct."""
    import urllib.parse
    try:
        host = urllib.parse.urlparse(ENDPOINT).hostname
    except Exception:
        host = ""
    return jsonify(
        {
            "endpoint": ENDPOINT,
            "host": host,
            "api_key_present": bool(API_KEY),
            "api_key_len": len(API_KEY) if API_KEY else 0,
            "api_key_masked": _mask(API_KEY),
        }
    )


@app.route("/diag/dns")
def diag_dns():
    """Resolve the endpoint host to verify DNS from this environment."""
    import socket, urllib.parse
    host = urllib.parse.urlparse(ENDPOINT).hostname if ENDPOINT else ""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        addrs = sorted({ai[4][0] for ai in infos})
        return jsonify({"ok": True, "host": host, "addresses": addrs})
    except Exception as e:
        return jsonify({"ok": False, "host": host, "error": f"{e} ({type(e).__name__})"}), 502


@app.route("/diag/selftest", methods=["GET", "POST"])
def diag_selftest():
    """
    Make a direct POST /threads call and return raw status/body (key redacted).
    Accepts GET for convenience (will still perform a POST to the service).
    """
    try:
        headers = get_auth_headers()
        safe_headers = {k: ("<redacted>" if k.lower() == "api-key" else v) for k, v in headers.items()}
        url = f"{ENDPOINT}/threads?api-version={API_VERSION}"
        resp = session.post(url, headers=headers, json={}, timeout=20)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return jsonify(
            {
                "endpoint": ENDPOINT,
                "headers_used": safe_headers,
                "status": resp.status_code,
                "response": body,
            }
        ), (200 if resp.status_code in (200, 201) else 502)
    except Exception as e:
        return jsonify({"error": f"{e} ({type(e).__name__})"}), 500


if __name__ == "__main__":
    # Safe startup logs (masked)
    print("🚀 Starting Simple AI Agent App")
    print("🔧 Endpoint:", ENDPOINT)
    print("🔧 API key present:", bool(API_KEY), " len:", len(API_KEY) if API_KEY else 0, " masked:", _mask(API_KEY))
    print(f"🔗 Agent (assistant) ID set: {bool(AGENT_ID and AGENT_ID != 'your-agent-id')}")
    print(f"📄 API Version: {API_VERSION}")

    # App Service sets PORT; keep debug off unless explicitly in development
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") == "development"
    print(f"🌐 Server will run on port: {port}")
    print("=" * 50)

    app.run(debug=debug_mode, host="0.0.0.0", port=port)

