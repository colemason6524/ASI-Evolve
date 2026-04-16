# Kalshi Collector VM Setup

This collector is best run on an always-on Linux VM, not a laptop. `tmux` is great for interactive monitoring, but the process that stays alive across reboots should be `systemd`.

## Recommended model

- Use your laptop for coding, testing, and one-off `collect-once` checks.
- Use a small Ubuntu VM for continuous collection.
- Use `tmux` when you want to attach, inspect logs, or run temporary commands.
- Use `systemd` for the always-on collector loop.

## 1. Provision the VM

Install the basics:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv tmux
```

Clone the repo:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/colemason6524/ASI-Evolve.git ultimate_ai
sudo chown -R "$USER":"$USER" /opt/ultimate_ai
cd /opt/ultimate_ai
```

## 2. Create a Python environment

```bash
cd /opt/ultimate_ai
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If you only want the Kalshi collector pieces and not the heavier package set, install the minimum dependencies you need into the VM environment instead.

## 3. Initialize collector storage

```bash
cd /opt/ultimate_ai
source .venv/bin/activate
python3 -m kalshi_research.main init-watchlist \
  --dataset-root /opt/ultimate_ai/data/kalshi \
  --watchlist-path /opt/ultimate_ai/data/kalshi/watchlist.json
```

## 4. Manual `tmux` workflow

Create a session:

```bash
tmux new -s kalshi
```

Inside `tmux`, run:

```bash
cd /opt/ultimate_ai
source .venv/bin/activate
PYTHON_BIN=/opt/ultimate_ai/.venv/bin/python3 \
INTERVAL_SECONDS=300 \
./scripts/run_kalshi_collector.sh
```

Helpful `tmux` commands:

- Detach: `Ctrl-b d`
- Reattach: `tmux attach -t kalshi`
- List sessions: `tmux ls`

This is useful for testing, but it still depends on you restarting it after VM reboot unless you also install the service below.

## 5. Install the `systemd` service

Copy the service file:

```bash
sudo cp /opt/ultimate_ai/deploy/systemd/kalshi-collector.service /etc/systemd/system/kalshi-collector.service
```

Update the service if needed:

- `User=...`
- `WorkingDirectory=...`
- `DATASET_ROOT=...`
- `WATCHLIST_PATH=...`
- `INTERVAL_SECONDS=...`

If you created a virtualenv, point the service at it by editing:

```ini
Environment=PYTHON_BIN=/opt/ultimate_ai/.venv/bin/python3
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kalshi-collector
sudo systemctl start kalshi-collector
```

Check status:

```bash
sudo systemctl status kalshi-collector
journalctl -u kalshi-collector -f
```

## 6. Recommended operating pattern

- Let `systemd` own the always-on collector.
- Use `tmux` for:
  - `dataset-summary`
  - ad hoc `collect-once`
  - inspecting raw files and logs
  - temporary debug runs

## 7. Important files

- Collector entrypoint: `/opt/ultimate_ai/scripts/run_kalshi_collector.sh`
- Service template: `/opt/ultimate_ai/deploy/systemd/kalshi-collector.service`
- Data root: `/opt/ultimate_ai/data/kalshi`
- CLI summary:

```bash
python3 -m kalshi_research.main dataset-summary --dataset-root /opt/ultimate_ai/data/kalshi
```

## 8. Suggested next improvement

Once the VM is stable, add a second lightweight backup job that syncs `/opt/ultimate_ai/data/kalshi` to cloud storage or another machine so the research dataset survives VM loss.
