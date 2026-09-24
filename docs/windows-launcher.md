# Windows launcher and ChatGPT connection

Phase 9 provides local Streamable HTTP on `127.0.0.1:18765` and a PowerShell launcher that starts ngrok after a real local MCP handshake. Public ngrok and ChatGPT connections have **not** been verified yet. The fixed telemetry directory is `D:\Steam\steamapps\common\Le Mans Ultimate\UserData\Telemetry`.

## Install and start

From `D:\duckdbtoparquet` in PowerShell, install the Python package into the project virtual environment (see [README](../README.md)) and install [ngrok](https://ngrok.com/docs/getting-started/). Configure its authtoken locally with `ngrok config add-authtoken <your-token>`. The launcher checks `ngrok version` and `ngrok config check`; these do not prove the account can create a tunnel.

Run `& .\startLeMansMCP.ps1`. The script uses `.venv\Scripts\python.exe`, checks the fixed telemetry root and ports 18765 and 4040, starts the loopback server, completes an MCP handshake, then starts ngrok with the project's Host rewrite policy. It prints the full HTTPS MCP URL, including a private path, once the local ngrok API reports a tunnel. Keep the terminal open while ChatGPT uses it; press Ctrl+C to stop the server and tunnel started by this launcher. If a port is occupied, the launcher fails without killing the existing listener or choosing another port.

A fresh terminal does not know the `startLeMansMCP` function until you load it. To make the command available **in this terminal only**, run the following first (it loads the function without starting the server):

```powershell
. 'D:\duckdbtoparquet\startLeMansMCP-profile.ps1'
Get-Command startLeMansMCP
```

Then run `startLeMansMCP` when you want to start the local server and ngrok tunnel. PowerShell command names are case-insensitive; `startLemansMCP` also works after the function is loaded.

To make the function available in future PowerShell terminals, review [the profile function](../startLeMansMCP-profile.ps1) and confirm its `D:\duckdbtoparquet` path. From this project directory, install it **once** into your PowerShell profile:

```powershell
New-Item -ItemType Directory -Path (Split-Path -Parent $PROFILE) -Force | Out-Null
Get-Content .\startLeMansMCP-profile.ps1 | Add-Content -Path $PROFILE
```

The checked-in function calls this project's launcher; the profile is not changed automatically. Start a new PowerShell terminal and run `startLeMansMCP`. Repeating the installation command would duplicate the function text in the profile.

## Connect ChatGPT

In ChatGPT, follow [OpenAI's MCP connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt) for your account's developer mode and connector setup. Paste the **full** printed HTTPS URL ending in `/mcp`, then inspect the discovered tools. Availability and UI labels can depend on the ChatGPT account or workspace. The recommended coaching sequence is [session discovery through bounded detail](progressive-querying.md).

The full URL is a bearer secret: anyone who has it can query the read-only server's recorded telemetry while the tunnel is up. It has no user accounts. Do not paste the URL into issues, logs or Git; share it only with the ChatGPT connection you choose. Stop the launcher when done. The random path persists in ignored `.runtime/private-path.txt` so restarting the launcher retains the same path. To revoke it, stop the launcher, run `.\.venv\Scripts\lmu-mcp.exe rotate-secret` from the project directory, restart and update the ChatGPT connection. The HTTPS hostname may change if ngrok assigns a new one.

The server preserves MCP Host/Origin validation. ngrok uses [a request-header traffic policy](https://ngrok.com/docs/universal-gateway/examples/ollama) to set the upstream Host to `127.0.0.1:18765`; the ngrok `--inspect=false` option disables HTTP introspection. The server disables its HTTP access log and binds only to loopback. The ngrok API on `127.0.0.1:4040` is used only to discover the public HTTPS origin. The launcher hides its owned child windows and closes only those children on failure or Ctrl+C.

## Troubleshooting

- **Missing telemetry directory:** verify the LMU telemetry location is installed at the fixed path. The application does not search for alternatives.
- **Missing `.venv` or package:** run the README installation command; the launcher uses the project virtual environment.
- **`ngrok` unavailable or configuration invalid:** install ngrok, add it to PATH, configure the local authtoken and run `ngrok config check`.
- **Port 18765 or 4040 occupied:** stop the program using that port yourself, then retry. The launcher will not stop it.
- **Server did not become ready:** run `.\.venv\Scripts\lmu-mcp.exe serve` locally to see the server error. It stays quiet when healthy; stop it before starting the launcher.
- **ngrok exited or no HTTPS tunnel appeared:** verify authentication, account limits and connectivity with ngrok's own commands. The launcher suppresses child logs to avoid recording the private path.
- **ChatGPT does not discover tools:** confirm the full URL includes the private path and `/mcp`, the launcher is running, and your ChatGPT account supports the connector workflow. A local health response alone does not prove a remote MCP handshake.

Local fixed-port MCP initialization and tool calls have passed. Launcher process-order, cleanup, occupied-port and tunnel-discovery tests use synthetic substitutes. A public tunnel test and an actual ChatGPT test remain open and must be reported separately.
