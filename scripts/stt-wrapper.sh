#!/usr/bin/env bash
# OpenClaw STT wrapper — called as: stt-wrapper.sh <input-audio-file>
# Contract per docs.openclaw.ai: file path in, transcript on stdout, exit 0 on success.
# whisper-ctranslate2 writes txt to a sidecar; we cat that to stdout, then clean up.
set -euo pipefail

in="$1"
out=$(mktemp -d -t codystt.XXXXXX)
trap 'rm -rf "$out"' EXIT

threads="${WHISPER_THREADS:-$(command -v nproc >/dev/null 2>&1 && nproc || echo 2)}"
device="${WHISPER_DEVICE:-auto}"
compute_type="${WHISPER_COMPUTE_TYPE:-auto}"
beam_size="${WHISPER_BEAM_SIZE:-1}"
language="${WHISPER_LANGUAGE:-}"

# Auto-detect: prefer GPU if NVIDIA driver responds, fall back to CPU.
# WHISPER_DEVICE=cuda|cpu forces a specific path; WHISPER_COMPUTE_TYPE overrides both.
if [[ "$device" == "auto" ]]; then
  if nvidia-smi >/dev/null 2>&1; then
    device="cuda"
    [[ "$compute_type" == "auto" ]] && compute_type="float16"
  else
    device="cpu"
    [[ "$compute_type" == "auto" ]] && compute_type="int8"
  fi
elif [[ "$compute_type" == "auto" ]]; then
  [[ "$device" == "cuda" ]] && compute_type="float16" || compute_type="int8"
fi

model_dir="${WHISPER_MODEL_DIR:-}"
if [[ -z "$model_dir" ]]; then
  for candidate in \
    /opt/whisper-cache/models--Systran--faster-whisper-medium/snapshots/* \
    /opt/whisper-cache/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/* \
    /opt/whisper-cache/models--mobiuslabsgmbh--faster-whisper-large-v3/snapshots/* \
    /opt/whisper-cache
  do
    if [[ -f "$candidate/model.bin" ]]; then
      model_dir="$candidate"
      break
    fi
  done
fi

if [[ -z "$model_dir" || ! -f "$model_dir/model.bin" ]]; then
  echo "stt-wrapper: no whisper model found under /opt/whisper-cache" >&2
  exit 2
fi

run_transcribe() {
  local dev="$1" ct="$2"
  local -a cmd=(
    /usr/local/bin/whisper-ctranslate2
    --model_directory "$model_dir"
    --device "$dev"
    --compute_type "$ct"
    --threads "$threads"
    --task transcribe
    --beam_size "$beam_size"
    --output_format txt
    --output_dir "$out"
    --verbose False
  )
  [[ -n "$language" ]] && cmd+=(--language "$language")
  cmd+=("$in")
  "${cmd[@]}" >/dev/null 2>/tmp/codystt.stderr
}

if ! run_transcribe "$device" "$compute_type"; then
  if [[ "$device" == "cuda" ]]; then
    echo "stt-wrapper: CUDA path failed, retrying on CPU" >&2
    cat /tmp/codystt.stderr >&2 2>/dev/null || true
    rm -f "$out"/*.txt 2>/dev/null || true
    if ! run_transcribe cpu int8; then
      cat /tmp/codystt.stderr >&2 2>/dev/null || true
      rm -f /tmp/codystt.stderr
      exit 4
    fi
  else
    cat /tmp/codystt.stderr >&2 2>/dev/null || true
    rm -f /tmp/codystt.stderr
    exit 4
  fi
fi
rm -f /tmp/codystt.stderr

# whisper-ctranslate2 names output as <input-basename>.txt in --output_dir.
txt_file=$(find "$out" -maxdepth 1 -name '*.txt' | head -1)
if [[ -z "$txt_file" ]]; then
  echo "stt-wrapper: whisper produced no transcript file" >&2
  exit 3
fi
cat "$txt_file"
