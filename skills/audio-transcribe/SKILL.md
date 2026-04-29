---
name: audio-transcribe
description: Transcribe an audio file using the local Whisper model (whisper-ctranslate2).
metadata: {"openclaw":{"emoji":"🎙️","os":["linux"],"requires":{"bins":["whisper-ctranslate2"]}}}
---

# audio-transcribe

Transcribe audio files into text locally on the gateway using `whisper-ctranslate2`. This uses a fast, highly optimized Whisper implementation and does not require an API key or an external service. 

## Inputs you need before running

- The path to the audio file to transcribe (e.g., an `.ogg` or `.wav` file).

## Flow

1. Determine the path to the audio file.
2. Run `whisper-ctranslate2` on the file.

```bash
# Basic transcription
whisper-ctranslate2 "/path/to/audio/file" --model_dir /opt/whisper-cache --output_dir /tmp --output_format txt

# Once finished, you can read the output text file:
cat "/tmp/file.txt"
```

## Notes

- ALWAYS use `whisper-ctranslate2` instead of `openai-whisper` or `faster-whisper-cli`.
- The gateway has a pre-cached model at `/opt/whisper-cache`. You can also specify `--model large-v3-turbo` if needed, but it should default correctly or be available in cache.
- The binary is pre-installed on the gateway and is fully supported under the OpenClaw exec policy.
- DO NOT attempt to install it via `brew` or `pip`. It is already available at `/usr/local/bin/whisper-ctranslate2`.
- DO NOT use the `openai-whisper-api` system skill or any other external API. We do this entirely locally for privacy and cost reasons.
