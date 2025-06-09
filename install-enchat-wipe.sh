#!/bin/bash

# == Setup: enchat wipe integration ==
CMD_DIR="$HOME/bin"
CMD_FILE="$CMD_DIR/enchat"

mkdir -p "$CMD_DIR"

cat > "$CMD_FILE" <<'EOF'
#!/bin/bash

wipe() {
    echo "== ENCHAT ZERO-TRACE CLEANER =="
    # 1. Clear terminal scrollback
    printf '\033[3J\033c\033[H'
    clear

    # 2. Securely remove .enchat.conf if present
    CONF="$HOME/.enchat.conf"
    if [ -f "$CONF" ]; then
        if command -v shred &>/dev/null; then
            shred -u "$CONF"
        else
            rm -f "$CONF"
        fi
        echo "Enchat config wiped."
    fi

    # 3. Remove Enchat lines from shell histories
    for HIST in "$HOME/.bash_history" "$HOME/.zsh_history"; do
        [ -f "$HIST" ] && grep -v 'enchat' "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
    done

    # 4. Clear current session history
    history -c 2>/dev/null

    echo "All Enchat traces wiped. Ready for next use."
}

case "$1" in
    wipe)
        wipe
        ;;
    *)
        # Start enchat.py from your install location
        # <--- Replace the path below with the real path to your enchat.py if needed --->
        ENCHAT_PY="$HOME/enchat/enchat.py"
        if [ -f "$ENCHAT_PY" ]; then
            if [ -d "$HOME/enchat/venv" ]; then
                source "$HOME/enchat/venv/bin/activate"
                python "$ENCHAT_PY" "${@:1}"
            else
                python3 "$ENCHAT_PY" "${@:1}"
            fi
        else
            echo "Cannot find enchat.py in $ENCHAT_PY"
            exit 1
        fi
        ;;
esac
EOF

chmod +x "$CMD_FILE"

# Add $HOME/bin to PATH if needed
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo
    echo "Your \$HOME/bin is not in your \$PATH. Adding it for you (bash/zsh)..."
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.zshrc"
    export PATH="$HOME/bin:$PATH"
    echo "Please restart your terminal, or run: export PATH=\"$HOME/bin:\$PATH\""
fi

echo
echo "✅ Done! From now on, use:"
echo "   enchat           # to start Enchat"
echo "   enchat wipe      # to wipe all traces"
echo

