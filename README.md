# bifrost-agent

Mac path-tunnel agent for [Bifrost](https://github.com/eskeon/go-bifrost). Connects outbound over WebSocket and exposes a local HTTP app under Bifrost’s tunnels base path (default `/tunnels/{slug}`).

## Install

```bash
pipx install bifrost-agent
# or: pip install bifrost-agent  (inside a venv)
```

Requires Python 3.11+.

## Connect

1. In Bifrost Console → **Tunnels**, create a tunnel and attach a path route (set **Local URL** there, e.g. `http://127.0.0.1:3000`).
2. Copy the one-time install command and run:

```bash
sudo bifrost tunnel install <token>
```

The token embeds the Bifrost WebSocket URL and auth secret. Local upstream URLs are **not** passed on the CLI — they come from the console on each request.

You can install **multiple** tokens on one Mac; each gets its own LaunchDaemon and instance id.

## Commands

```bash
sudo bifrost tunnel install <token>     # add/replace one instance
bifrost tunnel list                     # id, state, url, logs path
bifrost tunnel logs <id>                # last lines of that instance
bifrost tunnel logs <id> -f             # follow logs
sudo bifrost tunnel uninstall <id>      # remove one instance
sudo bifrost tunnel uninstall --all     # remove every instance
bifrost version
```

`list` example:

```text
a1b2c3d4e5f6
  state:   ● running
  url:     wss://bifrost.enfeca.cloud/api/v1/tunnel/connect
  logs:    /Library/Logs/bifrost-tunnel-a1b2c3d4e5f6.log
```

State uses a green ● when the LaunchDaemon is running, red ● when stopped.

Per-instance paths:

- Config: `/Library/Application Support/bifrost/instances/<id>/config.json`
- Logs: `/Library/Logs/bifrost-tunnel-<id>.log`
- LaunchDaemon: `com.bifrost.tunnel.<id>`

A pre-0.2.0 install appears as instance id `legacy`.

## Develop

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
bifrost version
bifrost tunnel list
```

## Publish

Repo: https://github.com/eskeon/bifrost-agent  

Tag a release (`v*`); GitHub Actions builds and publishes to PyPI as `bifrost-agent`.
