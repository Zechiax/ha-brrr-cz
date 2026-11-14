# Brrr.cz Cloud Sensors for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for [Brrr.cz](https://brrr.cz/) cloud temperature/humidity sensors and thermostat relays.

## Features

- **Automatic Account Discovery**: Automatically discovers all temperature sensors (`ts`), humidity sensors (`hs`), and thermostat relays (`relay`) in your Brrr.cz account using a single bulk JSON request.
- **Smart Authentication Input**: Enter either your 32-character MD5 account hash (`kod`) or paste the full request URL copied from browser DevTools.
- **Entities**:
  - **Sensors**: Temperature (°C), Humidity (%), Supply Voltage (V), Last Report Age (min), Target Temperature (°C) for relays.
  - **Binary Sensors**: Cloud Status (connectivity), Expert Mode Invoice Due (problem), Thermostat Relay State (power).
- **UI Configuration & Options**: Configurable polling interval (60–3600 seconds, default 180 seconds) via Config Flow and Options Flow.
- **Languages**: English and Czech (`en`, `cs`).

## Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add `https://github.com/Zechiax/ha-brrr-cz` with category **Integration**.
4. Search for **Brrr.cz Cloud Sensors** and click **Download**.
5. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/brrr_cz` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Brrr.cz**.
3. Enter your **Account Hash (`kod`) or Full API URL**:
   - Either paste just the 32-character MD5 hash (`kod`), which automatically builds `https://brrr.cz/brrr.php?runpagephp=afterlogin&kod={hash}`, **or**
   - Paste the full JSON request URL (`https://brrr.cz/brrr.php?runpagephp=afterlogin&kod=...`) from your browser's DevTools (`Network` tab) while logged into Brrr.cz.
4. Adjust the polling interval if desired (default: `180` seconds).
