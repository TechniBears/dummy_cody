#!/usr/bin/env bash
# Base provisioner for the Agent Cody Gateway AMI.
# Installs: Node 22, ffmpeg, Docker, Piper TTS (pip), whisper-ctranslate2 (pip),
# English + Arabic Piper voices, distil-large-v3 Whisper model pre-pulled.
#
# Supply-chain hardening:
# - Node + Docker: apt repo with GPG key (no curl|bash)
# - Piper + whisper-ctranslate2: pip-installed into dedicated venvs, versions pinned
# - Piper voices: downloaded from HuggingFace, SHAs logged to /opt/piper/voices.sha256 for audit
#   (Phase 4 will verify against pinned SHAs; for MVP we record-and-move)
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# ============================================================
# Base packages + hardening
# ============================================================
apt-get update
apt-get upgrade -y
apt-get install -y \
  unattended-upgrades \
  fail2ban \
  auditd \
  curl \
  ca-certificates \
  gnupg \
  software-properties-common \
  build-essential \
  python3.12 \
  python3.12-venv \
  python3-pip \
  python3-boto3 \
  pipx \
  jq \
  git \
  tmux \
  htop \
  ffmpeg \
  unzip \
  openjdk-21-jre-headless \
  xfce4 \
  xfce4-goodies \
  xrdp
dpkg-reconfigure --priority=low unattended-upgrades

# Configure xrdp and xfce4
systemctl enable xrdp
systemctl start xrdp
usermod -a -G ssl-cert ubuntu
echo "xfce4-session" > /home/ubuntu/.xsession
chown ubuntu:ubuntu /home/ubuntu/.xsession


# ============================================================
# Node.js 22 via NodeSource (keyring-based, no curl|bash)
# ============================================================
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  -o /etc/apt/keyrings/nodesource.asc
chmod a+r /etc/apt/keyrings/nodesource.asc
echo "deb [signed-by=/etc/apt/keyrings/nodesource.asc] https://deb.nodesource.com/node_22.x nodistro main" \
  > /etc/apt/sources.list.d/nodesource.list
apt-get update
apt-get install -y nodejs
node --version
npm --version

# ============================================================
# Docker Engine (for skill sandboxes in Phase 1-4)
# ============================================================
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# ============================================================
# AWS CLI v2 (via snap, since apt dropped awscli in 24.04)
# ============================================================
snap install aws-cli --classic
ln -sf /snap/bin/aws /usr/local/bin/aws
aws --version

# ============================================================
# Piper TTS — pip install into dedicated venv, English + Arabic voices
# ============================================================
python3.12 -m venv /opt/piper-venv
# piper-tts==1.4.1 has undeclared dep on pathvalidate; install explicitly
/opt/piper-venv/bin/pip install --no-cache-dir "piper-tts==1.4.1" "pathvalidate>=3.0"
# Wrapper shim so `piper` on PATH resolves to python -m piper (avoids broken script entrypoint)
cat > /usr/local/bin/piper <<'PIPER_WRAPPER'
#!/usr/bin/env bash
exec /opt/piper-venv/bin/python -m piper "$@"
PIPER_WRAPPER
chmod +x /usr/local/bin/piper
piper --help 2>&1 | head -3 || echo "piper wrapper ready"

mkdir -p /opt/piper/voices
# English voice
curl -fsSL -o /opt/piper/voices/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -fsSL -o /opt/piper/voices/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Arabic voice (Jordan — default Arabic voice in the rhasspy/piper-voices repo)
curl -fsSL -o /opt/piper/voices/ar_JO-kareem-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx \
  || echo "Arabic voice download failed; continuing — text-fallback will cover"
curl -fsSL -o /opt/piper/voices/ar_JO-kareem-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json \
  || true

# Record SHAs for future pinning
cd /opt/piper/voices
sha256sum *.onnx > voices.sha256 2>/dev/null || true
cat voices.sha256 || true
cd -

# ============================================================
# NVIDIA driver 570 + CUDA 12.6 runtime libraries + cuDNN 9
# Runtime libraries only (not the full cuda-toolkit which includes nvcc) —
# ctranslate2 4.x only needs libcudart + libcublas + libcublasLt (all in
# cuda-libraries-12-6) plus cuDNN 9.
#
# Notes from NVIDIA repo verification + first builds:
#   - Ubuntu 24.04 noble NVIDIA CUDA repo only ships CUDA >= 12.5. CUDA 12.4
#     is not available here. We pin to 12.6 (stable, production-grade,
#     ctranslate2 wheels ABI-compatible within 12.x).
#   - Driver package in NVIDIA's CUDA repo is "cuda-drivers-NNN" (not the
#     Ubuntu-universe "nvidia-driver-NNN-server" naming).
#   - Driver 550 (550.163.01 latest) fails DKMS build against kernel
#     6.17.0-1010-aws which apt-get upgrade pulls in on a fresh noble AMI.
#     Driver 570 branch supports newer kernels; pinned there for headroom.
#   - cuDNN is NOT in the CUDA repo at all. Added via a separate local-installer
#     .deb that registers its own apt source.
#
# Assumes a GPU-equipped Packer builder (g4dn.xlarge); nvidia-smi runs at the
# end and fails the build if the driver can't load against a real GPU.
# ============================================================
# CUDA repo (drivers + cuda-libraries-*)
curl -fsSL "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb" \
  -o /tmp/cuda-keyring.deb
dpkg -i /tmp/cuda-keyring.deb
rm /tmp/cuda-keyring.deb

# cuDNN 9.7.1 local-installer (registers its own apt source)
CUDNN_VER="9.7.1"
curl -fsSL "https://developer.download.nvidia.com/compute/cudnn/${CUDNN_VER}/local_installers/cudnn-local-repo-ubuntu2404-${CUDNN_VER}_1.0-1_amd64.deb" \
  -o /tmp/cudnn-local.deb
dpkg -i /tmp/cudnn-local.deb
cp /var/cudnn-local-repo-ubuntu2404-${CUDNN_VER}/cudnn-*-keyring.gpg /usr/share/keyrings/
rm /tmp/cudnn-local.deb

apt-get update
apt-get install -y \
  cuda-drivers-570 \
  cuda-libraries-12-6 \
  cudnn9-cuda-12

# Load kernel module + verify GPU visible. Fails the build on any error.
modprobe nvidia
nvidia-smi

# ============================================================
# whisper-ctranslate2 (faster-whisper's CLI) — pip install into dedicated venv
# ============================================================
python3.12 -m venv /opt/whisper-venv
/opt/whisper-venv/bin/pip install --no-cache-dir \
  "faster-whisper==1.1.0" \
  "whisper-ctranslate2==0.4.4" \
  "requests>=2.32"
ln -sf /opt/whisper-venv/bin/whisper-ctranslate2 /usr/local/bin/whisper-ctranslate2

# Pre-pull distil-large-v3 model so first user voice-note doesn't wait for model download.
# Model ~1.5GB; caches to ~/.cache/huggingface; move cache to /opt for the service user.
export HF_HOME=/opt/whisper-cache
mkdir -p /opt/whisper-cache
/opt/whisper-venv/bin/python -c "
from faster_whisper import WhisperModel
import os
os.environ.setdefault('HF_HOME', '/opt/whisper-cache')
# Multilingual model — Arabic + English + 100 other langs
model = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16', download_root='/opt/whisper-cache')
print('large-v3-turbo cached to /opt/whisper-cache')
"

# ============================================================
# Ollama — install binary + pre-pull Gemma 4 26B (MoE, fits T4 16GB)
# Installed to /opt/ollama so it survives between sessions.
# ============================================================
OLLAMA_VERSION=$(curl -fsSL https://api.github.com/repos/ollama/ollama/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
curl -fsSL "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tgz" \
  -o /tmp/ollama.tgz
mkdir -p /opt/ollama
tar -xz -C /opt/ollama -f /tmp/ollama.tgz
rm /tmp/ollama.tgz
ln -sf /opt/ollama/bin/ollama /usr/local/bin/ollama
ollama --version

# Create ollama systemd service
cat > /etc/systemd/system/ollama.service <<'OLLAMA_SVC'
[Unit]
Description=Ollama local LLM server
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/opt/ollama/bin/ollama serve
Environment=OLLAMA_MODELS=/opt/ollama/models
Environment=HOME=/opt/ollama
Environment=OLLAMA_HOST=127.0.0.1:11434
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
OLLAMA_SVC

systemctl daemon-reload
systemctl enable ollama
systemctl start ollama
sleep 5

# Pre-pull Gemma 4 26B (MoE — only 4B active params at inference, fits in T4 16GB)
mkdir -p /opt/ollama/models
OLLAMA_MODELS=/opt/ollama/models OLLAMA_HOST=127.0.0.1:11434 ollama pull gemma4:26b
echo "Gemma 4 26B pulled to /opt/ollama/models"

# ============================================================
# System directories for OpenClaw
# ============================================================
mkdir -p /opt/openclaw /opt/openclaw/workspace /var/log/openclaw /creds
chmod 700 /creds

# Service user for OpenClaw (non-root, no login shell)
useradd --system --home /opt/openclaw --shell /usr/sbin/nologin openclaw || true
usermod -aG docker openclaw || true  # allow Docker-sandbox skill invocations
chown -R openclaw:openclaw /opt/openclaw /var/log/openclaw /opt/piper-venv /opt/piper /opt/whisper-venv /opt/whisper-cache

# ============================================================
# Final: verify tooling is on PATH for openclaw user
# ============================================================
runuser -l openclaw -s /bin/bash -c 'which node npm ffmpeg piper whisper-ctranslate2 aws' || \
  echo "note: some binaries may need PATH adjustment"

# ============================================================
# GPU smoke — full transcribe on CUDA to validate the whole stack.
# Catches R1 (driver/CUDA/cuDNN mismatch), R2 (driver load), R14 (ABI break)
# at build time instead of after prod cutover.
# ============================================================
ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 1 -q:a 0 -y /tmp/smoke.wav
sudo -u openclaw -H /opt/whisper-venv/bin/python - <<'PY'
from faster_whisper import WhisperModel
m = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16', download_root='/opt/whisper-cache')
segs, info = m.transcribe('/tmp/smoke.wav', vad_filter=False)
list(segs)  # force generator so CUDA path actually executes
print('GPU smoke OK; detected_lang=', info.language, 'prob=', info.language_probability)
PY
rm -f /tmp/smoke.wav

echo "===== install-base.sh complete ====="
