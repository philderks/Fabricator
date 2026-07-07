---
title: playit.gg tunnels
description: Expose Minecraft servers through playit.gg without router port forwarding.
---

Fabricator can run a shared [playit.gg](https://playit.gg/) tunnel agent so friends can join your Minecraft servers without router port forwarding or inbound firewall rules.

The tunnel agent is global for the Fabricator host, but public addresses are shown per server by matching each playit tunnel's local port to the server's Minecraft port.

## Requirements

- Linux host. The playit integration is not available on Windows.
- A Fabricator install that includes the bundled `playit` and `playit-cli` binaries.
- Outbound HTTPS access to `playit.gg` and `api.playit.gg`.
- A playit.gg account for the one-time agent claim.

The packaged installer downloads pinned playit-agent binaries for supported Linux architectures and verifies their sha256 checksums. If verification fails or the architecture is unsupported, Fabricator still installs, but the playit tab shows a warning or a missing-binary error.

## Enable the tunnel agent

1. Open a server in the dashboard.
2. Select **playit.gg** in the server sidebar.
3. Click **Enable playit.gg**.
4. Open the claim link shown by Fabricator.
5. Sign in to, or sign up for, playit.gg and approve the agent.

After the claim succeeds, Fabricator starts the playit agent and keeps polling for tunnel status. The enabled state is persisted, so a tunnel enabled from the dashboard starts again after a Fabricator service restart.

:::note
The playit.gg controls manage one shared agent for all servers on the Fabricator host. Disabling or resetting playit.gg from any server's tab affects every server that depends on that agent.
:::

## Create a tunnel for a server

When the agent is running, Fabricator looks for a playit tunnel whose local port matches the selected server's Minecraft port, for example `25565`.

If no matching tunnel exists yet:

1. Open the link to the playit.gg dashboard from the **playit.gg** tab.
2. Create a tunnel that forwards to the Fabricator host and the server's local Minecraft port.
3. Wait a few seconds for Fabricator to refresh the tunnel list.

When a matching tunnel has a public address, Fabricator shows it in **This server's public address** with a copy button.

## Status states

| State | Meaning |
| --- | --- |
| `stopped` | The playit agent is not running. |
| `starting` | Fabricator is launching the agent. |
| `claiming` | A claim link is waiting for account approval. |
| `running` | The agent is active and Fabricator is reading tunnel data. |
| `error` | The agent failed; the UI shows the reason and retry/reset actions. |
| `unsupported` | The current platform does not support the playit integration. |

Tunnel data is read from playit's rundata API. If the API is temporarily unreachable, Fabricator keeps the agent status visible and reports that it cannot confirm the selected server's tunnel yet.

## Disable or reset playit.gg

Use **Disable** to stop the shared agent while keeping the saved playit account secret. Use **Reset** to stop the agent and remove the saved secret, forcing a fresh claim on the next enable.

Reset is useful when:

- You want to switch to a different playit.gg account.
- The agent was deleted or revoked in the playit.gg dashboard.
- playit.gg rejects the saved secret.

## Configuration

Packaged installs include these environment variables in `/etc/fabricator/fabricator.env`:

```ini
PLAYIT_ENABLED=false
PLAYIT_BINARY_VERIFIED=true
```

`PLAYIT_ENABLED=true` starts the agent automatically on boot when no dashboard-persisted state file exists. In normal use, prefer the dashboard toggle; it writes the desired state for future restarts.

`PLAYIT_BINARY_VERIFIED` is written by the installer after sha256 verification. The backend exposes it to the UI so operators can see when playit binaries were not verified during install or update.

Advanced/dev installs may set `PLAYIT_RUNTIME_DIR` to choose where Fabricator stores playit runtime files such as the secret, socket, PID file, and enabled-state marker. Packaged installs use `/var/lib/fabricator/playit`.

## Troubleshooting

- **Binary missing:** rerun the installer or place `playit` and `playit-cli` on `PATH` or in `/usr/local/bin`.
- **Signature unverified warning:** check installer/update logs. The tunnel may still work, but the current binaries were not verified by Fabricator's pinned checksums.
- **No tunnel for this port:** create a playit.gg tunnel whose local port equals the server's Minecraft port.
- **Agent limit or disabled agent:** remove unused agents or check the agent state in the playit.gg dashboard, then use **Reset** if needed.
- **Public address not shown yet:** wait for the rundata poller to refresh. If the message persists, verify outbound access to `api.playit.gg`.
