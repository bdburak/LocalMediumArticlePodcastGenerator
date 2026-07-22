import torch
from typing import List
import soundfile as sf
from faster_qwen3_tts import FasterQwen3TTS
import os
import shutil
from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
import time


class TTS:

    def __init__(
        self,
        temp_file_location="./LOG_temp_test",
    ) -> None:

        self.temp_file_location = temp_file_location

        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        print("[PERF] TF32 + cuDNN benchmark enabled")

        self.model = FasterQwen3TTS.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            device="cuda",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )

    def warmup(self):
        t_warm = time.perf_counter()
        self.model.warmup(prefill_len=100)
        print(f"[PERF] CUDA graph warmup complete ({time.perf_counter() - t_warm:.1f}s)")

    def create_voice_clone_prompt_items(
        self, reference_audio_path: str, reference_text: str = ""
    ) -> List[VoiceClonePromptItem]:

        if reference_text != "" and reference_text is not None:
            print("using reference audio")
            return self.model.model.create_voice_clone_prompt(
                ref_audio=reference_audio_path,
                ref_text=reference_text,
            )
        print("not using reference audio")
        return self.model.model.create_voice_clone_prompt(
            ref_audio=reference_audio_path, x_vector_only_mode=True
        )

    def generate_wav(
        self,
        text: str,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        language: str = "English",
    ):
        audio_list, sr = self.model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_clone_prompt_items,
        )
        return audio_list[0], sr

    def _gpu_mem_str(self):
        if not torch.cuda.is_available():
            return "mem=N/A"
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"mem_alloc={alloc:.1f}GB mem_res={reserved:.1f}GB"

    def generate_wav_batched(
        self,
        text: List,
        voice_clone_prompt_items: List[VoiceClonePromptItem],
        speaker_name: str,
        batch_size: int = 1,
        language: str = "English",
    ) -> List[List[str]]:
        """Generates wav files line by line using CUDA-graph accelerated inference.

        Returns list of lists matching the original batched interface.
        Each inner list contains file paths for one 'batch' (one line).
        """
        t_total = time.perf_counter()
        total_lines = len(text)
        print(f"[PERF] speaker={speaker_name} start lines={total_lines}")

        folder_path = f"{self.temp_file_location}/{speaker_name}"

        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        os.makedirs(folder_path, exist_ok=True)

        batch_clip_paths = []

        for i, line_text in enumerate(text):
            t1 = time.perf_counter()
            audio_list, sr = self.model.generate_voice_clone(
                text=line_text,
                language=language,
                voice_clone_prompt=voice_clone_prompt_items,
            )
            infer_time = time.perf_counter() - t1

            wav = audio_list[0]
            path = f"{self.temp_file_location}/{speaker_name}/{i}.wav"
            sf.write(path, wav, sr)
            save_time = time.perf_counter() - t1 - infer_time

            audio_secs = len(wav) / sr
            print(
                f"[PERF] speaker={speaker_name} line={i+1}/{total_lines} "
                f"infer={infer_time:.1f}s save={save_time:.3f}s "
                f"audio={audio_secs:.1f}s speedup={audio_secs/infer_time:.1f}x "
                f"{self._gpu_mem_str()}"
            )

            batch_clip_paths.append([path])

        elapsed = time.perf_counter() - t_total
        total_audio = sum(len(sf.read(p)[0]) / sr for paths in batch_clip_paths for p in paths)

        torch.cuda.empty_cache()

        print(
            f"[PERF] speaker={speaker_name} DONE "
            f"total={elapsed:.1f}s lines={total_lines} "
            f"audio={total_audio:.1f}s avg/line={elapsed/total_lines:.1f}s "
            f"speedup={total_audio/elapsed:.1f}x {self._gpu_mem_str()}"
        )
        return batch_clip_paths

    def get_batch_process(self):
        pass
