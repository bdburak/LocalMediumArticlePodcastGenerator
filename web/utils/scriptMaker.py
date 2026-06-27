from utils.textUtils import TextUtils
from langchain.agents import create_agent
from langchain.messages import HumanMessage
from typing import List
from pydantic import BaseModel, Field
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()


class ScriptMaker:
    def __init__(self) -> None:
        pass

    async def generateScript(
        self,
        log_path: str = "./logs",
        url: str = "",
        model: str = "openrouter:nvidia/nemotron-3-nano-30b-a3b:free",
    ) -> dict:
        print("getting raw html")
        rawHTML = await TextUtils.get_medium_article_html_async(url, log_path)

        print("getting the article")
        podcast_article = TextUtils.get_podcast_ready_content(rawHTML, log_path)

        if podcast_article == "":
            return dict()

        with open("utils/system_prompt.md", "r", encoding="UTF-8") as f:
            system_prompt = f.read()
            f.close()

        class ScriptTurn(BaseModel):
            speaker: str = Field(description="Host_A or Host_B")
            text: str = Field(description="The clean, spoken text for TTS.")

        class PodcastScript(BaseModel):
            title: str
            topic: str
            script: List[ScriptTurn]

        agent = create_agent(
            name="podcast_writer_agent",
            model=model,
            system_prompt=system_prompt,
            response_format=PodcastScript,
        )

        print("invoking agent")
        result = await asyncio.to_thread(
            agent.invoke, {"messages": [HumanMessage(content=podcast_article)]}
        )

        print("loading structured output to json string")
        result_structured = result["structured_response"]

        podcast_dict = result_structured.model_dump()
        json_string = json.dumps(podcast_dict, indent=4, ensure_ascii=False)

        with open(f"{log_path}/LOG_dialog.json", "w", encoding="UTF-8") as f:
            print("saving dict to json log")
            json.dump(podcast_dict, f, indent=4, ensure_ascii=False)
            f.close()

        return podcast_dict
