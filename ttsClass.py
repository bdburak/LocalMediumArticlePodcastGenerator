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

        if os.environ.get("TTS_COMPILE", "1") != "0":
            try:
                t_compile = time.perf_counter()
                self.model.model = torch.compile(self.model.model, mode="reduce-overhead")
                compile_time = time.perf_counter() - t_compile
                print(f"[PERF] torch.compile succeeded ({compile_time:.1f}s)")
            except Exception as e:
                print(f"[PERF] torch.compile failed: {e}")

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

    def _gpu_mem_str(self):
        if not torch.cuda.is_available():
            return "mem=N/A"
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"mem_alloc={alloc:.1f}GB mem_res={reserved:.1f}GB"

    @staticmethod
    def _get_safe_batch_size(requested: int) -> int:
        if not torch.cuda.is_available():
            return requested
        env_val = os.environ.get("TTS_BATCH_SIZE")
        if env_val:
            requested = int(env_val)
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        baseline_gb = torch.cuda.memory_reserved() / 1024**3
        usable_gb = (total_gb - max(baseline_gb, 0.5)) * 0.85
        safe = max(1, int(usable_gb / 0.86))
        capped = min(requested, safe)
        if capped < requested:
            print(f"[PERF] batch_size capped {requested} → {capped} (GPU={total_gb:.0f}GB usable={usable_gb:.1f}GB)")
        return capped

    def generate_wav_batched(
        self,
        text: List,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        speaker_name: str,
        batch_size: int = 10,
        language: str = "English",
    ) -> List[str]:
        batch_size = self._get_safe_batch_size(batch_size)
        t_total = time.perf_counter()
        total_batches = (len(text) + batch_size - 1) // batch_size
        print(f"[PERF] speaker={speaker_name} start lines={len(text)} batches={total_batches} batch_size={batch_size}")

        folder_path = f"{self.temp_file_location}/{speaker_name}"

        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        os.makedirs(folder_path, exist_ok=True)

        batch_clip_paths = []
        batch_idx = 0

        for text_index in range(0, len(text), batch_size):
            batch_text = text[text_index : text_index + batch_size]
            batch_clip_paths.append(
                self._generate_current_batch(
                    text_arr=batch_text,
                    voice_clone_prompt_items=voice_clone_prompt_items,
                    language=language,
                    index_begin=text_index,
                    speaker_name=speaker_name,
                    batch_idx=batch_idx,
                    total_batches=total_batches,
                )
            )
            batch_idx += 1

        t_cache = time.perf_counter()
        torch.cuda.empty_cache()
        cache_ms = (time.perf_counter() - t_cache) * 1000

        elapsed = time.perf_counter() - t_total
        avg_per_batch = elapsed / total_batches if total_batches else 0
        print(f"[PERF] speaker={speaker_name} DONE total={elapsed:.1f}s batches={total_batches} lines={len(text)} avg/batch={avg_per_batch:.1f}s cache_flush={cache_ms:.0f}ms {self._gpu_mem_str()}")
        return batch_clip_paths

    def _generate_current_batch(
        self,
        text_arr: List,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        speaker_name: str,
        index_begin: int,
        batch_idx: int = 0,
        total_batches: int = 1,
        language: str = "English",
    ):
        t1 = time.perf_counter()
        with torch.no_grad():
            wavs, sr = self.model.generate_voice_clone(
                text=text_arr,
                language=language,
                voice_clone_prompt=voice_clone_prompt_items,
            )
        infer_time = time.perf_counter() - t1

        t_save = time.perf_counter()
        result = self._save_temp_wavs_(
            wavs=wavs, sr=sr, speaker_name=speaker_name, index_begin=index_begin
        )
        save_time = time.perf_counter() - t_save

        total_wav_secs = sum(len(w) / sr for w in wavs)
        print(
            f"[PERF] speaker={speaker_name} batch={batch_idx}/{total_batches} "
            f"items={len(text_arr)} range=[{index_begin}:{index_begin+len(text_arr)}] "
            f"infer={infer_time:.1f}s save={save_time:.2f}s "
            f"audio={total_wav_secs:.1f}s {self._gpu_mem_str()}"
        )
        return result

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
