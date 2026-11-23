# claude-usage-tray

Your Claude plan usage in the Windows taskbar. One small number per limit, refreshed every 5 minutes.

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
pyw main.pyw
```

Windows puts new tray icons in the hidden area under the `^` arrow. Drag the three icons onto the taskbar once. They keep the right order wherever you drop them.

## Start with Windows

Run this in PowerShell from the repo folder:

```powershell
$py = (py -c "import sys; print(sys.executable)") -replace 'python\.exe$', 'pythonw.exe'
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Claude Usage Tray.lnk")
$lnk.TargetPath = $py
$lnk.Arguments = "`"$PWD\main.pyw`""
$lnk.WorkingDirectory = "$PWD"
$lnk.Save()
```

To stop it starting, delete `Claude Usage Tray.lnk` from the folder that opens with `shell:startup`.

## How it works

- Every 5 minutes it reads the access token from `%USERPROFILE%\.claude\.credentials.json`, the file Claude Code keeps, and calls `https://api.anthropic.com/api/oauth/usage`. The token is sent nowhere else.
- It never uses the refresh token. When the access token expires, no new numbers arrive until you use Claude Code again and it refreshes the login.
- Switching accounts in Claude Code needs no restart. The next poll picks up the new account.
- The endpoint is rate limited. Polling once a minute got HTTP 429 after about half an hour, so the default is 5 minutes. On 429 it waits longer before the next try, up to 30 minutes. If a 429 comes right after a successful request, the normal interval doubles for good.
- When a request fails, the icons keep the last numbers and the tooltip shows when they were updated. They turn into a grey `?` only when there is no data or it is over an hour old.
- Right-click an icon for **Refresh now** and **Quit**. A left click also refreshes. Manual refresh is ignored within a minute of the last request and while rate limited.
- Tooltips are in Turkish when Windows is set to Turkish, otherwise in English.
- A log is written to `usage_tray.log` next to the script (rotated at 256 KB).

## License

MIT
