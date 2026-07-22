import torch
from typing import List, Tuple
import soundfile as sf
from qwen_tts import Qwen3TTSModel
import os
import shutil
import numpy as np
from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
from utils.speaker import Speaker
import time


class TTS:

    def __init__(
        self,
        temp_file_location="./LOG_temp_test",
    ) -> None:

        self.temp_file_location = temp_file_location
        self.model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )

    def create_voice_clone_prompt_items(
        self, reference_audio_path: str, reference_text: str = ""
    ) -> List[VoiceClonePromptItem]:

        if reference_text != "" and reference_text != None:
            print("using reference audio")
            return self.model.create_voice_clone_prompt(
                ref_audio=reference_audio_path,
                ref_text=reference_text,
            )
        print("not using reference audio")
        return self.model.create_voice_clone_prompt(
            ref_audio=reference_audio_path, x_vector_only_mode=True
        )

    def generate_wav(
        self,
        text: str,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        language: str = "English",
    ):
        wav, sr = self.model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_clone_prompt_items,
        )

        return wav[0], sr

    def generate_wav_batched(
        self,
        text: List,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        speaker_name: str,
        batch_size: int = 10,
        language: str = "English",
    ) -> List[str]:
        """Generates wav files in a batched fashion from cloned voice and returns an array of paths containing the generated wav files' locations.

        Args:
            text (List): _description_
            voice_clone_prompt_items (List[VoiceClonePromptItem]): _description_
            speaker_name (str): _description_
            batch_size (int, optional): _description_. Defaults to 10.
            language (str, optional): _description_. Defaults to "English".

        Returns:
            List[str]: _description_
        """
        folder_path = f"{self.temp_file_location}/{speaker_name}"

        # delete folder if it exists
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        # create temp wav storage folder for speaker
        os.makedirs(folder_path, exist_ok=True)

        batch_clip_paths = []

        for text_index in range(0, len(text), batch_size):
            batch_text = text[text_index : text_index + batch_size]
            batch_clip_paths.append(
                self._generate_current_batch(
                    text_arr=batch_text,
                    voice_clone_prompt_items=voice_clone_prompt_items,
                    language=language,
                    index_begin=text_index,
                    speaker_name=speaker_name,
                )
            )

        torch.cuda.empty_cache()
        return batch_clip_paths

    def _generate_current_batch(
        self,
        text_arr: List,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        speaker_name: str,
        index_begin: int,
        language: str = "English",
    ):
        t1 = time.time()
        with torch.no_grad():
            wavs, sr = self.model.generate_voice_clone(
                text=text_arr,
                language=language,
                voice_clone_prompt=voice_clone_prompt_items,
            )
        print(f"generated batch starting index:{index_begin}")
        print(f"batch took {time.time()-t1}")
        return self._save_temp_wavs_(
            wavs=wavs, sr=sr, speaker_name=speaker_name, index_begin=index_begin
        )

    def _save_temp_wavs_(
        self, wavs: list, sr: int, speaker_name: str, index_begin: int
    ) -> List[str]:
        """Saves the list of numpy array's as wav files sequentially and returns the file paths as a string array

        Args:
            wavs (list): List of numpy arrays that consist of cloned voice snippets
            sr (int): Generated audio sample rate
            speaker_name (str): Speakers name to be used to save the file
            index_begin (int): Index to use for individual audio clips. Mostly intended to be used as an offset

        Returns:
            List[str]: List of paths for the saved audio clips
        """

        paths_of_saved_wavs = []

        for i, wav in enumerate(wavs):
            path = f"{self.temp_file_location}/{speaker_name}/{i+index_begin}.wav"

            sf.write(path, wav, sr)

            paths_of_saved_wavs.append(path)

        return paths_of_saved_wavs

    def get_batch_process(self):
        pass
