# bifrost-agent

Mac path-tunnel agent for [Bifrost](https://github.com/eskeon/go-bifrost). Connects outbound over WebSocket and exposes a local HTTP app under `/services/{slug}`.

## Install

```bash
pip install bifrost-agent
```

Requires Python 3.11+.

## Connect

1. In Bifrost Console → **Tunnels**, create a tunnel and attach a path route (set **Local URL** there, e.g. `http://127.0.0.1:3000`).
2. Copy the one-time install command and run:

```bash
sudo bifrost tunnel install <token>
```

The token embeds the Bifrost WebSocket URL and auth secret. Local upstream URLs are **not** passed on the CLI — they come from the console on each request.

## Commands

```bash
sudo bifrost tunnel install <token>   # LaunchDaemon + system config
bifrost tunnel run                    # foreground (uses saved config)
bifrost tunnel run <token>            # one-shot / save user config + run
sudo bifrost tunnel uninstall
bifrost version
```

System config: `/Library/Application Support/bifrost/config.json`  
Logs: `/Library/Logs/bifrost-tunnel.log`

## Develop

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
bifrost version
```

## Publish

Repo: https://github.com/eskeon/bifrost-agent  

Tag a release (`v*`); GitHub Actions builds and publishes to PyPI as `bifrost-agent`.
