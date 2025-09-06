#!/usr/bin/env bash
set -ex
# 1) deps
apt-get update && apt-get install -y wget tar
# 2) zrok
ZROK_VER=1.1.3
wget -qO- https://github.com/openziti/zrok/releases/download/v${ZROK_VER}/zrok_${ZROK_VER}_linux_amd64.tar.gz \
  | tar -xz -C /usr/local/bin
chmod +x /usr/local/bin/zrok
# 3) node deps
npm install
