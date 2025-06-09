#!/bin/bash

GREEN='\033[1;32m'
CYAN='\033[1;36m'
RED='\033[1;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

echo -e "${CYAN}Welkom bij de Enchat installer!${RESET}"
echo

# 1. Vraag installatiemap
read -rp "Waar wil je Enchat installeren? [Default: \$HOME/enchat] " INSTDIR
INSTDIR="${INSTDIR:-$HOME/enchat}"
if [[ -d "$INSTDIR/.git" ]]; then
    echo -e "${YELLOW}De map $INSTDIR lijkt al een git-repo te bevatten.${RESET}"
    read -rp "Wil je deze opnieuw clonen? [y/N]: " OVERWRITE
    OVERWRITE="${OVERWRITE:-N}"
    if [[ "$OVERWRITE" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTDIR"
    fi
fi
mkdir -p "$INSTDIR"
cd "$INSTDIR" || exit 1

# 2. Check op git
if ! command -v git &>/dev/null; then
    echo -e "${RED}Git is niet gevonden! Installeer git en start opnieuw.${RESET}"
    exit 1
fi

# 3. Repo clonen
echo -e "${GREEN}Cloning repo van GitHub...${RESET}"
git clone git@github.com:sudodevdante/enchat.git . || {
    echo -e "${RED}Kon repo niet clonen. Heb je SSH-toegang tot GitHub?${RESET}"
    exit 1
}

# 4. Check op python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 is niet gevonden! Installeer Python 3 en start opnieuw.${RESET}"
    exit 1
fi

# 5. Vraag of gebruiker venv wil (aanrader)
echo
read -rp "Wil je een virtuele omgeving (venv) gebruiken? (aanrader) [Y/n]: " USEVENV
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

# 6. Installeer pip indien nodig
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "${YELLOW}pip wordt geïnstalleerd...${RESET}"
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON get-pip.py --user
    rm get-pip.py
fi

# 7. Installeer dependencies
if [[ -f requirements.txt ]]; then
    echo -e "${GREEN}Dependencies installeren uit requirements.txt...${RESET}"
    $PIP install --upgrade pip
    $PIP install -r requirements.txt
else
    echo -e "${YELLOW}Geen requirements.txt gevonden, probeer standaard deps...${RESET}"
    $PIP install --upgrade pip
    $PIP install requests colorama cryptography
fi

# 8. Zorg dat script uitvoerbaar is
if [[ -f enchat.py ]]; then
    chmod +x enchat.py
fi

# 9. (Optioneel) Maak een snelstart-commando
read -rp "Wil je 'enchat' direct vanaf elke locatie kunnen starten? [y/N]: " BIN
BIN="${BIN:-N}"
if [[ "$BIN" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/bin"
    echo "#!/bin/bash" > "$HOME/bin/enchat"
    if [[ "$USEVENV" =~ ^[Yy]$ ]]; then
        echo "cd \"$INSTDIR\" && source venv/bin/activate && python enchat.py \"\$@\"" >> "$HOME/bin/enchat"
    else
        echo "cd \"$INSTDIR\" && python3 enchat.py \"\$@\"" >> "$HOME/bin/enchat"
    fi
    chmod +x "$HOME/bin/enchat"
    if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
        echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$HOME/.bashrc"
        echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$HOME/.zshrc"
        export PATH="$HOME/bin:$PATH"
    fi
    echo -e "${GREEN}Nu kun je altijd starten met: 'enchat'${RESET}"
else
    echo -e "${YELLOW}Start je chat in de map met:${RESET} ${CYAN}$PYTHON enchat.py${RESET}"
    [[ "$USEVENV" =~ ^[Yy]$ ]] && echo -e "${YELLOW}... nadat je eerst doet:${RESET} ${CYAN}source venv/bin/activate${RESET}"
fi

echo
echo -e "${GREEN}Enchat installatie klaar! Veel plezier 🚀${RESET}"

