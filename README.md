# Termux-NexusSEC-OS

Un ambiente di pentesting/amministrazione di rete su Android **senza root e senza
custom ROM**: un'interfaccia web moderna (PWA) che pilota i tool a riga di comando
di Kali Linux, il tutto dentro Termux.

> ⚠️ **Uso legale.** I tool inclusi vanno usati **solo** su sistemi e reti di tua
> proprietà o per cui hai un'autorizzazione scritta. Usarli contro terzi senza
> permesso è un reato. Questo progetto è pensato per apprendimento, laboratorio e
> penetration test autorizzati.

---

## Cos'è (l'idea in due righe)

Non riscriviamo Android e non compiliamo un kernel. Costruiamo due strati:

1. **Il motore** — una mini-distribuzione **Kali** installata dentro Termux con
   `proot-distro`. Fornisce i veri tool CLI (nmap, sqlmap, metasploit, …).
2. **L'interfaccia** — una **PWA** (pagina web installabile) servita da un piccolo
   server Python locale, con icone toccabili al posto dei comandi da digitare.

All'utente sembra una app; sotto, gira Kali.

---

## Architettura

```
┌─────────────────────────────────────────────┐
│  PWA (webapp/)  — icone, storico, terminale   │  ← quello che vedi
└───────────────┬─────────────────────────────┘
                │  HTTP su 127.0.0.1 (solo locale)
┌───────────────▼─────────────────────────────┐
│  server.py (FastAPI)  — il "ponte"            │
│   • oneshot   → subprocess → output JSON      │
│   • interactive → ttyd → terminale nel browser│
└───────────────┬─────────────────────────────┘
                │  proot-distro login kali -- <tool>
┌───────────────▼─────────────────────────────┐
│  Kali (proot)  — nmap, sqlmap, metasploit…    │  ← il motore
└─────────────────────────────────────────────┘
```

### I file

| File | Dove gira | Ruolo |
|------|-----------|-------|
| `install.sh` | Termux | Bootstrap: installa Termux base, Python, Kali e i tool |
| `tools.py` | ovunque | Registry dei tool + validazione input (nessuna dipendenza) |
| `native.py` | ovunque | Tool "nativi": richieste HTTP dirette (es. RDAP), senza proot |
| `server.py` | Termux | Backend **reale**: esegue i tool via proot / ttyd / native |
| `mock_server.py` | PC | Backend **finto** per sviluppare la UI senza Kali (solo stdlib) |
| `webapp/` | ovunque | La PWA: `index.html`, `manifest.json`, `sw.js` |

### Le tre modalità dei tool

- **`oneshot`** — il tool parte, produce un output e finisce (es. `nmap -sT`).
  Eseguito dentro Kali via proot; l'output torna come JSON, mostrato nell'app.
- **`interactive`** — il tool è una sessione (es. `msfconsole`, una shell).
  Viene esposto come **terminale nel browser** tramite `ttyd`. Se l'incorporamento
  in iframe viene bloccato, l'app offre il tasto **↗ Scheda** per aprirlo a parte.
- **`native`** — nessun Kali: il server Python fa direttamente una **richiesta HTTP
  a un'API pubblica** (es. `rdap` → whois via RDAP). Leggero, istantaneo, funziona
  anche prima di installare Kali e persino sul PC.

### Modalità anonima (Tor)

Il pulsante **🧅 Tor** nell'header instrada il traffico via Tor (`proxychains`
dentro Kali). Vale solo per i tool con il badge 🧅 (connessioni **TCP connect**:
`nmap -sT`, `whatweb`, `nikto`, `whois`). Categoria **Anonimato** dedicata:
*Verifica IP di uscita* e *Shell anonima*.

> Tor nasconde il tuo IP **verso il target**, ma non è invisibilità: instrada solo
> TCP (niente ping sweep/UDP), e non cambia nulla sul piano dell'autorizzazione.
> Alla prima accensione Tor può impiegare 10–30 s per costruire il circuito.

---

## Cosa puoi fare ✅ e cosa no ❌

### ✅ Funziona bene (rete IP e calcolo — il grosso del pentest)
- **Scansione di rete**: `nmap`, `masscan`, ping sweep, port scan, service detection.
- **Web/App pentest**: `sqlmap`, `nikto`, `gobuster`/`ffuf` (fuzzing directory),
  `whatweb`, `wpscan`.
- **Exploitation**: `metasploit`, `hydra` (brute-force su servizi di rete).
- **Cracking offline**: `john`, `hashcat` (CPU), `aircrack-ng` **su handshake già
  catturati**.
- **Amministrazione**: shell completa dentro Kali, `apt` per aggiungere altri tool.

### ❌ NON funziona (limiti reali, non aggirabili via software su telefono stock)
- **Cattura Wi-Fi / monitor mode / packet injection**: `airodump-ng`, deauth,
  `reaver`, WPS. Il chip Wi-Fi degli smartphone quasi mai supporta la monitor mode,
  e senza root/kernel adatto non c'è workaround. → puoi solo fare **crack offline**
  di handshake catturati con altro hardware.
- **Tool con interfaccia grafica** (es. Wireshark GUI, Burp Suite): non c'è un
  server grafico. Usa le versioni CLI (`tshark`, `wireshark-cli`).
- **Vero root del kernel**: `proot` è un'emulazione dello spazio utente. Alcune
  operazioni che richiedono privilegi kernel (raw socket a basso livello,
  manipolazione di interfacce) possono fallire o dare risultati parziali.

### 💡 Ricognizione senza Kali (modalità `native`, già inclusa)
Alcune funzioni **non richiedono affatto Kali**: il tool **Whois RDAP** (`rdap`)
interroga direttamente l'API pubblica RDAP e restituisce dati di dominio o IP in
modo istantaneo, senza proot — funziona anche prima di installare Kali e sul PC.
Lo stesso schema è estendibile a DNS-over-HTTPS, certificati (crt.sh), geo-IP.

---

## Quanto spazio occupa

Ordini di grandezza indicativi (variano con versioni e dipendenze scaricate):

| Componente | Spazio approssimativo |
|-----------|----------------------|
| Termux base + Python + FastAPI + ttyd | ~250–400 MB |
| Kali base via `proot-distro` (rootfs iniziale) | ~400–500 MB |
| Tool CLI curati (nmap, sqlmap, nikto, gobuster, ffuf, whatweb, wpscan, hydra, john, hashcat, aircrack) + dipendenze | ~800 MB – 1,2 GB |
| **Totale set base (senza Metasploit)** | **~1,5 – 2 GB** |
| Metasploit Framework (opzionale) | **+1,5 – 2 GB** |
| Wordlist tipo `rockyou` (opzionale, se le aggiungi) | ~130 MB |

**In pratica:** conta **~2 GB** per un'installazione utile, **~3,5–4 GB** se vuoi
anche Metasploit. Consiglio almeno **8–10 GB liberi** sul telefono per stare comodo
con cache di `apt`, download temporanei e i risultati.

Cosa **NON** installiamo di proposito:
- ❌ `kali-linux-everything` / meta-pacchetti (20+ GB, farebbero crashare il telefono).
- ❌ Ambiente grafico / desktop / VNC.
- ❌ Metasploit di default (troppo pesante — si abilita a richiesta).

---

## Installazione (sul telefono, in Termux)

### Passo 1 — Installare Termux (e F-Droid)

Installa **Termux** da **F-Droid**, *non* dal Play Store (quella versione è vecchia e
non aggiornabile):

1. Scarica e installa l'app **F-Droid** da <https://f-droid.org>.
2. Dentro F-Droid cerca e installa **Termux**.
3. (Opzionale ma utile) installa anche **Termux:Boot** e **Termux:API** da F-Droid,
   se in futuro vorrai l'auto-avvio e le funzioni di sistema.

Apri Termux e aggiorna i pacchetti base:

```bash
pkg update && pkg upgrade -y
```

### Passo 2 — Portare i file di `Termux-NexusSEC-OS` dentro Termux

Devi copiare questa cartella (con `install.sh`, `server.py`, `tools.py`, `webapp/`…)
dentro Termux. Scegli **uno** dei metodi qui sotto.

Termux, di default, vede solo il suo spazio privato (`~` =
`/data/data/com.termux/files/home`). Per accedere ai file scaricati sul telefono
serve prima dare il permesso allo storage **una volta sola**:

```bash
termux-setup-storage      # concedi il permesso quando Android lo chiede
```

Da qui in poi la cartella Download del telefono è `~/storage/downloads`.

---

#### Metodo A — File ZIP (il più semplice, senza PC in rete)

1. Sul computer, comprimi la cartella in **`Termux-NexusSEC-OS.zip`**.
2. Trasferisci lo zip sul telefono nel modo che preferisci: cavo USB, oppure
   mandandotelo su Google Drive / Telegram / email e scaricandolo. Deve finire
   nella cartella **Download**.
3. In Termux:

```bash
pkg install unzip -y
cd ~
unzip ~/storage/downloads/Termux-NexusSEC-OS.zip     # crea la cartella Termux-NexusSEC-OS/
cd Termux-NexusSEC-OS
```

#### Metodo B — Git (comodo se aggiorni spesso il codice)

Se metti il progetto su un repo (GitHub, Codeberg…):

```bash
pkg install git -y
git clone <URL-del-repo> Termux-NexusSEC-OS
cd Termux-NexusSEC-OS
```

Per aggiornarlo in seguito basterà `git pull` dentro la cartella.

#### Metodo C — Copia da PC via SSH (stessa rete Wi-Fi)

Utile se vuoi sincronizzare direttamente dal computer. In Termux:

```bash
pkg install openssh -y
whoami          # annota l'utente
ifconfig 2>/dev/null | grep 'inet '   # annota l'IP del telefono (es. 192.168.1.42)
sshd            # avvia il server SSH sul telefono (porta 8022)
```

Poi dal **PC** (nella cartella che contiene `Termux-NexusSEC-OS/`):

```bash
scp -P 8022 -r Termux-NexusSEC-OS <utente>@<IP-telefono>:~/
# esempio: scp -P 8022 -r Termux-NexusSEC-OS u0_a123@192.168.1.42:~/
```

> Nota: la prima volta imposta una password in Termux con `passwd`, perché lo
> `sshd` di Termux usa quella per l'accesso.

---

### Passo 3 — Lanciare l'installer

Una volta che sei dentro la cartella `Termux-NexusSEC-OS`:

```bash
chmod +x install.sh
./install.sh                       # set base (~2 GB, scarica Kali + tool)

# oppure, per includere anche Metasploit:
INSTALL_METASPLOIT=yes ./install.sh
```

Lo script è **idempotente**: puoi rilanciarlo senza rifare i download già fatti.

> **Suggerimento:** durante il download di Kali e dei tool, tieni Termux in
> primo piano o disattiva l'ottimizzazione batteria per Termux (Impostazioni
> Android → App → Termux → Batteria → "Nessuna restrizione"), altrimenti Android
> può sospendere il processo a schermo spento.

### Avvio

```bash
python server.py
```

Poi apri nel browser del telefono **http://127.0.0.1:8000**.
Da Chrome puoi fare *"Aggiungi a schermata Home"*: grazie al `manifest.json`
l'app parte a tutto schermo, come una vera applicazione.

---

## Provare l'interfaccia sul PC (senza telefono, senza Kali)

Per sviluppare/rifinire la UI c'è un backend finto che **non richiede nulla**
(solo Python 3):

```bash
python3 mock_server.py     # apri http://127.0.0.1:8000
```

I tool one-shot restituiscono output **simulato** e i tool interattivi aprono un
terminale placeholder. Fa eccezione — ed è voluto — la modalità **`native`**: il
tool **Whois RDAP** viene eseguito **davvero** anche nel mock (è solo una richiesta
HTTP), quindi sul PC ottieni dati reali. Tutta la navigazione, il modal del target,
il toggle Tor, lo storico e il salvataggio output sono identici alla versione reale
(condividono `tools.py` e `native.py`).

---

## Funzioni della UI

- **Griglia per categoria** con icone e ricerca istantanea; badge per modalità
  (`» run` / `▮ terminale` / `🌐 live`) e per Tor (🧅).
- **Toggle 🧅 Tor** nell'header per la modalità anonima.
- **Modal del target** con validazione in tempo reale (rifiuta input pericolosi).
- **Storico** delle esecuzioni (salvato in locale nel browser), riapribile.
- **Copia** e **download `.txt`** dell'output.
- **Terminale integrato** a schermo intero per i tool interattivi, con fallback
  **↗ Scheda** se `ttyd` blocca l'incorporamento in iframe.
- Funziona **offline** come PWA (lo "shell" dell'app è in cache; le chiamate ai
  tool ovviamente richiedono che `server.py` sia in esecuzione).

---

## Sicurezza (scelte di progetto)

- **Bind solo su `127.0.0.1`**: il server **non** è raggiungibile dalla rete Wi-Fi.
  Nessun altro dispositivo può eseguire comandi sul tuo telefono.
- **Niente shell injection**: i comandi sono liste di argomenti, mai stringhe
  concatenate; **non** si usa `shell=True`.
- **Validazione del target**: host/IP/CIDR e URL sono verificati con regex; un input
  che inizia con `-` (per iniettare flag) o che contiene metacaratteri viene rifiutato.
- **Whitelist**: si possono eseguire solo i tool dichiarati in `tools.py`.
- **Modalità `native`**: la richiesta esce dal telefono verso un servizio esterno
  (RDAP). Ricorda che stai comunicando a quel servizio cosa stai cercando; per il
  whois di un dominio è irrilevante, ma tienilo presente per target sensibili.

---

## Limitazioni note / da valutare in fase di test

- **Overhead di proot**: ogni comando one-shot rimonta l'ambiente Kali (qualche
  secondo). Se dà fastidio, il passo successivo è mantenere una sessione persistente.
- **Batteria**: tenere `server.py` acceso consuma. Conviene avviarlo quando serve e
  chiuderlo dopo (non 24/7).
- **Metasploit su proot**: la prima inizializzazione del database può dare warning;
  `msfconsole` funziona comunque anche senza DB.
- **Terminale `ttyd` in iframe**: alcune versioni impostano header che ne bloccano
  l'incorporamento. In quel caso il riquadro resta vuoto: usa il tasto **↗ Scheda**.
- **Tor "pronto" ≠ porta aperta**: alla prima accensione attendi che il circuito sia
  costruito (10–30 s) prima che i tool via Tor rispondano.

---

## Estensioni possibili (roadmap)

- **Altri tool `native`**: DNS → DNS-over-HTTPS, certificati → crt.sh, geo-IP.
  Stesso schema di `rdap`, in `native.py`.
- **Auto-avvio** con **Termux:Boot** (lancia `server.py` all'accensione).
- **Launcher WebView**: una app Android minimale (solo WebView a tutto schermo)
  impostata come launcher predefinito, per aprire la PWA come "sistema" all'avvio.
- **Sessione Kali persistente** per abbattere l'overhead di proot.
- **Bootstrap Tor al 100%**: leggere la control port invece della sola SOCKS.
- **Integrazione `termux-api`** per notifiche, GPS, appunti, ecc.

---

## Struttura del progetto

```
Termux-NexusSEC-OS/
├── install.sh          # bootstrap Termux + Kali + tool (+ tor/proxychains)
├── tools.py            # registry tool + validazione (condiviso)
├── native.py           # tool "nativi" via HTTP (RDAP), senza proot
├── server.py           # backend reale (FastAPI, proot + ttyd + native + Tor)
├── mock_server.py      # backend finto per il PC (solo stdlib)
├── README.md           # questo file
└── webapp/
    ├── index.html      # la PWA
    ├── manifest.json   # metadati PWA (installabile)
    └── sw.js           # service worker (cache offline dello shell)
```
