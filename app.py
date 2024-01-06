import os
import threading
from flask import Flask, request, jsonify
from orquesta_sdk import Orquesta, OrquestaClientOptions
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
    slack_client.token =  os.getenv("SLACK_BOT_TOKEN")  # Use the token from the session
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

    # Check if the deployment has choices and a message
    if deployment.choices and deployment.choices[0].message:
        # Reply to the thread with the result from Orquesta
        slack_client.chat_postMessage(
            channel=event['channel'],
            thread_ts=event['ts'],
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
        # Send an immediate response to acknowledge the command
        immediate_response = "Processing your Orquesta query for command: {}".format(command)
        threading.Thread(target=execute_orquesta_command, args=(orquesta_key, command_text, response_url, user_id, channel_id, data.get('ts'))).start()
        return jsonify({'text': immediate_response}), 200
    else:
        # Command not recognized, send an error message
        return jsonify({'text': "Sorry, I don't recognize that command."}), 200

def execute_orquesta_command(orquesta_key, command_text, response_url, user_id, channel_id, ts):
    # Define a regex pattern to match the command text within square brackets
    pattern = r.*?).*)]'
    
    # Initialize variables dictionary
    variables = {}

    # Match the command text against the regex pattern
    matches = re.match(pattern, command_text)

    if not matches:
        # If the pattern does not match, send a usage message and return
        slack_client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            text=f"Usage: {command} [argument1] [argument2] ... Check your formatting and try again."
        )
        return

    # Extract the matched groups based on the command
    if orquesta_key == "blog-post-creator":
        keywords, content = matches.groups()
        variables = {"keywords": keywords, "content": content}
    elif orquesta_key == "linkedin-post-creator":
        user, content = matches.groups()
        variables = {"user": user, "content": content}
    elif orquesta_key == "content-to-persona-creator":
        content, = matches.groups()
        variables = {"content": content}
    elif orquesta_key == "mail-creator":
        to, from_user, content = re.match(r[(.*?)s[(.*?)s command_text).groups()
        variables = {"to": to, "from": from_user, "content": content}
    elif orquesta_key == "image-creator-prompt":
        goal_of_image, = matches.groups()
        variables = {"goal_of_image": goal_of_image}
        # Invoke the image-creator-prompt deployment
        prompt_deployment = client.deployments.invoke(
            key="image-creator-prompt",
            inputs=variables
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
    else:
        # Invoke the Orquesta deployment for other commands
        deployment = client.deployments.invoke(
            key=orquesta_key,
            inputs=variables
        )

        # Check if the deployment has choices and a message
        if deployment.choices and deployment.choices[0].message:
            # Use the response_url to send the result back to Slack
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text=deployment.choices[0].message.content
            )
        else:
            # Handle the case where there is no message in the choices
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text="There was an error processing your request."
            )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)