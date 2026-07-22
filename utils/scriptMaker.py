import os
from medium_scraper import scrape, to_markdown, ScrapeError
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
        model: str = "openrouter:deepseek/deepseek-v4-flash",
    ) -> dict:
        print("scraping article")
        try:
            article = scrape(url)
            podcast_article = to_markdown(article)
        except ScrapeError as e:
            print(f"Scraping failed: {e}")
            return {"error": {"type": "scrape", "title": "Scraping failed", "message": str(e)}}

        if not podcast_article.strip():
            return dict()

        if log_path:
            os.makedirs(log_path, exist_ok=True)
            log_file = os.path.join(log_path, "LOG_article.md")
            with open(log_file, "w", encoding="UTF-8") as f:
                f.write(podcast_article)

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
