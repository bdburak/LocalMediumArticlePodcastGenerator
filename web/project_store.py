import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
VOICES_FILE = os.path.join(DATA_DIR, "voices.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_projects():
    _ensure_data_dir()
    if not os.path.exists(PROJECTS_FILE):
        return []
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(project: dict):
    projects = load_projects()
    projects.insert(0, project)
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)


def get_project(project_id: str):
    for p in load_projects():
        if p["id"] == project_id:
            return p
    return None


def load_voices():
    _ensure_data_dir()
    if not os.path.exists(VOICES_FILE):
        return {}
    with open(VOICES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_voice(voice: dict):
    voices = load_voices()
    voices[voice["name"]] = voice
    with open(VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, indent=2, ensure_ascii=False)


def delete_voice(name: str):
    voices = load_voices()
    voices.pop(name, None)
    with open(VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, indent=2, ensure_ascii=False)


def delete_project(project_id: str):
    projects = load_projects()
    projects = [p for p in projects if p["id"] != project_id]
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)
