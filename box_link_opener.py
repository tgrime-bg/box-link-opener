
"""
Box Link Opener

A simple Windows desktop utility:
- Paste a Box shared link
- Resolve it via the Box API using OAuth
- Map it to your local Box Drive folder
- Open the matching folder/file in Windows Explorer

Requirements:
    pip install -r requirements.txt

Run:
    python box_link_opener.py
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import requests


APP_NAME = "Box Link Opener"

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "BoxLinkOpener"
CONFIG_PATH = APP_DIR / "config.json"
TOKEN_PATH = APP_DIR / "token.json"
LOG_PATH = APP_DIR / "last_error.txt"

BOX_AUTH_URL = "https://account.box.com/api/oauth2/authorize"
BOX_TOKEN_URL = "https://api.box.com/oauth2/token"
BOX_SHARED_ITEMS_URL = "https://api.box.com/2.0/shared_items"

DEFAULT_CONFIG = {
    "box_drive_root": str(Path.home() / "Box"),
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "http://localhost:53682/callback",
    "drop_first_path_entry": True,
}


@dataclass
class AppConfig:
    box_drive_root: str
    client_id: str
    client_secret: str
    redirect_uri: str
    drop_first_path_entry: bool


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def log_error(message: str) -> None:
    ensure_app_dir()
    LOG_PATH.write_text(message, encoding="utf-8")


def load_config() -> AppConfig:
    ensure_app_dir()

    if not CONFIG_PATH.exists():
        save_config_dict(DEFAULT_CONFIG)

    data = DEFAULT_CONFIG.copy()
    try:
        data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass

    return AppConfig(
        box_drive_root=str(data.get("box_drive_root", DEFAULT_CONFIG["box_drive_root"])),
        client_id=str(data.get("client_id", "")),
        client_secret=str(data.get("client_secret", "")),
        redirect_uri=str(data.get("redirect_uri", DEFAULT_CONFIG["redirect_uri"])),
        drop_first_path_entry=bool(data.get("drop_first_path_entry", True)),
    )


def save_config_dict(data: dict) -> None:
    ensure_app_dir()
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_config(config: AppConfig) -> None:
    save_config_dict({
        "box_drive_root": config.box_drive_root,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
        "drop_first_path_entry": config.drop_first_path_entry,
    })


def load_tokens() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_tokens(tokens: dict) -> None:
    ensure_app_dir()
    tokens = dict(tokens)
    tokens["saved_at"] = int(time.time())
    TOKEN_PATH.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def clear_tokens() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def parse_local_redirect(config: AppConfig) -> tuple[str, int, str]:
    parsed = urllib.parse.urlparse(config.redirect_uri)
    if parsed.scheme != "http":
        raise ValueError("redirect_uri must use http for this local helper.")
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("redirect_uri must use localhost or 127.0.0.1.")
    if not parsed.port:
        raise ValueError("redirect_uri must include a port, e.g. http://localhost:53682/callback")
    return parsed.hostname, int(parsed.port), parsed.path or "/callback"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None
    auth_state: str | None = None
    auth_error: str | None = None
    expected_path: str = "/callback"

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != self.expected_path:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
        OAuthCallbackHandler.auth_state = params.get("state", [None])[0]
        OAuthCallbackHandler.auth_error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if OAuthCallbackHandler.auth_code:
            html = """
            <html>
              <body style="font-family: system-ui, sans-serif;">
                <h1>Box Link Opener is connected.</h1>
                <p>You can close this tab and return to the app.</p>
              </body>
            </html>
            """
        else:
            html = """
            <html>
              <body style="font-family: system-ui, sans-serif;">
                <h1>Box Link Opener could not connect.</h1>
                <p>Return to the app and try again.</p>
              </body>
            </html>
            """

        self.wfile.write(html.encode("utf-8"))


def request_new_tokens_with_oauth(config: AppConfig) -> dict:
    if not config.client_id or not config.client_secret:
        raise RuntimeError(
            "Missing Box OAuth client_id or client_secret.\n\n"
            "Open Settings and add both values from your Box Developer Console app."
        )

    host, port, path = parse_local_redirect(config)
    OAuthCallbackHandler.auth_code = None
    OAuthCallbackHandler.auth_state = None
    OAuthCallbackHandler.auth_error = None
    OAuthCallbackHandler.expected_path = path

    state = secrets.token_urlsafe(24)

    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
    }
    auth_url = BOX_AUTH_URL + "?" + urllib.parse.urlencode(params)

    try:
        server = HTTPServer((host, port), OAuthCallbackHandler)
    except OSError as exc:
        raise RuntimeError(
            f"Could not start local OAuth callback server on {config.redirect_uri}.\n\n{exc}"
        )

    webbrowser.open(auth_url)

    # Wait for the browser redirect after Box login.
    server.handle_request()
    server.server_close()

    if OAuthCallbackHandler.auth_error:
        raise RuntimeError(f"Box OAuth returned an error: {OAuthCallbackHandler.auth_error}")

    if not OAuthCallbackHandler.auth_code:
        raise RuntimeError("Box OAuth did not return an authorization code.")

    if OAuthCallbackHandler.auth_state != state:
        raise RuntimeError("OAuth state mismatch. Login was cancelled for safety.")

    data = {
        "grant_type": "authorization_code",
        "code": OAuthCallbackHandler.auth_code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
    }

    response = requests.post(BOX_TOKEN_URL, data=data, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Token request failed:\n{response.status_code}\n{response.text}")

    tokens = response.json()
    save_tokens(tokens)
    return tokens


def refresh_tokens(config: AppConfig, refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }

    response = requests.post(BOX_TOKEN_URL, data=data, timeout=30)

    if response.status_code != 200:
        clear_tokens()
        raise RuntimeError(
            "Could not refresh the Box token. Log in again from Settings.\n\n"
            f"{response.status_code}\n{response.text}"
        )

    tokens = response.json()
    save_tokens(tokens)
    return tokens


def get_access_token(config: AppConfig, force_login: bool = False) -> str:
    tokens = None if force_login else load_tokens()

    if not tokens:
        tokens = request_new_tokens_with_oauth(config)
        return str(tokens["access_token"])

    saved_at = int(tokens.get("saved_at", 0))
    expires_in = int(tokens.get("expires_in", 3600))
    expires_at = saved_at + expires_in

    # Refresh a little early.
    if time.time() > expires_at - 120:
        tokens = refresh_tokens(config, str(tokens["refresh_token"]))

    return str(tokens["access_token"])


def get_shared_item(config: AppConfig, shared_link: str) -> dict:
    access_token = get_access_token(config)

    fields = "id,type,name,path_collection,parent,shared_link"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "BoxApi": f"shared_link={shared_link}",
    }

    response = requests.get(
        BOX_SHARED_ITEMS_URL,
        params={"fields": fields},
        headers=headers,
        timeout=30,
    )

    if response.status_code == 401:
        access_token = get_access_token(config, force_login=True)
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.get(
            BOX_SHARED_ITEMS_URL,
            params={"fields": fields},
            headers=headers,
            timeout=30,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Could not resolve Box shared link:\n{response.status_code}\n{response.text}")

    return response.json()


def sanitize_path_part(name: str) -> str:
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, "_")
    return name.strip()


def box_item_to_local_path(config: AppConfig, item: dict) -> str:
    entries = item.get("path_collection", {}).get("entries", [])
    parts = [entry.get("name", "") for entry in entries if entry.get("name")]

    if config.drop_first_path_entry and parts:
        parts = parts[1:]

    item_name = item.get("name")
    if item_name:
        parts.append(str(item_name))

    safe_parts = [sanitize_path_part(part) for part in parts if part]
    return str(Path(config.box_drive_root).joinpath(*safe_parts))


def open_in_explorer(path: str) -> None:
    if os.path.isdir(path):
        subprocess.run(["explorer.exe", path], check=False)
        return

    if os.path.isfile(path):
        subprocess.run(["explorer.exe", "/select,", path], check=False)
        return

    parent = Path(path)
    while parent != parent.parent and not parent.exists():
        parent = parent.parent

    if parent.exists() and parent.is_dir():
        subprocess.run(["explorer.exe", str(parent)], check=False)

    raise FileNotFoundError(
        "Box resolved the link, but the expected local Box Drive path does not exist.\n\n"
        f"Expected path:\n{path}\n\n"
        "Possible causes:\n"
        "- Box Drive is not running\n"
        "- Your configured Box Drive root is wrong\n"
        "- The first path entry setting needs to be toggled\n"
        "- The item is accessible online but not present in your local Box Drive namespace"
    )


def open_box_link(shared_link: str) -> str:
    config = load_config()
    item = get_shared_item(config, shared_link)
    local_path = box_item_to_local_path(config, item)
    open_in_explorer(local_path)
    return local_path


class BoxLinkOpenerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("760x430")

        self.link_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Paste a Box shared link, then click Open in Explorer.")
        self.path_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, padx=14, pady=14)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            outer,
            text="Paste a Box shared link and open the matching local Box Drive folder or file.",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 14))

        tk.Label(outer, text="Box link:").pack(anchor="w")
        entry = tk.Entry(outer, textvariable=self.link_var, width=110)
        entry.pack(fill="x", pady=(4, 8))
        entry.focus()

        button_row = tk.Frame(outer)
        button_row.pack(fill="x", pady=(4, 12))

        tk.Button(button_row, text="Open in Explorer", command=self.open_clicked, width=18).pack(side="left")
        tk.Button(button_row, text="Paste from Clipboard", command=self.paste_clicked, width=18).pack(side="left", padx=(8, 0))
        tk.Button(button_row, text="Settings", command=self.settings_clicked, width=12).pack(side="left", padx=(8, 0))
        tk.Button(button_row, text="Log in to Box", command=self.login_clicked, width=14).pack(side="left", padx=(8, 0))

        tk.Label(outer, text="Status:").pack(anchor="w")
        tk.Label(
            outer,
            textvariable=self.status_var,
            justify="left",
            wraplength=720,
            relief="groove",
            padx=8,
            pady=8,
        ).pack(fill="x", pady=(4, 12))

        tk.Label(outer, text="Last resolved local path:").pack(anchor="w")
        tk.Label(
            outer,
            textvariable=self.path_var,
            justify="left",
            wraplength=720,
            relief="groove",
            padx=8,
            pady=8,
        ).pack(fill="x", pady=(4, 12))

        tk.Label(
            outer,
            text=f"Config and tokens are stored in: {APP_DIR}",
            font=("Segoe UI", 8),
            fg="gray",
            wraplength=720,
            justify="left",
        ).pack(anchor="w", side="bottom")

    def paste_clicked(self) -> None:
        try:
            self.link_var.set(self.root.clipboard_get().strip())
            self.status_var.set("Pasted link from clipboard.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not read clipboard:\n{exc}")

    def open_clicked(self) -> None:
        shared_link = self.link_var.get().strip()
        if not shared_link:
            messagebox.showwarning(APP_NAME, "Paste a Box shared link first.")
            return

        try:
            self.status_var.set("Resolving Box link...")
            self.root.update_idletasks()
            local_path = open_box_link(shared_link)
            self.path_var.set(local_path)
            self.status_var.set("Opened in Windows Explorer.")
        except Exception as exc:
            log_error(str(exc))
            self.status_var.set("Could not open the link. See the error popup for details.")
            messagebox.showerror(APP_NAME, str(exc))

    def login_clicked(self) -> None:
        try:
            self.status_var.set("Opening Box login in your browser...")
            self.root.update_idletasks()
            request_new_tokens_with_oauth(load_config())
            self.status_var.set("Box login succeeded.")
            messagebox.showinfo(APP_NAME, "Box login succeeded.")
        except Exception as exc:
            log_error(str(exc))
            self.status_var.set("Box login failed. See the error popup for details.")
            messagebox.showerror(APP_NAME, str(exc))

    def settings_clicked(self) -> None:
        SettingsWindow(self.root)

    def run(self) -> None:
        self.root.mainloop()


class SettingsWindow:
    def __init__(self, parent: tk.Tk) -> None:
        self.parent = parent
        self.config = load_config()

        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        self.win.geometry("780x320")
        self.win.transient(parent)
        self.win.grab_set()

        self.box_drive_root = tk.StringVar(value=self.config.box_drive_root)
        self.client_id = tk.StringVar(value=self.config.client_id)
        self.client_secret = tk.StringVar(value=self.config.client_secret)
        self.redirect_uri = tk.StringVar(value=self.config.redirect_uri)
        self.drop_first = tk.BooleanVar(value=self.config.drop_first_path_entry)

        self._build_ui()

    def _build_ui(self) -> None:
        frame = tk.Frame(self.win, padx=14, pady=14)
        frame.pack(fill="both", expand=True)

        def row(label: str, variable: tk.StringVar, index: int, show: str | None = None) -> tk.Entry:
            tk.Label(frame, text=label).grid(row=index, column=0, sticky="w", padx=6, pady=6)
            entry = tk.Entry(frame, textvariable=variable, width=82, show=show)
            entry.grid(row=index, column=1, sticky="we", padx=6, pady=6)
            return entry

        row("Local Box Drive root:", self.box_drive_root, 0)
        tk.Button(frame, text="Browse", command=self.browse_root).grid(row=0, column=2, padx=6, pady=6)

        row("Box OAuth client_id:", self.client_id, 1)
        row("Box OAuth client_secret:", self.client_secret, 2, show="*")
        row("Redirect URI:", self.redirect_uri, 3)

        tk.Checkbutton(
            frame,
            text='Drop first Box path entry, usually "All Files"',
            variable=self.drop_first,
        ).grid(row=4, column=1, sticky="w", padx=6, pady=6)

        buttons = tk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="w", pady=(14, 0))

        tk.Button(buttons, text="Save", command=self.save, width=14).pack(side="left")
        tk.Button(buttons, text="Clear saved tokens", command=self.clear_saved_tokens, width=18).pack(side="left", padx=(8, 0))
        tk.Button(buttons, text="Close", command=self.win.destroy, width=12).pack(side="left", padx=(8, 0))

        help_text = (
            "Create a Box OAuth app in the Box Developer Console, then add this redirect URI exactly: "
            "http://localhost:53682/callback"
        )
        tk.Label(frame, text=help_text, justify="left", wraplength=720, fg="gray").grid(
            row=6, column=0, columnspan=3, sticky="w", padx=6, pady=(18, 6)
        )

        frame.columnconfigure(1, weight=1)

    def browse_root(self) -> None:
        chosen = filedialog.askdirectory(title="Choose your local Box Drive folder")
        if chosen:
            self.box_drive_root.set(chosen)

    def save(self) -> None:
        new_config = AppConfig(
            box_drive_root=self.box_drive_root.get().strip(),
            client_id=self.client_id.get().strip(),
            client_secret=self.client_secret.get().strip(),
            redirect_uri=self.redirect_uri.get().strip(),
            drop_first_path_entry=bool(self.drop_first.get()),
        )
        save_config(new_config)
        messagebox.showinfo(APP_NAME, f"Saved settings to:\n{CONFIG_PATH}")

    def clear_saved_tokens(self) -> None:
        clear_tokens()
        messagebox.showinfo(APP_NAME, "Saved OAuth tokens were cleared. Use Log in to Box again.")


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--url", help="Open a specific Box shared link.")
    parser.add_argument("--login", action="store_true", help="Force a new Box OAuth login.")
    parser.add_argument("--settings", action="store_true", help="Open the GUI.")
    args = parser.parse_args()

    try:
        if args.login:
            request_new_tokens_with_oauth(load_config())
            print("OAuth login succeeded.")
            return 0

        if args.url:
            print(open_box_link(args.url))
            return 0

        BoxLinkOpenerApp().run()
        return 0

    except Exception as exc:
        log_error(str(exc))
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_NAME, str(exc))
            root.destroy()
        except Exception:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
