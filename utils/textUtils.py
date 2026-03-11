import html2text
import os
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from typing import Optional
import json


class TextUtils:

    @staticmethod
    def _ensure_log_dir(log_path: str):
        """Internal helper to make sure the log directory exists."""
        if not os.path.exists(log_path):
            os.makedirs(log_path)

    @staticmethod
    def get_medium_article_html(url: str, log_path: str) -> str:
        TextUtils._ensure_log_dir(log_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")

            try:
                page.wait_for_selector("article section", timeout=15000)
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Warning: {e}")

            html_content = page.content()
            browser.close()

            # Save log
            log_path = os.path.join(log_path, "LOG_page.html")
            with open(log_path, "w", encoding="UTF-8") as f:
                f.write(html_content)

            return html_content

    @staticmethod
    def get_podcast_ready_content(html_content: str, log_path: str) -> str:
        """
        Extract article content from Medium's HTML page.

        Medium stores article content in window.__APOLLO_STATE__ as a GraphQL cache.
        This function extracts and reconstructs the article from that data.

        Args:
            html_content: Raw HTML from Medium page (from Playwright or requests)
            log_path: Optional path to save debug log

        Returns:
            Clean markdown text of the article
        """

        def extract_json_with_brace_counting(s: str) -> str:
            """Extract valid JSON by counting braces to handle truncated data"""
            brace_count = 0
            in_string = False
            escape_next = False

            for i, char in enumerate(s):
                if escape_next:
                    escape_next = False
                    continue
                if char == "\\":
                    escape_next = True
                    continue
                if char == '"' and not in_string:
                    in_string = True
                elif char == '"' and in_string:
                    in_string = False
                elif not in_string:
                    if char in "{[":
                        brace_count += 1
                    elif char in "}]":
                        brace_count -= 1
                        if brace_count == 0:
                            return s[: i + 1]
            return s

        def apply_markups(text: str, markups: list) -> str:
            """Apply Medium's markup formatting (bold, links, etc.)"""
            if not markups:
                return text

            # Sort by start position (reverse to apply from end)
            markups = sorted(markups, key=lambda x: x.get("start", 0), reverse=True)

            for markup in markups:
                m_type = markup.get("type", "")
                start = markup.get("start", 0)
                end = markup.get("end", len(text))

                if start < 0 or end > len(text) or start >= end:
                    continue

                if m_type == "STRONG":
                    text = text[:start] + f"**{text[start:end]}**" + text[end:]
                elif m_type == "EM":
                    text = text[:start] + f"*{text[start:end]}*" + text[end:]
                elif m_type == "A":
                    href = markup.get("href", "")
                    text = text[:start] + f"[{text[start:end]}]({href})" + text[end:]
                elif m_type == "CODE":
                    text = text[:start] + f"`{text[start:end]}`" + text[end:]

            return text

        try:
            # Find Apollo state in HTML
            start_idx = html_content.find("window.__APOLLO_STATE__ = ")
            if start_idx == -1:
                # Fallback: try finding article in HTML directly (older Medium format)
                soup = BeautifulSoup(html_content, "html.parser")
                article = soup.find("article")
                if article:
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    h.body_width = 0
                    return h.handle(str(article))
                return ""

            # Extract JSON from script tag
            script_end = html_content.find("</script>", start_idx)
            script_content = html_content[start_idx:script_end]
            json_start = script_content.find("{")
            json_str = script_content[json_start:].rstrip().rstrip(";")

            # Parse JSON safely
            proper_json = extract_json_with_brace_counting(json_str)
            data = json.loads(proper_json)

            # Find Post object
            post_data = None
            for key, value in data.items():
                if key.startswith("Post:") and isinstance(value, dict):
                    if value.get("__typename") == "Post":
                        post_data = value
                        break

            if not post_data:
                return ""

            # Get content (handle the parameterized key)
            content_key = None
            for key in post_data.keys():
                if key.startswith("content("):
                    content_key = key
                    break

            if not content_key:
                return ""

            content = post_data.get(content_key, {})
            body_model = (
                content.get("bodyModel", {}) if isinstance(content, dict) else {}
            )
            paragraph_refs = body_model.get("paragraphs", [])

            # Resolve paragraph references
            paragraphs = []
            for ref in paragraph_refs:
                if isinstance(ref, dict) and "__ref" in ref:
                    para_data = data.get(ref["__ref"], {})
                    if para_data:
                        paragraphs.append(para_data)

            # Convert to markdown
            markdown_lines = []
            for p in paragraphs:
                p_type = p.get("type", "P")
                text = p.get("text", "")

                if not text.strip():
                    continue

                # Apply markups
                markups = p.get("markups", [])
                text = apply_markups(text, markups)

                # Format based on type
                if p_type == "H3":
                    markdown_lines.append(f"\n## {text}\n")
                elif p_type == "H4":
                    markdown_lines.append(f"\n### {text}\n")
                elif p_type == "PRE":
                    code_meta = p.get("codeBlockMetadata", {})
                    lang = code_meta.get("lang", "") if code_meta else ""
                    markdown_lines.append(f"\n```{lang}\n{text}\n```\n")
                elif p_type == "ULI":
                    markdown_lines.append(f"- {text}")
                elif p_type == "OLI":
                    markdown_lines.append(f"1. {text}")
                elif p_type == "IMG":
                    continue  # Skip images
                elif p_type == "PQ":
                    markdown_lines.append(f"> {text}")
                else:
                    markdown_lines.append(text)

            # Join and clean
            full_text = "\n\n".join(markdown_lines)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)

            # Remove junk phrases
            lines = full_text.split("\n")
            cleaned_lines = [
                l
                for l in lines
                if not any(
                    junk in l
                    for junk in [
                        "Follow",
                        "min read",
                        "Sign up",
                        "Sign in",
                        "Get the app",
                    ]
                )
            ]
            full_text = "\n".join(cleaned_lines)

            # Save log if requested
            if log_path:
                os.makedirs(log_path, exist_ok=True)
                log_file = os.path.join(log_path, "LOG_article.md")
                with open(log_file, "w", encoding="UTF-8") as f:
                    f.write(full_text)

            return full_text

        except Exception as e:
            print(f"Error extracting article: {e}")
            return ""
