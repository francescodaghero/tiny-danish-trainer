"""
Parses the JSON files in data/ and generates a valid deck structure in output
"""

import json
import random
import os
import pathlib
import dataclasses
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import soundfile as sf
from huggingface_hub import snapshot_download
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
import torchaudio as ta


def audio_gen(language_path: str, output_path: str):
    # Pass over all files, generate audio for all translations and put them in the audio/ folder
    # Numbers
    with open(f"{language_path}/numbers.json", "r") as f:
        data = json.load(f)
    
    ## Ordinal
    for idx, item in enumerate(data["ordinal"]):
        translation = item[0]
        audio = generate_audio(translation, f"{output_path}/{item[0]}.mp3")
    
    ## Cardinal
    for idx, item in enumerate(data["cardinal"]):
        translation = item[0]
        audio = generate_audio(translation, f"{output_path}/{item[0]}.mp3")

    

def verbs_deckgen(language_path: str, output_path: str):
    # Just copy the file
    with open(f"{language_path}/verbs.json", "r") as f:
        data = json.load(f)
    with open(f"{output_path}/verbs.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def numbers_deckgen(language_path: str, output_path: str):
    # Just copy the file
    with open(f"{language_path}/numbers.json", "r") as f:
        data = json.load(f)
    with open(f"{output_path}/numbers.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def general_deckgen(language_path: str, output_path: str):
    # Just copy the file
    with open(f"{language_path}/adjectives.json", "r") as f:
        data_adj = json.load(f)

    # Merge with nouns
    with open(f"{language_path}/nouns.json", "r") as f:
        data_nouns = json.load(f)
    data = data_adj + data_nouns
    with open(f"{output_path}/deck.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    

class Model:
    def __init__(self):
        REPO_ID = "CoRal-project/roest-v3-chatterbox-500m"
        model_dir = snapshot_download(
            repo_id=REPO_ID,
            token=os.getenv("HF_TOKEN") or True,
            # Optional: Filter to download only what you need
            allow_patterns=["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"],
        )

        device = "cpu"
        self.model = ChatterboxMultilingualTTS.from_local(model_dir, device=device)

    def generate_audio(self, text: str):
        try:
            wav = self.model.generate(text, language_id="da")
        except Exception as e:
            print(f"Error generating audio for '{text}': {e}")
            with open("audio_generation_errors.log", "a") as log_file:
                log_file.write(f"Error generating audio for '{text}': {e}\n")
            return None
        return wav


def generate_audio(text: str, filename: str):
    """
    This requires huggingface
    CoRal-project/roest-v3-chatterbox-500m
    """

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if os.path.exists(filename):
        return filename
    wav = model.generate_audio(text)
    if wav is not None:
        ta.save(uri=filename, src=wav, sample_rate=model.model.sr)
        # Convert to mp3 mono, 16kHz
        return filename
    return ""


model = Model()
if __name__ == "__main__":
    os.makedirs("output/audio", exist_ok=True)
    os.makedirs("output/static", exist_ok=True)

    #audio_gen("deckgen/danish", "output/audio")
    verbs_deckgen("deckgen/danish", "output/static")
    numbers_deckgen("deckgen/danish", "output/static")
    general_deckgen("deckgen/danish", "output/static")
