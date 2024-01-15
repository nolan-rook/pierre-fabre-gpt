from flask import request, jsonify
from app.utils import handle_app_mention
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def slack_events():
    data = request.json
    logging.info(f"Received event: {data}")

    if 'challenge' in data:
        return jsonify({'challenge': data['challenge']})

    event = data.get('event', {})

    if event.get('type') == 'app_mention':
        handle_app_mention(event)
    elif event.get('type') == 'message' and event.get('channel_type') == 'im':
        handle_app_mention(event)

    return '', 200