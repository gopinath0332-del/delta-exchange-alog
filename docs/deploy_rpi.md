# Raspberry Pi Deployment Guide

This guide explains how to deploy the Delta Exchange Trading Bot to a Raspberry Pi 4 (or any Linux server) for 24/7 operation.

## Prerequisites

- Raspberry Pi (Delta Exchange Bot requires Python 3.8+)
- Internet Connection
- Access via SSH

## Step 1: Preparation

1.  **Clone the Repository**:

    ```bash
    cd /home/pi
    git clone <your-repo-url> delta-exchange-alog
    cd delta-exchange-alog
    ```

2.  **Install Dependencies**:

    ```bash
    # Create virtual environment (avoids PEP 668 error)
    python3 -m venv venv

    # Activate and install
    source venv/bin/activate
    pip install -r requirements.txt
    ```

    _Note: `dearpygui` is NOT needed for terminal mode, so if it fails to install on RPi (which uses ARM architecture), you can ignore it or remove it from `requirements.txt`._

3.  **Configure Environment**:
    Copy your `.env` file to the config directory:
    ```bash
    cp config/.env.example config/.env
    nano config/.env
    ```
    Fill in your API keys, Discord Webhook, and Email settings.

## Step 2: Verification

Test the bot manually first:

```bash
# Run interactively
python3 run_terminal.py

# Run non-interactively (Terminal Mode)
python3 -u run_terminal.py --strategy 1 --non-interactive
```

Ensure it starts and sends the "Strategy Started" notification. Press `Ctrl+C` to stop.

## Step 3: Setup Systemd Service

To run 24/7, we use `systemd`.

1.  **Edit Service File**:
    Check the provided `delta-bot.service` file. Ensure paths match your installation (default assumes `User=pi` and path `/home/pi/delta-exchange-alog`).

    ```bash
    nano delta-bot.service
    ```

2.  **Install Service**:

    ```bash
    sudo cp delta-bot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    ```

3.  **Enable and Start**:
    ```bash
    sudo systemctl enable delta-bot.service
    sudo systemctl start delta-bot.service
    ```

## Step 4: Maintenance

- **Check Status**: `sudo systemctl status delta-bot.service`
- **View Logs**: `journalctl -u delta-bot.service -f` or check `logs/service.log`
- **Stop**: `sudo systemctl stop delta-bot.service`
- **Restart**: `sudo systemctl restart delta-bot.service`

## Troubleshooting

- **Permission Errors**: Ensure the `User` in service file owns the directory (`chown -R pi:pi /home/pi/delta-exchange-alog`).
- **Python Path**: Verify python path with `which python3`.
