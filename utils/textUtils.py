import html2text
import os
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class TextUtils:
    LOG_DIR = "./logs"

    @staticmethod
    def _ensure_log_dir():
        """Internal helper to make sure the log directory exists."""
        if not os.path.exists(TextUtils.LOG_DIR):
            os.makedirs(TextUtils.LOG_DIR)

    @staticmethod
    def get_medium_article_html(url: str) -> str:
        TextUtils._ensure_log_dir()

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
            log_path = os.path.join(TextUtils.LOG_DIR, "LOG_page.html")
            with open(log_path, "w", encoding="UTF-8") as f:
                f.write(html_content)

            return html_content

    @staticmethod
    def get_podcast_ready_content(html_content: str) -> str:
        TextUtils._ensure_log_dir()

        soup = BeautifulSoup(html_content, "html.parser")
        article = soup.find("article")

        if not article:
            print("Article not found!")
            return ""

        # 1. Strip junk
        for junk in article.select("button, nav, svg, figcaption"):
            junk.decompose()

        # 2. Configure HTML2Text
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        h.ignore_emphasis = False

        markdown_content = h.handle(str(article))

        # 3. Final polish
        lines = markdown_content.split("\n")
        cleaned_lines = [l for l in lines if "Follow" not in l and "min read" not in l]
        cleaned_article = "\n".join(cleaned_lines)

        # Save log
        log_path = os.path.join(TextUtils.LOG_DIR, "LOG_article.md")
        with open(log_path, "w", encoding="UTF-8") as f:
            f.write(cleaned_article)

        return cleaned_article
