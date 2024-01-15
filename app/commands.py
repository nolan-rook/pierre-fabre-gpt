from flask import request, jsonify
from app.utils import (
    parse_command_arguments,
    post_error_message
)
from app import slack_client as slack_client_module
from app import orquesta_client as orquesta_client_module
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)

def slack_commands():
    data = request.form
    command_text = data.get('text')
    command = data.get('command')
    channel_id = data.get('channel_id')
    ts = data.get('ts')

    logging.info(f"Received command '{command}' with text: {command_text}")

    if command == "/content-BEMelanoma-All":
        return handle_all_personas_command(command_text, channel_id, ts)

    return handle_individual_command(command, command_text, channel_id, ts)

def handle_all_personas_command(command_text, channel_id, ts):
    immediate_response = f"Processing your request for all personas with content: '{command_text}'"
    handle_content_BEMelanoma_All(command_text, channel_id, ts)
    return jsonify({'text': immediate_response}), 200

def handle_individual_command(command, command_text, channel_id, ts):
    command_to_key_map = {
    "/blog": "pierre-fabre-blog-post-creator",
    "/linkedin-post": "pierre-fabre-linkedin-post-creator",
    "/content-to-persona": "pierre-fabre-content-to-persona-creator",
    "/mail": "pierre-fabre-mail-creator",
    "/image": "pierre-fabre-image-creator-prompt",
    "/content-BEMelanoma-Innovator": "pierre-fabre-content-BEMelanoma-Innovator-creator",
    "/content-BEMelanoma-Science": "pierre-fabre-content-BEMelanoma-Science-creator",
    "/content-BEMelanoma-Patient": "pierre-fabre-content-BEMelanoma-Patient-creator"
    }

    orquesta_key = command_to_key_map.get(command)
    if orquesta_key:
        immediate_response = f"Processing your request for command: '{command}' with content: '{command_text}'"
        threading.Thread(target=execute_orquesta_command, args=(orquesta_key, command_text, channel_id, ts)).start()
        return jsonify({'text': immediate_response}), 200
    else:
        return jsonify({'text': f"Sorry, I don't recognize the command '{command}'."}), 200

def execute_orquesta_command(orquesta_key, command_text, channel_id, ts):
    try:
        inputs = get_orquesta_inputs(orquesta_key, command_text)
        if orquesta_key == "image-creator-prompt":
            handle_image_creation(inputs, channel_id, ts)
        else:
            invoke_orquesta_and_post_message(orquesta_key, inputs, channel_id, ts)
    except ValueError as e:
        post_error_message(channel_id, ts, str(e))
    except Exception as e:
        logging.error(f"An error occurred while invoking the Orquesta deployment: {e}")
        post_error_message(channel_id, ts, "An error occurred while processing your request.")

def get_orquesta_inputs(orquesta_key, command_text):
    args = parse_command_arguments(command_text)
    command_to_inputs = {
        "blog-post-creator": {"content": args[1], "keywords": args[0]} if len(args) >= 2 else None,
        "linkedin-post-creator": {"user": args[0], "content": args[1]} if len(args) >= 2 else None,
        "content-to-persona-creator": {"content": command_text},
        "mail-creator": {"to": args[0], "from_": args[1], "content": args[2]} if len(args) >= 3 else None,
        "image-creator-prompt": {"goal_of_image": command_text},
        "content-BEMelanoma-Innovator-creator": {"content": command_text},
        "content-BEMelanoma-Science-driven-creator": {"content": command_text},
        "content-BEMelanoma-Patient-oriented-creator": {"content": command_text},
    }

    if orquesta_key not in command_to_inputs:
        raise ValueError(f"Command '{orquesta_key}' is not recognized.")

    if command_to_inputs[orquesta_key] is None:
        raise ValueError(f"Insufficient arguments provided for command '{orquesta_key}'.")

    return command_to_inputs[orquesta_key]

def handle_image_creation(inputs, channel_id, ts):
    prompt_deployment = orquesta_client_module.client.deployments.invoke(key="image-creator-prompt", inputs=inputs)
    if prompt_deployment.choices and prompt_deployment.choices[0].message:
        image_deployment = orquesta_client_module.client.deployments.invoke(
            key="pierre-fabre-image-creator",
            inputs={"prompt": prompt_deployment.choices[0].message.content}
        )
        image_url = image_deployment.choices[0].message.url
        post_image_message(image_url, channel_id, ts)
    else:
        raise ValueError("There was an error processing your prompt request.")

def post_image_message(image_url, channel_id, ts):
    slack_client_module.slack_client.chat_postMessage(
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

def invoke_orquesta_and_post_message(orquesta_key, inputs, channel_id, ts):
    deployment = orquesta_client_module.client.deployments.invoke(key=orquesta_key, inputs=inputs)
    slack_client_module.slack_client.chat_postMessage(
        channel=channel_id,
        thread_ts=ts,
        text=deployment.choices[0].message.content
    )

def handle_content_BEMelanoma_All(command_text, channel_id, ts):
    content = command_text
    inputs = {"content": content}

    # Define the keys for the three different personas
    persona_keys = {
        "content-BEMelanoma-Innovator": "pierre-fabre-content-BEMelanoma-Innovator-creator",
        "content-BEMelanoma-Science": "pierre-fabre-content-BEMelanoma-Science-creator",
        "content-BEMelanoma-Patient": "pierre-fabre-content-BEMelanoma-Patient-creator"
    }

    # Initialize an empty list to store the results
    results = []

    # Loop over the persona_keys and invoke the corresponding Orquesta deployments
    for persona, key in persona_keys.items():
        try:
            # Invoke the Orquesta deployment
            deployment = orquesta_client_module.client.deployments.invoke(
                key=key,
                inputs=inputs
            )

            # Append the result to the results list
            result_text = f"Persona {persona}n{deployment.choices[0].message.content}"
            results.append(result_text)
        except Exception as e:
            # Log the exception for debugging
            logging.error(f"An error occurred while invoking the Orquesta deployment for {persona}: {e}")

            # Append an error message to the results list
            results.append(f"An error occurred while processing your request for persona: {persona}")

    # Join the results into a single string with line breaks between each result
    combined_results ="\n".join(results)

    # Send the combined result back to Slack
    slack_client_module.slack_client.chat_postMessage(
        channel=channel_id,
        thread_ts=ts,  # Use the timestamp from the Slash Command request
        text=combined_results
    )