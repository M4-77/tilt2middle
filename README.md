tilt2middle

A small Linux utility that remaps mouse tilt-wheel input to the middle mouse button, with a configurable debounce/deadzone to prevent jitter.

# Why?

I accidentally superglued my middle mouse button. 

I wanted to use my mouse's side-scrolling/tilt buttons as a replacement, but my Logitech G502 doesn't send clean button presses. Instead, the tilt wheel produces bursts of REL_HWHEEL events that can bounce around the press/release edges.

Remapping those events directly causes the middle mouse button to flicker.

tilt2middle solves this by treating tilt activity as a single held middle-click:

    Tilt left/right → middle mouse button pressed

    More tilt activity → middle button stays held

    No tilt activity for --debounce seconds → middle button released

By default, it listens for REL_HWHEEL events. It can also handle mice that expose tilt as actual buttons such as BTN_SIDE and BTN_EXTRA.
Installation
1. Install dependencies

On Arch/CachyOS:

sudo pacman -S python-evdev

2. Allow your desktop to read the virtual device

tilt2middle creates a virtual input device through /dev/uinput. Your desktop/compositor may not have permission to read it by default.

Generate and install the required udev rule:

python3 tilt2middle.py --udev-rule | sudo tee /etc/udev/rules.d/99-uinput-uaccess.rules >/dev/null
sudo udevadm control --reload
sudo udevadm trigger

This only needs to be done once.
3. Test it

First, identify what your mouse sends when the wheel is tilted:

python3 tilt2middle.py --identify

Then run the remapper:

python3 tilt2middle.py --verbose

Tilting the wheel should now act as a middle mouse button. The button remains held while tilt events are being received and is released after the debounce period.

The default debounce is 0.15 seconds.
4. Start automatically with systemd

Create the user service directory:

mkdir -p ~/.config/systemd/user

Save the following as:

~/.config/systemd/user/tilt2middle.service

[Unit]
Description=Tilt wheel to middle-mouse remap
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /home/matt/tilt2middle.py
Restart=on-failure

[Install]
WantedBy=graphical-session.target

Then enable it:

systemctl --user daemon-reload
systemctl --user enable --now tilt2middle.service

Check its status:

systemctl --user status tilt2middle

View logs:

journalctl --user -u tilt2middle -f

    Note: Update the ExecStart path if tilt2middle.py is somewhere other than /home/matt/tilt2middle.py.

Usage

Basic usage:

python3 tilt2middle.py

Specify a device and debounce time:

python3 tilt2middle.py --device /dev/input/eventN --debounce 0.2

Enable verbose output:

python3 tilt2middle.py --verbose

Identify input events:

python3 tilt2middle.py --identify

List input devices and capabilities:

python3 tilt2middle.py --list

Mice that report tilt as buttons

If your mouse reports tilt as actual buttons instead of REL_HWHEEL:

python3 tilt2middle.py --buttons --left BTN_SIDE --right BTN_EXTRA

Tuning

If the middle button releases too quickly or the input is still jittery, increase the debounce time:

python3 tilt2middle.py --debounce 0.2

Other useful options:

    --device — manually select a /dev/input/eventN device

    --debounce — time to wait after the last tilt event before releasing middle-click

    --buttons — use button events instead of REL_HWHEEL

    --left / --right — specify the button codes when using --buttons

    --verbose — print input/output events

    --identify — monitor live input events

    --list — list input devices and capabilities

    --udev-rule — print the udev rule required for desktop access

Permissions

The script needs access to the input device and /dev/uinput.

Depending on your system, this may require root privileges, membership in the input/uinput groups, or appropriate udev ACLs.

The virtual device created by uinput is typically not readable by the desktop by default. If the script reports:

WARNING: the desktop cannot read the virtual device

install the udev rule using:

python3 tilt2middle.py --udev-rule

and follow the installation instructions above.
Disclaimer

I did not write this.

This is completely vibecoded. Claude wrote the actual code for me — Claude was running locally, so at least it wasn't being sent off to some datacenter to think about my stupid mouse button.

Please do not mistake this repository for my programming ability. I DID NOT MAKE THIS. RAHHH.
