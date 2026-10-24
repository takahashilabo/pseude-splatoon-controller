# Splatoon Dummy Bot Controller (for Raspberry Pi 4)

A system that **simulates human-like dummy input (paint & advance, swim & hide, look around, jump shots, etc.)** to prevent the "no-input" penalty (forced disconnect / matchmaking restriction) during a Splatoon match.

Just boot up a Raspberry Pi 4, and you can **start/stop the dummy operation with one tap from your phone (Safari / Chrome)**. It pairs directly with the Switch over Bluetooth, so **no USB cable is required at all**.

---

## How it works

```
【Your phone】
  │ (open a browser over Wi-Fi)
  ▼
【Raspberry Pi 4】 ───(Bluetooth / NXBT)───> 【Nintendo Switch】
  ・Web controller UI                          ・Paired directly as a Pro Controller
  ・Human-like AI input engine                 ・Wireless input, no cable needed
```

1. **No cable, fully wireless**: Using the Raspberry Pi 4's built-in Bluetooth and the `NXBT` library, it pairs directly with the Switch as a Pro Controller. Your real Pro Controller can stay connected to the Switch the whole time, coexisting as a separate controller.
2. **Intuitive control from your phone**: The phone screen shows "START / STOP" and the real-time stick position.
3. **Relays the real Pro Controller's gyro (motion aiming) too**: A custom patch in `nxbt_patches/` is applied to nxbt itself, relaying the real Pro Controller's gyro/accelerometer data (`/dev/input/eventX`) to the Switch in real time (stock nxbt has no such feature).
4. **Bot-detection countermeasures**:
   - Not just random noise — a purposeful behavior state machine: "paint & advance → squid-swim hide → look around → jump shot."
   - Finger inertia (linear interpolation / lerp) keeps stick movement smooth instead of jerky.
   - Gaussian noise adds subtle hand-tremor and irregular timing variation.

---

## Required hardware

1. **Raspberry Pi 4** (a model with built-in Bluetooth; Pi 3/3B+/400/Zero W/Zero 2 W etc. with Bluetooth also work)
2. **A microSD card (32GB recommended) or a USB flash drive / external SSD (32GB+)**
   - The Pi 4 supports booting from USB storage. Since Raspberry Pi has no power button, the power often gets cut forcibly — **if you want to avoid filesystem corruption from sudden power loss, running from a USB SSD is recommended** (microSD cards use cheap controllers and are known to be prone to corruption if power is cut mid-write).
3. **A USB-C power adapter** (to power the Pi 4)

---

## Setup

### Step 1: Flash the OS onto the microSD card
1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on your PC.
2. Choose **Raspberry Pi 4** as the device and **Raspberry Pi OS (64-bit, Lite recommended)** as the OS.
3. In the settings (gear icon), configure:
   - Hostname: `raspberrypi`
   - Username and password
   - **Wi-Fi settings** (your home or phone's tethering Wi-Fi)
   - **Enable SSH**
4. Flash the microSD card, insert it into the Raspberry Pi 4, and power it on.

### Step 2: Deploy the code and run the fully automated install
From the PC where you cloned this repository, transfer the files to the Pi with `deploy.sh` (you'll be prompted for the password):
```bash
./deploy.sh [user@host]   # defaults to joho@raspberrypi.local
```

SSH into the Pi and run the automated setup:
```bash
ssh <username>@raspberrypi.local
cd pseude-splatoon-controller
sudo ./setup.sh
```
(`setup.sh` installs the required packages and also automatically applies the gyro-relay patch from `nxbt_patches/` to the nxbt package itself.)

Once setup finishes, reboot as instructed:
```bash
sudo reboot
```
*From then on, simply powering on the Pi will automatically put it into Bluetooth pairing-wait mode and bring up the web server.*

> **Important**: We've confirmed that running `sudo apt full-upgrade` or `sudo rpi-eeprom-update` after setup can, depending on the environment, destabilize the onboard Bluetooth via kernel/driver updates (e.g. `Unexpected continuation frame` errors). Once things are working, avoid these upgrades unless you have a specific reason to run them.

---

## Usage (relay mode — no need to turn off your Pro Controller!)

```
【Real Pro Controller】
       │ (Bluetooth pairing)
       ▼
【Raspberry Pi 4】 ───(Bluetooth / NXBT)───> 【Nintendo Switch (P1)】
  ・Normally: Pro Controller input passes straight through to the Switch
  ・On handoff: tap "START BOT" on your phone to cut the Pro Controller and switch to dummy input
       ▲
       │ (Wi-Fi)
【Your phone】
```

1. **First time only: pair the Pi 4 with the Switch**
   - Boot the Pi 4 while the Switch's "Controllers" → "Change Grip/Order" screen is open.
   - `NXBT` pairs automatically, and the Switch recognizes it as a "Pro Controller" (it will auto-reconnect afterward via `reconnect_address`).
2. **Connect the real Pro Controller to the Pi (play as usual)**
   - Pair the real Pro Controller to the Pi over Bluetooth (or connect it via USB).
   - The Pi passes the Pro Controller's input straight through to the Switch via NXBT, so you can **play Splatoon exactly as normal**.
3. **When you need to step away for a moment**
   - **Open `http://raspberrypi.local` in your phone's browser**
   - **Just tap the big【START BOT】button!**
   - The Pro Controller's input is automatically cut off, and **the Switch sees the handoff to dummy input as if the player never stopped playing**. No cable swapping, no Switch grip-confirmation screen, nothing.
4. **When you're back**
   - Tap【STOP BOT】on your phone to immediately return to Pro Controller control and resume playing.

> **Note**: Since a single Bluetooth adapter on the Raspberry Pi 4 handles both "reading the real Pro Controller (host role)" and "acting as a Pro Controller to the Switch (peripheral role)" at the same time, the connection may become unstable in some environments. If it's unstable, consider adding a second USB Bluetooth adapter to separate the two roles.

---

## Preview / dry run on a Mac

Before you have a Raspberry Pi, you can try out the phone control screen and the AI's behavior directly on a Mac.

```bash
# Start the preview server
python3 run_local_preview.py
```
A browser opens automatically, showing the phone control screen.
Press "START BOT" and you'll see the stick movement and button input simulated in real time.

---

## Operational note: shutting down safely

Since the Raspberry Pi has no power button, it's tempting to just pull the power cable — but **cutting power mid-write can corrupt the SD card / USB storage's filesystem** (this risk increases a lot if SSH is flaky and you end up forcing power cuts repeatedly).

- Whenever possible, run `sudo shutdown -h now` (full stop) or `sudo reboot` (restart) over SSH before cutting/pulling power.
- If the green activity LED was blinking right after boot but then **goes completely dark and stops responding**, the OS has likely crashed. If the same thing happens again after a reboot, consider re-flashing the storage.
- For reliability, consider switching from a microSD card to **booting from a USB SSD** instead (the Pi 4 supports booting from USB storage).
- Before going into production use, enabling `sudo raspi-config` → Performance Options → Overlay File System eliminates almost all SD-card writes during normal operation, making it much more resistant to corruption from a hard power-off (leave it disabled while you're still developing).

---

## Troubleshooting

### Can't pair with the Switch
1. **Check whether Bluetooth is blocked by rfkill**:
   ```bash
   bluetoothctl show
   ```
   If you see `Powered: no` / `PowerState: off-blocked`:
   ```bash
   sudo rfkill unblock bluetooth
   sudo systemctl restart bluetooth
   sudo systemctl restart splatoon-controller.service
   ```
2. **If `Discoverable: yes` but the Switch still can't find it**, the `ISCAN` (inquiry scan) flag may not actually be set at the HCI level:
   ```bash
   hciconfig hci0 -a
   ```
   If `PSCAN` is present but `ISCAN` is missing:
   ```bash
   sudo hciconfig hci0 piscan
   ```
3. **If another Bluetooth device (e.g. your phone) also can't find the Pi**, it's an issue with the onboard Bluetooth hardware itself. Rebooting the Pi sometimes fixes it. If not, consider using a USB Bluetooth dongle instead.
4. If it's still not working, on the Switch go to **Settings → System → Controllers and Sensors → Disconnect pairing info for all wireless controllers**, then try pairing again.

### `systemctl restart` hangs for a long time
When Bluetooth is misbehaving, the shutdown cleanup (nxbt's teardown) can get stuck on a Bluetooth D-Bus call, causing `systemctl restart` to hang for close to 90 seconds. Resolve the Bluetooth issue above first.
