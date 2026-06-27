import numpy as np


def combine_wavs_interleaved(title_wav, speaker_a, speaker_b, sr, silence_duration=0.5):
    """
    Combine podcast dialog audio with title intro.

    Args:
        title_wav: Single audio array for the title/intro
        speaker_a: List of numpy arrays (Host_A lines)
        speaker_b: List of numpy arrays (Host_B lines)
        sr: Sample rate
        silence_duration: Seconds of silence between segments
    """

    silence = np.zeros(int(sr * silence_duration))
    segments = [title_wav, silence]

    # Interleave while both have lines
    min_len = min(len(speaker_a), len(speaker_b))

    for i in range(min_len):
        segments.extend([speaker_a[i], silence, speaker_b[i], silence])

    # Append remaining lines from longer list (usually Host_A closing)
    if len(speaker_a) > len(speaker_b):
        for i in range(min_len, len(speaker_a)):
            segments.extend([speaker_a[i], silence])
    elif len(speaker_b) > len(speaker_a):
        for i in range(min_len, len(speaker_b)):
            segments.extend([speaker_b[i], silence])

    return np.concatenate(segments)
