from flask import Flask
from app.events import slack_events
from app.commands import slack_commands
from app.slack_client import init_slack_client
from app.orquesta_client import init_orquesta_client

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack client
init_slack_client()

# Initialize Orquesta client
init_orquesta_client()

# Route for handling Slack events
app.add_url_rule('/slack/events', view_func=slack_events, methods=['POST'])

# Route for handling Slash Commands
app.add_url_rule('/slack/commands', view_func=slack_commands, methods=['POST'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)