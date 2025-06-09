#!/bin/bash

# Kleuren
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
mkdir -p "$INSTDIR"
cd "$INSTDIR" || exit 1

# 2. Check op python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 is niet gevonden! Installeer Python 3 eerst en start opnieuw.${RESET}"
    exit 1
fi

# 3. Vraag of gebruiker venv wil (aanrader)
echo
read -rp "Wil je een virtuele omgeving (venv) gebruiken? (aanrader) [Y/n]: " USEVENV
USEVENV="${USEVENV:-Y}"

if [[ "$USEVENV" =~ ^[Yy]$ ]]; then
    # 4. Maak en activeer venv
    python3 -m venv venv
    source venv/bin/activate
    PIP="pip"
    PYTHON="python"
else
    PIP="pip3"
    PYTHON="python3"
fi

# 5. Controleer/installeer pip
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "${YELLOW}pip wordt geïnstalleerd...${RESET}"
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON get-pip.py --user
    rm get-pip.py
fi

# 6. Installeer dependencies
echo -e "${GREEN}Dependencies installeren...${RESET}"
$PIP install --upgrade pip
$PIP install requests colorama cryptography

# 7. Download of kopieer het enchat.py script
read -rp "Wil je het script downloaden van GitHub of lokaal toevoegen? [download/lokaal]: " DL
DL="${DL:-download}"
if [[ "$DL" =~ ^[Dd] ]]; then
    # Voorbeeld (vervang url door jouw repo, of bewaar lokaal)
    curl -fsSL -o enchat.py https://gist.githubusercontent.com/salarvk/7e66df9c0f08db1e6b6ba8a955d684cf/raw/enchat.py
    echo -e "${GREEN}enchat.py is gedownload!${RESET}"
else
    read -rp "Voer het pad naar jouw lokale enchat.py in: " LOKAAL
    cp "$LOKAAL" ./enchat.py
    echo -e "${GREEN}Script gekopieerd!${RESET}"
fi

chmod +x enchat.py

# 8. (Optioneel) Maak een snelstart commando aan
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
    echo -e "${GREEN}Nu kun je starten met: 'enchat'${RESET}"
else
    echo -e "${YELLOW}Start je chat in de map met:${RESET} ${CYAN}$PYTHON enchat.py${RESET}"
    [[ "$USEVENV" =~ ^[Yy]$ ]] && echo -e "${YELLOW}... nadat je eerst doet:${RESET} ${CYAN}source venv/bin/activate${RESET}"
fi

echo
echo -e "${GREEN}Enchat installatie klaar! Veel plezier 🚀${RESET}"


