
# Box Link Opener

A small Windows desktop app for opening Box shared links in your local Box Drive folder.


Workflow:

```text
Run app -> paste Box link -> app resolves through Box OAuth/API -> Explorer opens local Box Drive path
```

## Files

- `box_link_opener.py` - main app
- `requirements.txt` - Python dependency list
- `Run_Box_Link_Opener.bat` - double-click launcher
- `Install_And_Run.bat` - installs dependencies, then runs app
- `Build_EXE.ps1` - optional PyInstaller build script
- `README.md` - this file

## Install and run

1. Install Python 3.11 or newer.
2. Unzip this folder.
3. Double-click:

```text
Install_And_Run.bat
```

Or run manually from PowerShell:

```powershell
pip install -r requirements.txt
python box_link_opener.py
```

## Create a Box OAuth app

In the Box Developer Console:

1. Create a custom app.
2. Choose OAuth 2.0 / user authentication.
3. Add this redirect URI exactly:

```text
http://localhost:53682/callback
```

4. Copy the app's `client_id` and `client_secret`.

## Configure the app

In Box Link Opener:

1. Click **Settings**.
2. Set your local Box Drive root, for example:

```text
C:\Users\Thomas\Box
```

3. Paste your Box OAuth `client_id`.
4. Paste your Box OAuth `client_secret`.
5. Leave redirect URI as:

```text
http://localhost:53682/callback
```

6. Click **Save**.
7. Click **Log in to Box**.

## Use

1. Copy a Box shared link.
2. Launch `Run_Box_Link_Opener.bat`.
3. Paste the link.
4. Click **Open in Explorer**.

The app will resolve the link through Box, construct the expected local Box Drive path, then open that folder or select that file in Windows Explorer.

## Optional: build a single EXE

From PowerShell:

```powershell
.\Build_EXE.ps1
```

The resulting EXE will be in:

```text
dist\BoxLinkOpener.exe
```

You can copy that EXE somewhere convenient and create a Start Menu/Desktop shortcut.

## Where settings are stored

```text
%APPDATA%\BoxLinkOpener\config.json
%APPDATA%\BoxLinkOpener\token.json
%APPDATA%\BoxLinkOpener\last_error.txt
```

## Troubleshooting

### Explorer opens the wrong folder

Open **Settings** and toggle:

```text
Drop first Box path entry, usually "All Files"
```

Then try again.

### Box resolves the link, but the path does not exist locally

Possible causes:

- Box Drive is not running.
- Your configured Box Drive root is wrong.
- The linked item is accessible in the browser but not visible in your local Box Drive namespace.
- The first-path-entry setting needs to be toggled.

### Login stops working after a while

Use **Settings -> Clear saved tokens**, then **Log in to Box** again.
