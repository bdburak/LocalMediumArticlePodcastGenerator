from utils.textUtils import TextUtils
from langchain.agents import create_agent
from langchain.messages import HumanMessage
from typing import List
from pydantic import BaseModel, Field
import json
from dotenv import load_dotenv

load_dotenv()

log_path = "./logs"

# Example URL:
# https://medium.com/@grom_65116/the-semantic-layer-is-dead-now-its-an-api-for-ai-agents-f91d48a0c74a
# Execution
# url = input("Enter a medium.com URL: ")
# Only non member url's are working
url = "https://medium.com/@hungquangphan/your-llm-is-the-dj-not-the-singer-b5305e4e7491"


print("getting raw html")
rawHTML = TextUtils.get_medium_article_html(url, log_path)


print("getting the article")
podcast_article = TextUtils.get_podcast_ready_content(rawHTML, log_path)

if podcast_article == "":
    exit()

with open("system_prompt.md", "r", encoding="UTF-8") as f:
    system_prompt = f.read()
    f.close()


# Defining the structure of the output


class ScriptTurn(BaseModel):
    speaker: str = Field(description="Host_A or Host_B")
    text: str = Field(description="The clean, spoken text for TTS.")


class PodcastScript(BaseModel):
    title: str
    topic: str
    script: List[ScriptTurn]


agent = create_agent(
    name="podcast_writer_agent",
    model="gpt-5.2",
    system_prompt=system_prompt,
    response_format=PodcastScript,
)

print("invoking agent")
result = agent.invoke({"messages": [HumanMessage(content=podcast_article)]})

print("loading structured output to json string")
result_structured = result["structured_response"]

podcast_dict = result_structured.model_dump()
json_string = json.dumps(podcast_dict, indent=4, ensure_ascii=False)


with open(f"{log_path}/LOG_dialog.json", "w", encoding="UTF-8") as f:
    print("saving dict to json log")
    json.dump(podcast_dict, f, indent=4, ensure_ascii=False)
    f.close()
