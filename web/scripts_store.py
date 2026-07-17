import json
import os
from uuid import uuid4

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "scripts")


def _ensure_dir():
    os.makedirs(SCRIPTS_DIR, exist_ok=True)


def load_scripts():
    _ensure_dir()
    scripts = []
    for filename in os.listdir(SCRIPTS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SCRIPTS_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                s = json.load(f)
                scripts.append({
                    "id": s["id"],
                    "article_url": s.get("article_url", ""),
                    "article_title": s.get("article_title", "Untitled"),
                    "created_at": s.get("created_at", ""),
                    "turns": s.get("turns", 0),
                })
    scripts.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return scripts


def save_script(script: dict):
    _ensure_dir()
    script["id"] = script.get("id") or uuid4().hex[:12]
    filepath = os.path.join(SCRIPTS_DIR, f"{script['id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    return script["id"]


def get_script(script_id: str):
    filepath = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_script(script_id: str):
    filepath = os.path.join(SCRIPTS_DIR, f"{script_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
