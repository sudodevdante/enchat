#!/usr/bin/env bash
set -e

# 1) Determine installation directory
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

# 2) Ensure Python3 & pip3 are available
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

# 3) Try venv, fallback if not available
VENV_DIR="$ENCHAT_DIR/venv"
USE_VENV=false
if python3 -m venv --help &>/dev/null; then
  # Test create temporary venv to verify ensurepip
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
  echo "⚠️  Virtualenv not available – installing dependencies to user site"
  pip3 install --user requests colorama cryptography
fi

# 4) Create enhanced launcher with wipe functionality in ~/bin
LAUNCHER="$HOME/bin/enchat"
mkdir -p "$HOME/bin"
cat > "$LAUNCHER" <<EOF
#!/bin/bash

wipe() {
    echo "== ENCHAT ZERO-TRACE CLEANER =="
    # 1. Clear terminal scrollback
    printf '\033[3J\033c\033[H'
    clear

    # 2. Securely remove .enchat.conf if present
    CONF="\$HOME/.enchat.conf"
    if [ -f "\$CONF" ]; then
        if command -v shred &>/dev/null; then
            shred -u "\$CONF"
        else
            rm -f "\$CONF"
        fi
        echo "Enchat config wiped."
    fi

    # 3. Remove Enchat lines from shell histories
    for HIST in "\$HOME/.bash_history" "\$HOME/.zsh_history"; do
        [ -f "\$HIST" ] && grep -v 'enchat' "\$HIST" > "\$HIST.tmp" && mv "\$HIST.tmp" "\$HIST"
    done

    # 4. Clear current session history
    history -c 2>/dev/null

    echo "All Enchat traces wiped. Ready for next use."
}

case "\$1" in
    wipe)
        wipe
        ;;
    *)
        cd "$ENCHAT_DIR"
EOF

if $USE_VENV; then
  cat >> "$LAUNCHER" <<EOF
        source "$VENV_DIR/bin/activate"
        python3 enchat.py "\$@"
        ;;
esac
EOF
else
  cat >> "$LAUNCHER" <<EOF
        python3 enchat.py "\$@"
        ;;
esac
EOF
fi

chmod +x "$LAUNCHER"

# 5) Add ~/bin to PATH if needed
if ! echo ":$PATH:" | grep -q ":$HOME/bin:"; then
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
  export PATH="$HOME/bin:$PATH"
  echo "🔄 Added \$HOME/bin to PATH; run 'source ~/.bashrc' or restart your shell."
fi

echo
echo "✅ Installation complete!"
echo "▶️  Start chat: enchat"
echo "▶️  Wipe traces: enchat wipe"