#!/bin/bash

GREEN='\033[1;32m'
CYAN='\033[1;36m'
RED='\033[1;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

echo -e "${CYAN}Welcome to the Enchat installer!${RESET}"
echo

# 1. Ask for install directory
CURDIR=$(pwd)
read -rp "Where do you want to install Enchat? [Default: $CURDIR/enchat] " INSTDIR
INSTDIR="${INSTDIR:-$CURDIR/enchat}"

if [[ -d "$INSTDIR/.git" ]]; then
    echo -e "${YELLOW}Directory $INSTDIR already looks like a git repo.${RESET}"
    read -rp "Do you want to overwrite (reclone) it? [y/N]: " OVERWRITE
    OVERWRITE="${OVERWRITE:-N}"
    if [[ "$OVERWRITE" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTDIR"
    fi
fi
mkdir -p "$INSTDIR"
cd "$INSTDIR" || exit 1

# 2. Check for git
if ! command -v git &>/dev/null; then
    echo -e "${RED}Git is not installed! Please install git and try again.${RESET}"
    exit 1
fi

# 3. Clone the repo
echo -e "${GREEN}Cloning Enchat from GitHub...${RESET}"
git clone https://github.com/sudodevdante/enchat.git . || {
    echo -e "${RED}Could not clone the repo. Check your access rights or network.${RESET}"
    exit 1
}

# 4. Check for python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 is not installed! Please install Python 3 and try again.${RESET}"
    exit 1
fi

# 5. Ask if user wants a venv (recommended)
echo
read -rp "Use a Python virtual environment (venv)? [Y/n]: " USEVENV
USEVENV="${USEVENV:-Y}"

if [[ "$USEVENV" =~ ^[Yy]$ ]]; then
    python3 -m venv venv
    source venv/bin/activate
    PIP="pip"
    PYTHON="python"
else
    PIP="pip3"
    PYTHON="python3"
fi

# 6. Ensure pip is installed
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "${YELLOW}pip will be installed...${RESET}"
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON get-pip.py --user
    rm get-pip.py
fi

# 7. Install dependencies
if [[ -f requirements.txt ]]; then
    echo -e "${GREEN}Installing dependencies from requirements.txt...${RESET}"
    $PIP install --upgrade pip
    $PIP install -r requirements.txt
else
    echo -e "${YELLOW}No requirements.txt found, installing default deps...${RESET}"
    $PIP install --upgrade pip
    $PIP install requests colorama cryptography
fi

# 8. Make enchat.py executable
if [[ -f enchat.py ]]; then
    chmod +x enchat.py
fi

# 9. Write or update launcher to $HOME/bin/enchat
mkdir -p "$HOME/bin"
cat > "$HOME/bin/enchat" <<'LAUNCHER'
#!/bin/bash
CONFIG="$HOME/.enchat-path"

if [[ ! -f "$CONFIG" ]]; then
    echo "Enchat is not installed or .enchat-path is missing! Please run the installer script first."
    exit 1
fi

INSTDIR=$(cat "$CONFIG")

if [[ ! -d "$INSTDIR" ]]; then
    echo "The specified Enchat folder ($INSTDIR) does not exist!"
    exit 1
fi

cd "$INSTDIR"

# Use venv if it exists
if [[ -d venv ]]; then
    source venv/bin/activate
    PIP="pip"
    PYTHON="python"
else
    PIP="pip3"
    PYTHON="python3"
fi

# Auto-install dependencies if missing
for pkg in requests colorama cryptography; do
    $PYTHON -c "import $pkg" 2>/dev/null || $PIP install $pkg
done

# Wipe command
if [[ "$1" == "wipe" ]]; then
    printf '\033[3J\033c\033[H'
    clear
    CONF="$HOME/.enchat.conf"
    if [ -f "$CONF" ]; then
        if command -v shred &>/dev/null; then
            shred -u "$CONF"
        else
            rm -f "$CONF"
        fi
        echo "Enchat config wiped."
    fi
    for HIST in "$HOME/.bash_history" "$HOME/.zsh_history"; do
        [ -f "$HIST" ] && grep -v 'enchat' "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
    done
    history -c 2>/dev/null
    echo "All Enchat traces wiped. Ready for next use."
    exit 0
fi

$PYTHON enchat.py "${@:1}"
LAUNCHER
chmod +x "$HOME/bin/enchat"

# 10. Save the current install path in ~/.enchat-path
echo "$INSTDIR" > "$HOME/.enchat-path"

if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$HOME/.bashrc"
    echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$HOME/.zshrc"
    export PATH="$HOME/bin:$PATH"
    echo "Please open a new terminal or run: export PATH=\"\$HOME/bin:\$PATH\""
fi

echo
echo -e "${GREEN}You can now always start Enchat from anywhere using: 'enchat'${RESET}"
echo -e "${YELLOW}To wipe all traces after a session, use:${RESET} 'enchat wipe'"
echo
echo -e "${GREEN}Enchat installation complete! Enjoy 🚀${RESET}"
