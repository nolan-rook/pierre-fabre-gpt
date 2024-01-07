import os
import threading
from flask import Flask, request, jsonify
from orquesta_sdk import Orquesta, OrquestaClientOptions
import shlex
from slack_sdk import WebClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack client
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

# Initialize Orquesta client
api_key = os.getenv("ORQUESTA_API_KEY")
options = OrquestaClientOptions(api_key=api_key, environment="production")
client = Orquesta(options)

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
    slack_client.chat_postMessage(
        channel=event['channel'],
        thread_ts=event['ts'],  # Ensure this is the original message timestamp
        text="Processing your request, please wait..."
    )

    # Start a new thread to handle the long-running Orquesta API call
    threading.Thread(target=query_orquesta, args=(event, prompt_user)).start()

def query_orquesta(event, prompt_user):
    # Invoke the Orquesta deployment
    deployment = client.deployments.invoke(
        key="pierre-slack-app",
        inputs={"prompt": prompt_user}
    )

    # Reply to the thread with the result from Orquesta
    slack_client.chat_postMessage(
        channel=event['channel'],
        thread_ts=event['ts'],  # Ensure this is the original message timestamp
        text=deployment.choices[0].message.content
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
        # Send an immediate response to acknowledge the command and include the command text
        immediate_response = "Processing your request for command: '{}', with: '{}'".format(command, command_text)
        threading.Thread(target=execute_orquesta_command, args=(orquesta_key, command_text, response_url, user_id, channel_id, data.get('ts'))).start()
        return jsonify({'text': immediate_response}), 200
    else:
        # Command not recognized, send an error message
        return jsonify({'text': "Sorry, I don't recognize that command."}), 200

def execute_orquesta_command(orquesta_key, command_text, response_url, user_id, channel_id, ts):
    # Parse the command_text based on the command to extract the necessary inputs
    inputs = {}

    # Use shlex to split the command_text into arguments while respecting quoted substrings
    try:
        args = shlex.split(command_text)
    except ValueError as e:
        slack_client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            text=f"Error parsing arguments: {e}. Make sure to enclose each argument with double quotes."
        )
        return

    # Map the command to the corresponding Orquesta inputs
    if orquesta_key == "blog-post-creator":
        try:
            keywords, content = args
            inputs = {"content": content, "keywords": keywords}
        except ValueError:
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text='Usage: /blog "keywords" "content"'
            )
            return
    elif orquesta_key == "linkedin-post-creator":
        try:
            user, content = args
            inputs = {"user": user, "content": content}
        except ValueError:
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text='Usage: /linkedin-post "user" "content"'
            )
            return
    elif orquesta_key == "content-to-persona-creator":
        content = command_text
        inputs = {"content": content}
    elif orquesta_key == "mail-creator":
        try:
            to, from_, content = args
            inputs = {"to": to, "from_": from_, "content": content}
        except ValueError:
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text='Usage: /mail "to" "from" "content"'
            )
            return
    elif orquesta_key == "image-creator-prompt":
        inputs = {"goal_of_image": command_text}

        # Step 1: Invoke the image-creator-prompt deployment
        prompt_deployment = client.deployments.invoke(
            key="image-creator-prompt",
            inputs=inputs
        )

        # Check if the prompt deployment has choices and a message
        if prompt_deployment.choices and prompt_deployment.choices[0].message:
            # Step 2: Invoke the image-creator deployment with the result from the first prompt
            image_deployment = client.deployments.invoke(
                key="image-creator",
                inputs={"prompt": prompt_deployment.choices[0].message.content}
            )

            # Assuming the correct attribute is 'url' instead of 'content'
            image_url = image_deployment.choices[0].message.url  # Adjust this line based on the output
            # Send the image URL to Slack
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
                        "image_url": image_url,
                        "alt_text": "Generated image"
                    }
                ]
            )
        else:
            # Handle the case where there is no message in the choices for the prompt deployment
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="There was an error processing your prompt request."
            )
        return  # End the function after handling the image creation
    try:
        # Log the request body for debugging
        print(f"Invoking Orquesta deployment with key: {orquesta_key} and inputs: {inputs}")

        # Invoke the Orquesta deployment
        deployment = client.deployments.invoke(
            key=orquesta_key,
            inputs=inputs
        )

        # Use the response_url to send the result back to Slack
        slack_client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,  # Use the timestamp from the Slash Command request
            text=deployment.choices[0].message.content
        )
    except Exception as e:
        # Log the exception for debugging
        print(f"An error occurred while invoking the Orquesta deployment: {e}")

        # Send an error message back to Slack
        slack_client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            text="An error occurred while processing your request."
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)