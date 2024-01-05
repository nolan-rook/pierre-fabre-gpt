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

# Updated Route for handling Slash Commands
@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    data = request.form  # Slack sends command data as form-encoded

    # Extract the command text and other relevant information
    command_text = data.get('text')
    command = data.get('command')
    response_url = data.get('response_url')
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')

    # Map the command to the corresponding Orquesta prompt key
    command_to_key_map = {
        "/blog": "blog-post-creator",
        "/linkedin-post": "linkedin-post-creator",
        "/content-to-persona": "content-to-persona-creator",
        "/mail": "mail-creator",
        "/image": "image-creator-prompt"
    }

    # Check if the command is recognized and get the Orquesta prompt key
    orquesta_key = command_to_key_map.get(command)

    if orquesta_key:
        # Send an immediate response to acknowledge the command
        immediate_response = "Processing your Orquesta query for command: {}".format(command)
        threading.Thread(target=execute_orquesta_command, args=(orquesta_key, command_text, response_url, user_id, channel_id, data.get('ts'))).start()
        return jsonify({'text': immediate_response}), 200
    else:
        # Command not recognized, send an error message
        return jsonify({'text': "Sorry, I don't recognize that command."}), 200

def execute_orquesta_command(orquesta_key, command_text, response_url, user_id, channel_id, ts):
    # Parse the command_text based on the command to extract the necessary variables
    variables = {}
    if orquesta_key == "blog-post-creator":
        try:
            keywords, content = command_text.split(' ', 1)
            variables = {"keywords": keywords, "content": content}
        except ValueError:
            # Handle the error if the command_text does not contain the expected number of arguments
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="Usage: /blog [keywords] [content]"
            )
            return
    elif orquesta_key == "linkedin-post-creator":
        try:
            user, content = command_text.split(' ', 1)
            variables = {"user": user, "content": content}
        except ValueError:
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="Usage: /linkedin-post [user] [content]"
            )
            return
    elif orquesta_key == "content-to-persona-creator":
        content = command_text
        variables = {"content": content}
    elif orquesta_key == "mail-creator":
        try:
            to, from_user, content = command_text.split(' ', 2)
            variables = {"to": to, "from": from_user, "content": content}
        except ValueError:
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="Usage: /mail [to] [from] [content in bulletpoints]"
            )
            return
    # Special handling for image-creator-prompt
    elif orquesta_key == "image-creator-prompt":
        # Step 1: Query the image-creator-prompt endpoint
        goal_of_image = command_text
        prompt_request = OrquestaEndpointRequest(
            key="image-creator-prompt",
            variables={"goal_of_image": goal_of_image}
        )
        prompt_result = client.endpoints.query(prompt_request)

        # Check if the prompt_result is successful and contains content
        if prompt_result.is_successful and prompt_result.content:
            # Step 2: Send the result to the image-creator endpoint
            image_creator_request = OrquestaEndpointRequest(
                key="image-creator",
                variables={"prompt": prompt_result.content}
            )
            image_creator_result = client.endpoints.query(image_creator_request)

            # Check if the image_creator_result is successful and contains an image URL
            if image_creator_result.is_successful and image_creator_result.content:
                # Send the image to Slack as an attachment
                slack_client.token = os.getenv("SLACK_BOT_TOKEN")
                slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=ts,
                    blocks=[
                        {
                            "type": "image",
                            "title": {
                                "type": "plain_text",
                                "text": "Generated Image"
                            },
                            "image_url": image_creator_result.content,
                            "alt_text": "Generated image"
                        }
                    ]
                )
                return  # End the function after sending the image
            else:
                # Handle the case where the image_creator_result is not successful
                slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=ts,
                    text="Failed to create image. Please try again."
                )
                return  # End the function after sending the error message
        else:
            # Handle the case where the prompt_result is not successful
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="Failed to generate image prompt. Please try again."
            )
            return  # End the function after sending the error message

    # Create an OrquestaEndpointRequest object with the specific variables for the command
    orquesta_request = OrquestaEndpointRequest(
        key=orquesta_key,
        variables=variables
    )

    # Query the OrquestaClient for a response
    result = client.endpoints.query(orquesta_request)

    # Use the response_url to send the result back to Slack
    slack_client.token = os.getenv("SLACK_BOT_TOKEN")
    slack_client.chat_postMessage(
        channel=channel_id,
        thread_ts=ts,  # Use the timestamp from the Slash Command request
        text=result.content
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)