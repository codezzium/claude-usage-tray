# claude-usage-tray

Your Claude plan usage in the Windows taskbar. One small number per limit, refreshed every minute.

![Three tray icons showing 15, 63 and 88](docs/preview.png)

From left to right:

| Icon | Limit |
|---|---|
| 1 | 5-hour session |
| 2 | Weekly, all models |
| 3 | Weekly, per model (for example Fable) |

The colour shows how full the limit is: green under 50%, amber from 50%, red from 80%. Hover an icon to see when the limit resets. If your plan has fewer limits, you get fewer icons.

> Not affiliated with Anthropic. It reads an undocumented endpoint that may change without notice.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- [Claude Code](https://claude.com/claude-code), signed in with your Claude account

## Install

```powershell
git clone https://github.com/codezzium/claude-usage-tray.git
cd claude-usage-tray
py -m pip install --user -r requirements.txt
pyw usage_tray.pyw
```

Windows puts new tray icons in the hidden area under the `^` arrow. Drag the three icons onto the taskbar once. They keep the right order wherever you drop them.

## Start with Windows

Run this in PowerShell from the repo folder:

```powershell
$py = (py -c "import sys; print(sys.executable)") -replace 'python\.exe$', 'pythonw.exe'
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Claude Usage Tray.lnk")
$lnk.TargetPath = $py
$lnk.Arguments = "`"$PWD\usage_tray.pyw`""
$lnk.WorkingDirectory = "$PWD"
$lnk.Save()
```

To stop it starting, delete `Claude Usage Tray.lnk` from the folder that opens with `shell:startup`.

## How it works

- Every minute it reads the access token from `%USERPROFILE%\.claude\.credentials.json`, the file Claude Code keeps, and calls `https://api.anthropic.com/api/oauth/usage`. The token is sent nowhere else.
- It never uses the refresh token. When the access token expires, the icons show a grey `?` until you use Claude Code again and it refreshes the login.
- Switching accounts in Claude Code needs no restart. The next poll picks up the new account.
- After three failed requests in a row the icons turn grey. On HTTP 429 it waits longer between requests, up to 10 minutes.
- Right-click an icon for **Refresh now** and **Quit**. A left click also refreshes.
- Tooltips are in Turkish when Windows is set to Turkish, otherwise in English.
- A log is written to `usage_tray.log` next to the script (rotated at 256 KB).

## License

MIT
