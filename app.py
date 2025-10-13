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

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Azure AI Configuration - using the provided endpoint
ENDPOINT = "https://epwater-multi-agent-test-resourc.services.ai.azure.com/api/projects/multi-agent-test"
AGENT_ID = os.getenv('AZURE_AI_AGENT_ID', 'your-agent-id')  # Set this in .env
API_VERSION = "2025-05-01"

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
            "Content-Type": "application/json"
        }
    except Exception as e:
        print(f"❌ Azure authentication error: {e}")
        print(f"❌ Exception type: {type(e).__name__}")
        
        # Fallback to API key if available
        api_key = os.getenv('AZURE_AI_API_KEY')
        if api_key:
            print("🔑 Using API key fallback")
            return {
                "api-key": api_key,
                "Content-Type": "application/json"
            }
        else:
            print("💥 No API key found in environment. Please set AZURE_AI_API_KEY or configure Azure authentication.")
            raise

def create_thread():
    """Create a new conversation thread"""
    try:
        url = f"{ENDPOINT}/threads?api-version={API_VERSION}"
        print(f"🔗 Creating thread at: {url}")
        
        headers = get_auth_headers()
        print(f"🔑 Headers prepared successfully")
        
        response = requests.post(url, headers=headers, json={})
        print(f"📡 Response status: {response.status_code}")
        print(f"📄 Response text: {response.text}")
        
        if response.status_code in [200, 201]:
            thread_data = response.json()
            thread_id = thread_data['id']
            print(f"✅ Thread created successfully: {thread_id}")
            return thread_id
        else:
            print(f"❌ Error creating thread. Status: {response.status_code}")
            print(f"❌ Response: {response.text}")
            return None
    except Exception as e:
        print(f"💥 Exception in create_thread: {str(e)}")
        print(f"💥 Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

def send_message(thread_id, message):
    """Send a message to the agent"""
    # Add message to thread
    url = f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
    headers = get_auth_headers()
    
    message_data = {
        "role": "user",
        "content": message
    }
    
    response = requests.post(url, headers=headers, json=message_data)
    if response.status_code not in [200, 201]:
        print(f"Error adding message: {response.text}")
        return None
    
    # Create run
    run_url = f"{ENDPOINT}/threads/{thread_id}/runs?api-version={API_VERSION}"
    run_data = {
        "assistant_id": AGENT_ID
    }
    
    run_response = requests.post(run_url, headers=headers, json=run_data)
    if run_response.status_code not in [200, 201]:
        print(f"Error creating run: {run_response.text}")
        return None
    
    run_id = run_response.json()['id']
    
    # Poll for completion
    import time
    max_attempts = 30
    for _ in range(max_attempts):
        status_url = f"{ENDPOINT}/threads/{thread_id}/runs/{run_id}?api-version={API_VERSION}"
        status_response = requests.get(status_url, headers=headers)
        
        if status_response.status_code == 200:
            status = status_response.json()['status']
            if status == 'completed':
                # Get messages
                messages_url = f"{ENDPOINT}/threads/{thread_id}/messages?api-version={API_VERSION}"
                messages_response = requests.get(messages_url, headers=headers)
                
                if messages_response.status_code == 200:
                    messages = messages_response.json()['data']
                    # Return the latest assistant message
                    for msg in messages:
                        if msg['role'] == 'assistant':
                            content = msg['content'][0]['text']['value']
                            return content
                break
            elif status in ['failed', 'cancelled', 'expired']:
                print(f"Run failed with status: {status}")
                break
        
        time.sleep(1)
    
    return "Sorry, I couldn't process your request at the moment."

@app.route('/')
def home():
    """Serve the main HR Policy Assistant interface optimized for Teams"""
    return send_from_directory('.', 'index.html')

@app.route('/privacy')
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

@app.route('/terms')
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

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    global current_thread_id
    
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Create thread if it doesn't exist
        if not current_thread_id:
            current_thread_id = create_thread()
            if not current_thread_id:
                return jsonify({'error': 'Failed to create conversation thread'}), 500
        
        # Send message and get response
        response = send_message(current_thread_id, message)
        
        if response:
            return jsonify({
                'response': response,
                'thread_id': current_thread_id
            })
        else:
            return jsonify({'error': 'Failed to get response from agent'}), 500
            
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/new-conversation', methods=['POST'])
def new_conversation():
    """Start a new conversation"""
    global current_thread_id
    current_thread_id = None
    return jsonify({'message': 'New conversation started'})

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'endpoint': ENDPOINT,
        'api_version': API_VERSION
    })

if __name__ == '__main__':
    print(f"🚀 Starting Simple AI Agent App")
    print(f"📡 Endpoint: {ENDPOINT}")
    print(f"🔗 Agent ID: {AGENT_ID}")
    print(f"📄 API Version: {API_VERSION}")
    
    # Get port from environment variable (Azure App Service uses this)
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🌐 Server will run on port: {port}")
    print("=" * 50)
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

