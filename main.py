from playwright.sync_api import sync_playwright
import html2text
from bs4 import BeautifulSoup

logging_folder_path = "./logs"


def get_medium_article_html(url):
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
        return html_content


def get_podcast_ready_content(html_content):

    soup = BeautifulSoup(html_content, "html.parser")
    article = soup.find("article")

    if not article:
        print("Article not found!")
        return

    # 1. Strip known Medium "Junk" before converting
    for junk in article.select("button, nav, svg, figcaption"):
        junk.decompose()

    # 2. Configure HTML2Text for the cleanest output
    h = html2text.HTML2Text()
    h.ignore_links = True  # Podcast hosts don't read URLs
    h.ignore_images = True  # Podcast hosts can't see images
    h.body_width = 0  # Don't wrap lines
    h.ignore_emphasis = False  # Keep bold/italics (helps LLM find key terms)

    markdown_content = h.handle(str(article))

    # 3. Final polish: Remove the "Follow/Read" metadata lines
    lines = markdown_content.split("\n")
    cleaned_lines = [l for l in lines if "Follow" not in l and "min read" not in l]
    cleaned_article = "\n".join(cleaned_lines)

    with open(f"{logging_folder_path}/LOG_article.md", "w", encoding="UTF-8") as f:
        f.write(cleaned_article)
        f.close()

    return cleaned_article


# Example URL:
# https://medium.com/@grom_65116/the-semantic-layer-is-dead-now-its-an-api-for-ai-agents-f91d48a0c74a
# Execution
url = input("Enter a medium.com URL: ")

rawHTML = get_medium_article_html(url)

# Create a log file containing the extracted page
with open(f"{logging_folder_path}/LOG_page.html", "w", encoding="UTF-8") as f:
    f.write(rawHTML)
    f.close()

podcast_article = get_podcast_ready_content(rawHTML)
