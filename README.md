<div align="center">
  <img src="https://sudosallie.com/enchatlogo.png" alt="Enchat Logo" width="400">
</div>

# 🔐 Enchat - Encrypted Terminal Chat

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)

**Enchat** brings **military-grade encryption** directly to your terminal, enabling completely private conversations without corporate surveillance or data harvesting. Chat securely with colleagues, friends, or team members knowing that your messages are **cryptographically protected** and invisible to servers, governments, and eavesdroppers.

**Why Enchat?** Because your conversations deserve better than Big Tech's "encrypted" platforms that still profile you, track you, and own your data. Take back control with a tool that's **truly private by design** - no accounts, no tracking, no compromises.

## 🔒 Security & Encryption

### **How Your Messages Stay Safe**
- **End-to-end encryption** using Fernet (AES 128 in CBC mode + HMAC-SHA256)
- **Client-side encryption** - messages are encrypted before leaving your device
- **Server blindness** - ntfy servers only see encrypted blobs, never plaintext
- **Authenticated encryption** - prevents message tampering and ensures integrity
- **Key derivation** - SHA-256 hash of your passphrase generates encryption keys

### **Message Flow Security**
```
Your Message → [Encrypt] → Encrypted Blob → ntfy Server → Encrypted Blob → [Decrypt] → Recipient
```

The ntfy server acts as a **message relay only** - it cannot decrypt your messages without your passphrase. Even if the server is compromised, your conversations remain secure.

### **Privacy Guarantees**
- 🔐 **Zero knowledge** - servers never see message content
- 🎭 **Anonymous** - no accounts or personal information required
- 🧹 **Clean exit** - secure wipe removes all traces

## ✨ Features

- **Real-time encrypted chat** with timestamps and status indicators
- **Self-hosted ntfy support** for complete infrastructure control
- **Auto-reconnection** with smart retry logic
- **Desktop notifications** (Linux, macOS)
- **Command system** (`/help`, `/clear`, `/exit`)
- **Smart input handling** and message validation
- **Cross-platform** terminal support

## 🚀 Quick Start

### Installation

#### Automatic Installer (Recommended)
```bash
git clone https://github.com/sudodevdante/enchat.git
cd enchat
./install-enchat.sh
```

#### Manual Setup
```bash
git clone https://github.com/sudodevdante/enchat.git
cd enchat
pip install requests colorama cryptography
chmod +x enchat.py
```

### First Run

```bash
enchat
```

Setup interface:
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ENCRYPTED TERMINAL CHAT                           │
└─────────────────────────────────────────────────────────────────────────────┘

Welcome to Enchat! Let's set up your encrypted chat.

🏠 Room name (unique, secret): my-secret-room
👤 Your nickname: alice
🔐 Encryption passphrase (hidden): ••••••••
🌐 ntfy server URL (press Enter for default https://ntfy.sh): 
💾 Save settings for auto-reconnect? [Y/n]: y
```

### Chat Interface

```
┌─────────────────────────────────────────────────────────────────────────────┐
│🟢 my-secret-room | alice | ntfy.sh                                           │
└─────────────────────────────────────────────────────────────────────────────┘

[14:32:15] ℹ Joined room 'my-secret-room' • Type /exit to quit, /clear to clear screen
[14:32:16] ℹ Connected successfully! Ready to chat!

[14:32:20] → bob joined the chat
[14:32:25] bob: Hey Alice! 👋
[14:32:30] alice: Hi Bob! How are you?
[14:32:35] bob: This is completely private!

💬 > 
```

## 🛠️ Configuration

### Command Line Options

```bash
enchat --help                                    # Show help
enchat --reset                                   # Clear saved settings
enchat --server https://your-ntfy.example.com   # Use custom ntfy server
enchat wipe                                      # Securely remove all traces
```

### In-Chat Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear screen |
| `/exit` | Leave chat |

### Self-Hosted ntfy

For complete control over your infrastructure:

```bash
# Docker
docker run -d --name ntfy -p 80:80 binwiederhier/ntfy serve

# Then use with Enchat
enchat --server https://your-ntfy-server.com
```

## 🔧 How It Works

**Architecture:**
```
Alice ←→ [Encrypted Channel] ←→ ntfy Server ←→ [Encrypted Channel] ←→ Bob
```

1. **Message encryption** happens on your device using your shared passphrase
2. **Encrypted data** is sent to ntfy server (never plaintext)
3. **Server relays** the encrypted blob without decryption capability
4. **Recipients decrypt** using the same passphrase

**Security Properties:**
- Server compromise doesn't expose message content
- Network sniffing only reveals encrypted data
- Forward secrecy through unique room sessions
- Message authentication prevents tampering

## 🔒 Security Best Practices

✅ **Recommended:**
- Use strong passphrases (12+ characters)
- Share room details through secure channels
- Use different rooms for different groups
- Self-host for sensitive communications

⚠️ **Important:**
- All participants need the exact same passphrase
- Room names are case-sensitive
- Don't reuse room names across different conversations

### Configuration Security

Settings are stored in `~/.enchat.conf`. Secure this file:
```bash
chmod 600 ~/.enchat.conf
```

For maximum security, don't save your passphrase (choose 'n' during setup).

## 📋 Requirements

- **Python 3.6+**
- **Dependencies:** `requests`, `colorama`, `cryptography`
- **Platforms:** Linux, macOS, Windows (with Unicode terminal support)

## 🐛 Troubleshooting

**Connection Issues:**
- Verify internet connection and ntfy server accessibility
- Try default ntfy.sh if custom server fails

**Encryption Issues:**
- Ensure exact passphrase match across all participants
- Check for typos in room names (case-sensitive)

**Display Issues:**
- Ensure terminal supports Unicode characters
- Update terminal emulator for proper color support

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [ntfy.sh](https://ntfy.sh) for secure notification infrastructure
- [cryptography](https://cryptography.io/) for robust encryption implementation

---

**Secure terminal communication made simple**