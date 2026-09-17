# pDrop

**Passworded LAN file browser for SharkDeck / WalnutPi OS.**

`pDrop` is a single-file Python 3 HTTP server. Run it on the deck, open a phone or laptop on the same Wi-Fi, and browse, download, upload, mkdir, or delete under a chosen root.

```
pDrop  http://0.0.0.0:8080/  root=/home/working  user=pdrop
```

It is **HTTP, not HTTPS**. Stay on your LAN. Do not put this on the public internet.

## What it does

- Directory listing in a dark, phone-friendly page
- Breadcrumb path
- Directories first, files second
- Download any file as an attachment
- Upload into the current folder
- Create a folder
- Delete a file, or an empty folder
- HTTP Basic Auth (username + password)
- Path join is clamped to `--root` so `../` cannot walk out

Default root is `/home/working` when that directory exists, otherwise `$HOME`.

## Requirements

Python 3 from the official WalnutPi Zero 2W / SharkDeck image. No pip packages. It uses only the standard library (`http.server`, `argparse`, `html`, `urllib`).

On the 3.5″ 480×320 deck you usually start pDrop in a tty and browse from another device. The UI is built for a phone or laptop viewport, not for the panel itself.

## Run

```bash
chmod +x pdrop.py
./pdrop.py
```

or

```bash
python3 pdrop.py
```

Then, from another machine on the same network:

```
http://<deck-ip>:8080/
```

Find the deck address with:

```bash
hostname -I
```

Browser login:

| Field | Default |
| --- | --- |
| Username | `pdrop` |
| Password | `shark` (change this) |

## Options

```bash
pDrop --root /home/working --port 8080 --pass secret
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--root` | `/home/working` or `$HOME` | Tree the browser is allowed to see |
| `--port` | `8080` | Listen port |
| `--bind` | `0.0.0.0` | Bind address (`127.0.0.1` for local-only) |
| `--pass` | see password order below | HTTP Basic password |
| `--user` | `pdrop` | HTTP Basic username |

Examples:

```bash
# Share the working tree on the default port
python3 pdrop.py --root /home/working

# Tight bind: only the deck itself can connect
python3 pdrop.py --bind 127.0.0.1 --port 8080

# Share a drop folder on another port
python3 pdrop.py --root /home/working/inbox --port 9090 --user deck --pass change-me
```

`--root` is created if it does not exist.

## Password

Resolved in this order. First hit wins.

1. `--pass` on the command line
2. Environment variable `PDROP_PASS`
3. First line of `~/.pdrop.pass`
4. Hardcoded fallback `shark`

Set a real password before you leave the device on the LAN:

```bash
echo 'your-long-password' > ~/.pdrop.pass
chmod 600 ~/.pdrop.pass
```

or:

```bash
export PDROP_PASS='your-long-password'
python3 pdrop.py
```

`--pass` is visible in `ps`. Prefer the file or the environment variable.

## Page

Dark background, green title, cyan links, green directory names.

Each row:

- name (directories end with `/`)
- size (`B` / `K` / `M`)
- **del** button

Below the table:

- file picker + **upload**
- text field + **mkdir**

`..` is shown when you are not at the root. Clicking a file downloads it. Clicking a directory lists it.

Delete of a directory uses `os.rmdir`, so a folder with files in it will fail until you empty it.

## Security model

pDrop is a convenience tool for a handheld on a trusted network. Treat it that way.

- HTTP Basic over cleartext. Anyone on the LAN who can sniff can see the password after you log in.
- No TLS, no sessions, no CSRF tokens.
- Upload overwrites a same-named file in that folder.
- Delete is a one-click POST with no confirm dialog.
- `safe_join` rejects paths outside `--root`, including `..` and backslashes.
- Uploaded and mkdir names are reduced to `os.path.basename`, so a crafted filename cannot escape the current folder.
- The server is `ThreadingHTTPServer` — fine for a couple of phones, not a public file host.
- Bind `127.0.0.1` if you only need it over SSH port-forward:

```bash
python3 pdrop.py --bind 127.0.0.1 --port 8080
# on the laptop:
ssh -L 8080:127.0.0.1:8080 user@<deck-ip>
```

Then open `http://127.0.0.1:8080/` on the laptop.

## Autostart on the deck

A user systemd unit keeps it off until you want it:

```ini
# ~/.config/systemd/user/pdrop.service
[Unit]
Description=pDrop LAN file browser
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/working/SharkDeck/pdrop.py --root /home/working --port 8080
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now pdrop.service
```

Keep the password in `~/.pdrop.pass`, not in the unit file.

## Keyboard / launcher

Point a sKEY bind or a shell alias at the script if you want one key to start sharing:

```bash
alias drop='python3 /home/working/SharkDeck/pdrop.py --root /home/working'
```

Stop it with Ctrl+C in that tty (`bye`).

## Files

```
pdrop.py         the server
~/.pdrop.pass    optional password (one line)
```

Single file. No extra modules.

## Compatibility

Written against:

- SharkDeck Gen 1 — WalnutPi Zero 2W, Allwinner H618, 1 GB RAM
- Official WalnutPi Zero 2W image from [sharkdeck.dev/firmware](https://sharkdeck.dev/firmware)
- Docs: [sharkdeck.dev/docs](https://sharkdeck.dev/docs) (rev 4, 2026-08-19)
- Python 3 on any Linux box with a LAN interface

The 480×320 panel is not the client. The client is whatever browser you have in your pocket.

## License

Use and modify freely for personal use ONLY
