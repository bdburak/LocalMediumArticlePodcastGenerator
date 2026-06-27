import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel
import os
from utils.speaker import Speaker
from utils.scriptMaker import ScriptMaker
from utils.wavCombiner import combine_wavs_interleaved
import numpy as np
import asyncio

batching_count = 5

print("Loading model")
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",
)

print("Initializig ScriptMaker")
scriptMaker = ScriptMaker()


async def main():
    print("Generating script")
    conversation = await scriptMaker.generateScript(
        url="https://medium.com/@brettluelling/sdlc-for-agentic-ai-engineering-5813abfdbc12"
    )

    print("starting generating audio")
    print(f"total number of clips to generate: {len(conversation['script']) / 2}")

    speaker_a = Speaker()
    speaker_b = Speaker()

    speaker_a.name = "prime"
    speaker_a.referece_audio_path = "./ref/prime.wav"
    speaker_a.reference_text = "You would be able to effectively kind of circumvent Cloudflare's randomness, and boom, you could guess all the keys, right? Well, it turns out that they do even more than that. Many operating systems have their own sources of random data for use in cryptographic seeds—for instance, user actions, mouse movements, keyboard typing, blah blah blah. Although they obtain this data relatively slowly."

    print("cloning speaker_a voice")
    speaker_a.voiceClonePromptItems = model.create_voice_clone_prompt(
        ref_audio=speaker_a.referece_audio_path,
        ref_text=speaker_a.reference_text,
    )
    print("cloned speaker_a voice\n")

    speaker_b.name = "morgan"
    speaker_b.referece_audio_path = "./ref/morgan.wav"
    speaker_b.reference_text = """
    When to leave and where to go.
    It's not Shakespeare.
    It does not speak in memorable lines.
    My inner voice always gives it to me straight.
    Tells me who my real friends are.
    When to say yes, when to say no.
    Whether the person sitting next to me is the one I'll be spending the rest of my life with.
    """
    print("cloning speaker_b voice")
    speaker_b.voiceClonePromptItems = model.create_voice_clone_prompt(
        ref_audio=speaker_b.referece_audio_path,
        ref_text=speaker_b.reference_text,
    )
    print("cloned speaker_b voice\n")

    os.makedirs(f"./{speaker_a.name}", exist_ok=True)
    os.makedirs(f"./{speaker_b.name}", exist_ok=True)

    speaker_a.dialog_lines.append(conversation["topic"])

    for line in conversation["script"]:
        if line["speaker"] == "Host_A":
            speaker_a.dialog_lines.append(line["text"])
        elif line["speaker"] == "Host_B":
            speaker_b.dialog_lines.append(line["text"])

    batched_speaker_a_lines = [
        speaker_a.dialog_lines[i : i + batching_count]
        for i in range(0, len(speaker_a.dialog_lines), batching_count)
    ]

    batched_speaker_b_lines = [
        speaker_b.dialog_lines[i : i + batching_count]
        for i in range(0, len(speaker_b.dialog_lines), batching_count)
    ]

    speaker_a_wavs = []
    speaker_b_wavs = []

    print(f"Generating dialog for speaker_a")
    for i, batch in enumerate(batched_speaker_a_lines):
        print(f"generating batch {i + 1} out of {len(batched_speaker_a_lines)}")

        with torch.no_grad():
            speaker_a_wavs_temp, sr = model.generate_voice_clone(
                text=batch,
                language="English",
                voice_clone_prompt=speaker_a.voiceClonePromptItems,
            )

        if torch.is_tensor(speaker_a_wavs_temp):
            speaker_a_wavs_temp = speaker_a_wavs_temp.cpu().numpy()

        speaker_a_wavs.extend(speaker_a_wavs_temp)

        del speaker_a_wavs_temp
        torch.cuda.empty_cache()

    print(f"Generating dialog for speaker_b")
    for i, batch in enumerate(batched_speaker_b_lines):
        print(f"generating batch {i + 1} out of {len(batched_speaker_b_lines)}")

        with torch.no_grad():
            speaker_b_wavs_temp, sr = model.generate_voice_clone(
                text=batch,
                language="English",
                voice_clone_prompt=speaker_b.voiceClonePromptItems,
            )

        if torch.is_tensor(speaker_b_wavs_temp):
            speaker_b_wavs_temp = speaker_b_wavs_temp.cpu().numpy()

        speaker_b_wavs.extend(speaker_b_wavs_temp)

        del speaker_b_wavs_temp
        torch.cuda.empty_cache()

    combined_dialog = combine_wavs_interleaved(
        speaker_a_wavs[0], speaker_a_wavs[1::], speaker_b_wavs, sr, 0.5
    )

    sf.write("full_episode_async.wav", combined_dialog, sr)
    print(f"✅ Saved combined audio: {len(combined_dialog) / sr:.1f} seconds total")


if __name__ == "__main__":
    asyncio.run(main())
