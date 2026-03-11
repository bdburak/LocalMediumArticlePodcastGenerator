from utils.textUtils import TextUtils

# Example URL:
# https://medium.com/@grom_65116/the-semantic-layer-is-dead-now-its-an-api-for-ai-agents-f91d48a0c74a
# Execution
url = input("Enter a medium.com URL: ")

rawHTML = TextUtils.get_medium_article_html(url)

podcast_article = TextUtils.get_podcast_ready_content(rawHTML)
