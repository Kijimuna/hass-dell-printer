#!/bin/bash
set -e

echo "Start setup environment for HA 2026.3 explicitly ..."

# system dependencies
sudo apt-get update
sudo apt-get install -y ffmpeg libturbojpeg0-dev \
  pkg-config \
  libavformat-dev \
  libavcodec-dev \
  libavdevice-dev \
  libavutil-dev \
  libavfilter-dev \
  libswscale-dev \
  libswresample-dev

# python dependencies
# everything installed into the system path to avoid path conflicts ...
sudo python3 -m pip install --break-system-packages \
  homeassistant==2026.3.0 \
  home-assistant-frontend==20260304.0 \
  colorlog==6.10.1 \
  numpy \
  ha-av \
  ha-ffmpeg \
  PyTurboJPEG \
  Pillow \
  mutagen \
  pymicro_vad \
  webrtc-noise-gain \
  pyspeex-noise \
  hassil \
  home-assistant-intents \
  sqlalchemy \
  fnv-hash-fast \
  gtts \
  dell_printer_parser

# fix access (make vscode owner of the sudo-installes stuff) 
sudo chown -R vscode:vscode /usr/local/lib/python3.14/site-packages || true

# frontend-name-fix (hass_frontend versus home_assistant_frontend package mixup)
sudo ln -sf /usr/local/lib/python3.14/site-packages/hass_frontend /usr/local/lib/python3.14/site-packages/home_assistant_frontend

# # Remove onboardings step
# mkdir -p .storage
# if [ ! -f .storage/onboarding ]; then
#     echo '{"version":1,"minor_version":1,"key":"onboarding","data":{"done":["user","core_config","integration"]}}' > .storage/onboarding
#     echo "Configured Onboarding-Skip."
# fi

echo "-------------------------------------------------------"
echo "SETUP SUCCESSFUL! Start HA by:"
echo "hass -c . --skip-pip"
echo "-------------------------------------------------------"