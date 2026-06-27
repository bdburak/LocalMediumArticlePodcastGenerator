from typing import Dict, Any


def dialog_to_markdown(dialog: Dict[str, Any]) -> str:
    """
    Convert a dialog dictionary to a markdown formatted string.

    Args:
        dialog: A dictionary with keys:
            - title (str): The title of the dialog/podcast
            - topic (str): The topic description
            - script (list): List of dicts with 'speaker' and 'text' keys

    Returns:
        A markdown formatted string
    """
    lines = []

    title = dialog.get("title", "")
    if title:
        lines.append(f"# {title}")
        lines.append("")

    topic = dialog.get("topic", "")
    if topic:
        lines.append(f"*Topic: {topic}*")
        lines.append("")

    script = dialog.get("script", [])
    if script:
        for entry in script:
            speaker = entry.get("speaker", "Unknown")
            text = entry.get("text", "")
            lines.append(f"**{speaker}**: {text}")
            lines.append("")

    return "\n".join(lines)
