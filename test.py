import os
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

from orquesta_sdk import Orquesta, OrquestaClientOptions

api_key = os.getenv("ORQUESTA_API_KEY")

options = OrquestaClientOptions(
    api_key=api_key,
    environment="production"
)

client = Orquesta(options)

deployment = client.deployments.invoke(
  key="blog-post-creator",
  context={
    "environments": []
  },
  inputs={
    "content": "Hoe Amersfoort zijn transportnetwerk verbetert voor een duurzame toekomst",
    "keywords": "mobiliteit, Amersfoort"
  },
  metadata={"custom-field-name":"custom-metadata-value"}
)

print(deployment.choices[0].message.content)