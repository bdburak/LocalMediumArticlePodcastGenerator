# Local AI Podcast Generator

With this gui users will be able to create audio podcasts from Mediumm articles. Here is the simple workflow:

1. User enters the URL.
    1. The `medium-scraper` library fetches and parses the article content
   2. The article and a system prompt are fed into a langchain agent which creates a podcast dialog script in a json format
   3. The generated script is shown to the user
2. User proceeds to the next stage which is the voice cloning stage.
   1. There will be two fields for dragging and dropping wav files for the reference audio of Speaker A and Speaker B
      1. The uploaded files will be uploaded to the `./web/uploads/ref_voices/` folder. If it does not exist, create it.
      2. After reference audios are uploaded, there also needs to be a way to play them back
   2. For each one, there will also be an optional text transcript area where the user can either write or paste in the transcript of the reference audio for better voice cloning precision
   3. There will be a generate voice clones button that will generate them
3. After voice clones are generated the user will proceed to the next stage, this is the podcast generation stage. There will be a button for generating the podcast. Also there needs to be a way to show the progress of it

## Rules

- All of these things will be created within the `./web` folder.
- I want place holders for the generated stuff.
  - An example of the dialog is within the `./web` folder called `./web/placeholders/LOG_dialog.json`. Use it for the generated dialog
  - An example of the generated podcast audio is also present as the `./web/placeholders/full_episode_async.wav` file.
- I want it to be a python web application. I don't want django or gradio.
- Use placeholder api calls and such for the project for now. The functionality and api's will be created later on with all the needed web scraping, podcast script generation and tts later on.
