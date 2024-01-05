import os
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from orquesta_sdk import OrquestaClient, OrquestaClientOptions
from orquesta_sdk.endpoints import OrquestaEndpointRequest
from slack_sdk import WebClient
# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack client
slack_client = WebClient()

# Initialize Orquesta client
api_key = os.getenv("ORQUESTA_API_KEY")
options = OrquestaClientOptions(api_key=api_key, ttl=3600, environment="production")
client = OrquestaClient(options)

# Route for handling Slack events
@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json

    # Slack sends a challenge parameter in the initial verification request
    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})

    event = data.get('event', {})

    # Handle app_mention events
    if event.get('type') == 'app_mention':
        handle_app_mention(event)

    return '', 200  # HTTP 200 with empty body

def handle_app_mention(event):
    # Extract the text mentioned to the bot
    prompt_user = event.get('text', '').split('>')[1].strip()

    # Send an immediate response to Slack indicating that the request is being processed
    slack_client.token =  os.getenv("SLACK_BOT_TOKEN")  # Use the token from the session
    slack_client.chat_postMessage(
        channel=event['channel'],
        thread_ts=event['ts'],  # Ensure this is the original message timestamp
        text="Processing your request, please wait..."
    )

    # Start a new thread to handle the long-running Orquesta API call
    threading.Thread(target=query_orquesta, args=(event, prompt_user)).start()

def query_orquesta(event, prompt_user):
    # Create an OrquestaEndpointRequest object
    orquesta_request = OrquestaEndpointRequest(
        key="pierre-slack-app",
        variables={"prompt": prompt_user}
    )

    # Query the OrquestaClient for a response
    result = client.endpoints.query(orquesta_request)

    # Reply to the thread with the result from Orquesta
    slack_client.chat_postMessage(
        channel=event['channel'],
        thread_ts=event['ts'],  # Ensure this is the original message timestamp
        text=result.content
    )

@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    # Your request verification logic here

    # Respond immediately to avoid "dispatch_failed" error
    return jsonify({
        "response_type": "in_channel",  # or "ephemeral" for a private response
        "text": "Processing your request..."
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)