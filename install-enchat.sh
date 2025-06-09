#!/usr/bin/env bash
set -e

# 1) Bepaal installatiemap
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/enchat.py" ]]; then
  ENCHAT_DIR="$SCRIPT_DIR"
  echo "📁 Using existing Enchat directory: $ENCHAT_DIR"
else
  ENCHAT_DIR="$HOME/enchat"
  echo "📥 Cloning Enchat into $ENCHAT_DIR"
  git clone https://github.com/sudodevdante/enchat.git "$ENCHAT_DIR"
fi

cd "$ENCHAT_DIR"

# 2) Zorg voor Python3 & pip3
install_pkg() {
  PKGS="$*"
  if   command -v apt   &>/dev/null; then sudo apt update && sudo apt install -y $PKGS
  elif command -v dnf   &>/dev/null; then sudo dnf install -y $PKGS
  elif command -v brew  &>/dev/null; then brew install $PKGS
  else echo "❌ No supported package manager for: $PKGS" >&2; exit 1
  fi
}

if ! command -v python3 &>/dev/null; then
  echo "🔧 Installing python3…"
  install_pkg python3
fi
if ! command -v pip3 &>/dev/null; then
  echo "🔧 Installing pip3…"
  install_pkg python3-pip
fi

# 3) Probeer venv, anders fallback
VENV_DIR="$ENCHAT_DIR/venv"
USE_VENV=false
if python3 -m venv --help &>/dev/null; then
  # test create temporal venv to verify ensurepip
  TMP_VENV="$ENCHAT_DIR/.tmpvenv"
  if python3 -m venv "$TMP_VENV" &>/dev/null; then
    rm -rf "$TMP_VENV"
    USE_VENV=true
  fi
fi

if $USE_VENV; then
  echo "🐍 Setting up virtualenv…"
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  echo "📦 Installing dependencies in venv…"
  pip install --upgrade pip
  pip install requests colorama cryptography
else
  echo "⚠️  Virtualenv not available – installing deps to user site"
  pip3 install --user requests colorama cryptography
fi

# 4) Maak launcher in ~/bin
LAUNCHER="$HOME/bin/enchat"
mkdir -p "$HOME/bin"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
cd "$ENCHAT_DIR"
EOF

if $USE_VENV; then
  cat >> "$LAUNCHER" <<EOF
source "$VENV_DIR/bin/activate"
python3 enchat.py "\$@"
EOF
else
  cat >> "$LAUNCHER" <<EOF
python3 enchat.py "\$@"
EOF
fi

chmod +x "$LAUNCHER"

# 5) Voeg ~/bin aan PATH toe indien nodig
if ! echo ":$PATH:" | grep -q ":$HOME/bin:"; then
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
  export PATH="$HOME/bin:$PATH"
  echo "🔄 Added \$HOME/bin to PATH; run 'source ~/.bashrc' of herstart je shell."
fi

echo
echo "✅ Installation complete!"
echo "▶️  Start met: enchat"
echo "▶️  Wipe traces met: enchat wipe  (als je dat script hebt geïnstalleerd)"