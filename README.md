# ZTE Wi-Fi presence

Home Assistant custom integration: a device is **home** while it is connected to the Wi-Fi of
a ZTE router or mesh unit (tested: F8648P router, H3601P mesh). No third-party code,
standard library only.

Every 30 s it logs into each access point's web interface, reads its Wi-Fi client list and
logs out (F8648P: `wlan_client_stat_lua.lua`, H3601P: `accessdev_ssiddev_lua.lua`; both
are tried). All access points feed one tracker per device; its `access_point` attribute
shows which unit the device is on.

Only Wi-Fi associations count. A unit drops a departed phone from its Wi-Fi list within
~30 s, while the router's LAN client list keeps a phone behind a mesh unit for ~11 minutes
(its address table ages out slowly), so LAN lists are not used.

A device counts as away after it has been missing from every unit for `consider_home`
seconds (default 180). Right after a Home Assistant restart there is no history yet, so a
device that is off Wi-Fi at that moment turns away immediately. If a unit cannot be
reached, presence from that unit is frozen instead of everyone on it turning away. After a
rejected login it stops logging in to that unit until the integration is reloaded, so the
unit does not lock the account; a temporary lock is waited out.

## Credentials

The integration expects the login in the `ZTE_USERNAME` and `ZTE_PASSWORD` environment
variables of the Home Assistant container; it is never stored in Home Assistant. Docker
Compose example:

```yaml
services:
  homeassistant:
    environment:
      ZTE_USERNAME: user
      ZTE_PASSWORD: "password"
```

**Advanced:** if a unit has its own login, add it to `ZTE_CREDENTIALS`, a JSON object keyed
by the unit's address. An entry there is used for that unit instead of `ZTE_USERNAME` /
`ZTE_PASSWORD`:

```yaml
      ZTE_CREDENTIALS: '{"192.168.1.2": {"username": "user", "password": "mesh-password"}}'
```

Use the limited `user` account. These units often allow one web session at a time, so a
browser login may be logged out while the integration polls.

On `https://` addresses the certificate is not verified: these units use self-signed
certificates. The password is never sent as is, only hashed with a one-time login token.

## Install

1. Install the files, either way:
   - **HACS**: HACS → ⋮ → Custom repositories → `https://github.com/capJavert/ha-zte-presence`,
     type **Integration**; then download **ZTE Wi-Fi presence**.
   - **Manually**: copy `custom_components/zte_presence` into the HA config folder
     (`<config>/custom_components/zte_presence`).
2. Set the environment variables, then recreate the container (`docker compose up -d homeassistant`).
3. Settings → Devices & services → Add integration → **ZTE Wi-Fi presence**.
4. Enter the router and mesh unit addresses, then pick the phones to track. Change the
   phones later under the integration's **Configure**, the addresses under **Reconfigure**.

## Development

`python3 tools/probe.py 192.168.1.1` logs in once with the same environment variables and
prints the Wi-Fi clients (name, MAC, IP). Without an argument it uses `ZTE_HOST`, else
`192.168.1.1`. Parser tests: `python3 -m unittest discover tests`.

## License

MIT
