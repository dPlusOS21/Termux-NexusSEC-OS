#!/data/data/com.termux/files/usr/bin/bash
#
# install.sh - Bootstrap dell'ambiente "Termux-NexusSEC-OS"
#
# Prepara Termux + una mini-distribuzione Kali (via proot-distro) con un set
# CURATO di tool da riga di comando, e installa le dipendenze Python del ponte.
#
# NON installa meta-pacchetti tipo kali-linux-everything (20+ GB).
# Metasploit e' pesante (~1.5 GB): disattivato di default, abilitalo con:
#     INSTALL_METASPLOIT=yes ./install.sh
#
# Idempotente: puoi rilanciarlo, salta cio' che e' gia' fatto.

set -euo pipefail

DISTRO="kali-rolling"
INSTALL_METASPLOIT="${INSTALL_METASPLOIT:-no}"

log()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }

# --- 0. Controllo di essere davvero in Termux -------------------------------
if [ -z "${PREFIX:-}" ] || [ ! -d "/data/data/com.termux" ]; then
    err "Questo script va eseguito dentro Termux."
    exit 1
fi

# --- 1. Base Termux ---------------------------------------------------------
log "Aggiorno i pacchetti di Termux..."
pkg update -y && pkg upgrade -y

log "Installo i pacchetti base (proot-distro, python, ttyd)..."
pkg install -y proot-distro python ttyd

# --- 2. Dipendenze Python del ponte ----------------------------------------
log "Installo FastAPI + uvicorn..."
python -m pip install --upgrade pip
python -m pip install "fastapi" "uvicorn[standard]"

# --- 3. Installazione di Kali dentro proot ----------------------------------
if proot-distro login "$DISTRO" -- true >/dev/null 2>&1; then
    log "Kali ($DISTRO) risulta gia' installata, salto il download."
else
    log "Installo Kali ($DISTRO) via proot-distro (scarica ~1-2 GB)..."
    proot-distro install "$DISTRO"
fi

# --- 4. Configurazione e tool dentro Kali -----------------------------------
log "Aggiorno gli indici dei pacchetti dentro Kali..."
proot-distro login "$DISTRO" -- apt-get update -y

# Set curato di tool CLI. Divisi per categoria a scopo documentale.
NETWORK_TOOLS="nmap masscan netcat-traditional dnsutils whois"
WEB_TOOLS="sqlmap nikto gobuster ffuf whatweb wpscan"
CRACK_TOOLS="john hashcat hashid aircrack-ng"          # aircrack solo crack offline
EXPLOIT_TOOLS="hydra"                                  # metasploit a parte (pesante)
ANON_TOOLS="tor proxychains4"                          # anonimato: traffico via Tor
UTILS="curl git ca-certificates"

log "Installo i tool CLI dentro Kali (puo' richiedere qualche minuto)..."
# shellcheck disable=SC2086
proot-distro login "$DISTRO" -- apt-get install -y --no-install-recommends \
    $NETWORK_TOOLS $WEB_TOOLS $CRACK_TOOLS $EXPLOIT_TOOLS $ANON_TOOLS $UTILS

# --- 4b. Configurazione di proxychains per usare Tor (SOCKS5 + DNS via proxy)
log "Configuro proxychains per instradare via Tor..."
proot-distro login "$DISTRO" -- bash -c 'cat > /etc/proxychains4.conf <<EOF
# Generato da install.sh (Termux-NexusSEC-OS) - instrada il TCP via Tor
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 127.0.0.1 9050
EOF'

if [ "$INSTALL_METASPLOIT" = "yes" ]; then
    log "Installo Metasploit Framework (pesante, ~1.5 GB)..."
    proot-distro login "$DISTRO" -- apt-get install -y --no-install-recommends metasploit-framework
else
    warn "Metasploit NON installato. Per aggiungerlo: INSTALL_METASPLOIT=yes ./install.sh"
fi

# --- 5. Fine ----------------------------------------------------------------
log "Installazione completata."
echo
echo "Per avviare l'interfaccia:"
echo "    python server.py"
echo "Poi apri nel browser del telefono:  http://127.0.0.1:8000"
