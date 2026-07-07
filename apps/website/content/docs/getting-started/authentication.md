---
title: Authentication
description: Configure Fabricator's built-in operator login and first-boot setup flow.
---

Fabricator includes a built-in single-operator login. It is enabled by default for both native and Docker installs.

## First boot setup

On first boot, when no credential exists yet, Fabricator enters setup mode and redirects every dashboard route to `/setup`. Create the operator password there. Until setup completes, only the setup and auth-status endpoints are reachable.

The first password must be at least 8 characters. After setup, the browser session is logged in automatically.

:::caution[Trust-on-first-use]
The setup page is reachable by anyone who can reach the dashboard until the password is set. If Fabricator is exposed on an untrusted network before you can complete setup, configure `FABRICATOR_AUTH_PASSWORD_HASH` before first start instead.
:::

## Stored credentials and session key

Fabricator stores auth state in `auth.json` next to `servers.json`:

| Install type | Path |
| --- | --- |
| Native systemd | `/var/lib/fabricator/auth.json` |
| Docker | `/data/auth.json` |

The file contains the hashed operator password and the session `SECRET_KEY`. Fabricator writes it with `0600` permissions where POSIX file modes are available.

Precedence is:

- Password: `FABRICATOR_AUTH_PASSWORD_HASH` environment variable, then `auth.json`, then setup mode.
- Session key: `SECRET_KEY` environment variable, then `auth.json`, then generated on first boot.

## Declarative password setup

For automation, generate a password hash and place it in the environment before starting Fabricator.

Native install:

```bash
fabricator hash-password
```

Docker or source checkout:

```bash
python -m backend.auth hash
```

Then set:

```ini
FABRICATOR_AUTH_PASSWORD_HASH=<generated-hash>
```

When the password is env-managed, the dashboard cannot change it because the environment value always wins. Replace the env var and restart Fabricator to rotate it.

## Changing or resetting the password

When the password is stored in `auth.json`, use **Change password** in the dashboard header. You must enter the current password.

If you are locked out, stop Fabricator, delete `auth.json`, and start it again. Fabricator returns to setup mode so you can create a new password. This resets only the login/session state; server data remains untouched.

## Disabling built-in auth

Disable auth only if another trusted layer protects Fabricator, such as reverse-proxy SSO, VPN-only access, or a private firewall:

```ini
FABRICATOR_DISABLE_AUTH=1
```

For browser access through HTTPS, set the session cookie's `Secure` flag:

```ini
FABRICATOR_SESSION_COOKIE_SECURE=1
```

Do this only when TLS is terminated in front of Fabricator; plain HTTP access will not receive Secure cookies.
