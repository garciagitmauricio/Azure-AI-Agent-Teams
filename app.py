"""
Simple Azure AI Foundry Agent App
No Teams SDK, no complexity - just a clean agent interface
"""

from azure.identity import DefaultAzureCredential
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Azure AI Configuration - using the provided endpoint
# Example format:
#   https://<your-ai-services-id>.services.ai.azure.com/api/projects/<your-project-name>
ENDPOINT = os.getenv(
    "AZURE_AI_PROJECT_ENDPOINT",
    "https://epwater-multi-agent-test-resourc.services.ai.azure.com/api/projects/multi-agent-test",
)
AGENT_ID = os.getenv("AZURE_AI_AGENT_ID", "your-agent-id")  # Set this in .env
API_VERSION = "v1"

# Azure Authentication
credential = DefaultAzureCredential()
current_thread_id = None


def get_auth_headers():
    """Get authorization headers for Azure AI API"""
    try:
        print("🔐 Attempting Azure authentication...")
        token = credential.get_token("https://ai.azure.com/.default").token
        print("✅ Azure token obtained successfully")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    except Exception as e:
        print(f"❌ Azure authentication error: {e} ({type(e).__name__})")

        # Fallback to API key if available
        api_key = os.getenv("AZURE_AI_API_KEY")
        if api_key:
            print("🔑 Using API key fallback")
            return {"api-key": api_key, "Content-Type": "application/json"}
        else:
            print(
                "💥 No API key found in environment. "
                "Please set AZURE_AI_API_KEY or configure Azure authentication."
            )
            raise


def _log_http_error(prefix: str, response: requests.Response):
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict) and "error" in payload:
        err = payload.get("error") or {}
        print(
            f"{prefix} Status={response.status_code} "
            f"Code={err.get('code')} Message={err.get('message')}"
        )
    else:
        print(f"{prefix} Status={response.status_code} Raw={response.text}")


def create_thread():
    """Create a new conversation thread"""
    try:
        url = f"{ENDPOINT}/threads?api-version={API_VERSION}"
        print(f"🔗 Creating thread at: {url}")

        headers = get_auth_headers()
        print("🔑 Headers prepared successfully")

        response = requests.post(url, headers=headers, json={}, timeout=30)
        print(f"📡 Response status: {response.status_code}")

        if response.status_code in (200, 201):
            thread_data = response.json()
            thread_id = thread_data["id"]
            print(f"✅ Thread created successfully: {thread_id}")
            return thread_id
        else:
            _log_http_error("❌ Error creating thread.", response)
            return None
    except Exception as e:
        print(f"💥 Exception in create_thread: {e} ({type(e).__name__})")
        import traceback

        traceback.print_exc()
        return None


def send_message(thread_id, message: str):
    """Send a message to the agent and return the latest assistant response (text)"""
    headers = get_auth_headers()

    # 1) Add message to the thread
    msg_url = f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
    message_data = {"role": "user", "content": message}
    msg_resp = requests.post(msg_url, headers=headers, json=message_data, timeout=30)
    if msg_resp.status_code not in (200, 201):
        _log_http_error("❌ Error adding message.", msg_resp)
        return None

    # 2) Create a run for the thread
    run_url = f"{ENDPOINT}/threads/{thread_id}/runs?api-version={API_VERSION}"
    run_data = {"assistant_id": AGENT_ID}  # Azure Agent Service expects assistant_id
    run_resp = requests.post(run_url, headers=headers, json=run_data, timeout=30)
    if run_resp.status_code not in (200, 201):
        _log_http_error("❌ Error creating run.", run_resp)
        return None

    run_id = run_resp.json()["id"]

    # 3) Poll for completion
    import time

    status_url = (
        f"{ENDPOINT}/threads/{thread_id}/runs/{run_id}?api-version={API_VERSION}"
    )
    max_attempts = 45
    for _ in range(max_attempts):
        status_resp = requests.get(status_url, headers=headers, timeout=30)
        if status_resp.status_code == 200:
            status = status_resp.json().get("status")
            print(f"⏳ Run status: {status}")
            if status == "completed":
                # 4) Fetch messages; return the newest assistant text block
                messages_url = (
                    f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
                )
                messages_resp = requests.get(messages_url, headers=headers, timeout=30)
                if messages_resp.status_code == 200:
                    data = messages_resp.json().get("data", [])
                    # data is typically newest-first; guard just in case:
                    # Find the most recent assistant message with a text value
                    def _created_at(msg):
                        return msg.get("created_at", 0)

                    for msg in sorted(data, key=_created_at, reverse=True):
                        if msg.get("role") == "assistant":
                            # Each message has a list of content blocks
                            contents = msg.get("content", [])
                            for block in contents:
                                # Expecting {"type":"output_text" or "text","text":{"value": "..."}}
                                txt = None
                                if isinstance(block, dict):
                                    # Most common: block["text"]["value"]
                                    txt = (
                                        block.get("text", {}) or {}
                                    ).get("value") or block.get("value")
                                if txt:
                                    return txt
                    return "I completed the run, but couldn't find a text reply."
                else:
                    _log_http_error("❌ Error fetching messages.", messages_resp)
                    return None
            elif status in ("failed", "cancelled", "expired"):
                print(f"❌ Run ended with status: {status}")
                # Try to surface last_error if present
                body = status_resp.json()
                last_error = (body or {}).get("last_error")
                if last_error:
                    print(
                        f"   ↳ code={last_error.get('code')} message={last_error.get('message')}"
                    )
                return None
        else:
            _log_http_error("❌ Error fetching run status.", status_resp)
            return None

        time.sleep(1)

    return "Sorry, I couldn't process your request at the moment."


@app.route("/")
def home():
    """Serve the main HR Policy Assistant interface optimized for Teams"""
    return send_from_directory(".", "index.html")


@app.route("/privacy")
def privacy():
    """Privacy policy for Teams compliance"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Privacy Policy - HR Policy Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #464775; }
        </style>
    </head>
    <body>
        <h1>Privacy Policy - HR Policy Assistant</h1>
        <p><strong>Data Processing:</strong> HR queries are processed securely by Azure AI Foundry services.</p>
        <p><strong>Storage:</strong> No personal information is stored permanently on our servers.</p>
        <p><strong>Privacy:</strong> All conversations are processed through Microsoft Azure's secure infrastructure.</p>
        <p><strong>Compliance:</strong> This app follows Microsoft Teams app privacy guidelines.</p>
    </body>
    </html>
    """


@app.route("/terms")
def terms():
    """Terms of use for Teams compliance"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Terms of Use - HR Policy Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #464775; }
        </style>
    </head>
    <body>
        <h1>Terms of Use - HR Policy Assistant</h1>
        <p><strong>Usage:</strong> This HR Policy Assistant is for informational purposes only.</p>
        <p><strong>Accuracy:</strong> While powered by advanced AI, responses should be verified with HR professionals.</p>
        <p><strong>Support:</strong> For official HR matters, contact your HR department directly.</p>
        <p><strong>Technology:</strong> Built with Azure AI Foundry and Microsoft Teams integration.</p>
    </body>
    </html>
    """


@app.route("/chat", methods=["POST"])
def chat():
    """Handle chat messages"""
    global current_thread_id

    try:
        data = request.get_json()
        message = data.get("message", "")

        if not message:
            return jsonify({"error": "No message provided"}), 400

        # Create thread if it doesn't exist
        if not current_thread_id:
            current_thread_id = create_thread()
            if not current_thread_id:
                return (
                    jsonify({"error": "Failed to create conversation thread"}),
                    500,
                )

        # Send message and get response
        response = send_message(current_thread_id, message)

        if response:
            return jsonify({"response": response, "thread_id": current_thread_id})
        else:
            return jsonify({"error": "Failed to get response from agent"}), 500

    except Exception as e:
        print(f"Chat error: {e} ({type(e).__name__})")
        return jsonify({"error": str(e)}), 500


@app.route("/new-conversation", methods=["POST"])
def new_conversation():
    """Start a new conversation"""
    global current_thread_id
    current_thread_id = None
    return jsonify({"message": "New conversation started"})


@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify(
        {"status": "healthy", "endpoint": ENDPOINT, "api_version": API_VERSION}
    )


if __name__ == "__main__":
    print("🚀 Starting Simple AI Agent App")
    print(f"📡 Endpoint: {ENDPOINT}")
    print(f"🔗 Agent (assistant) ID: {AGENT_ID}")
    print(f"📄 API Version: {API_VERSION}")

    # Get port from environment variable (Azure App Service uses this)
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") == "development"

    print(f"🌐 Server will run on port: {port}")
    print("=" * 50)

    app.run(debug=debug_mode, host="0.0.0.0", port=port)

