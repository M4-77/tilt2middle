# tilt2middle
basically i accidentally superglued my middle mouse button so i wanted to rebind to the side scrolling middle mouse buttons but those sent a jitter signal so this basically deadzones that to fix the jitter and rebinds side scroll to middle mouse button

tilt2middle - remap mouse tilt-wheel activity (horizontal scroll / tilt-left +
tilt-right buttons) to a single middle-mouse button, with a debounce "deadzone".

On many mice the tilt wheel does NOT send clean buttons - e.g. the Logitech G502
sends a burst of REL_HWHEEL pulses (+/-120) that bounce/jitter at the press and
release edges. Remapping those 1:1 to middle clicks makes it flicker. This tool
instead keeps the middle button HELD while tilt activity is arriving, and only
releases it once --debounce seconds have passed with no tilt activity at all.

Default mode intercepts REL_HWHEEL (horizontal wheel). Use --buttons if your
mouse reports the tilt as real buttons instead (e.g. BTN_SIDE / BTN_EXTRA).

###############################################################################
# HOW TO INSTALL (run once after a fresh OS install):
#
# 1) Dependencies (Arch/CachyOS):
#        sudo pacman -S python-evdev
#
# 2) Grant the desktop read access to the virtual device this tool creates.
#    This is required for the remap to actually reach your apps. One time:
#        python3 tilt2middle.py --udev-rule | sudo tee /etc/udev/rules.d/99-uinput-uaccess.rules >/dev/null
#        sudo udevadm control --reload && sudo udevadm trigger
#
# 3) Test it works before installing the service:
#        python3 tilt2middle.py --identify   # tilt the wheel, confirm REL codes
#        python3 tilt2middle.py --verbose    # tilt -> middle button held
#    Tilt left/right should produce a held middle click, released after the
#    debounce deadzone (default 0.15s, tweak with --debounce).
#
# 4) Auto-start with a systemd USER service (no root needed to run it):
#        mkdir -p ~/.config/systemd/user
#        # save the service below as ~/.config/systemd/user/tilt2middle.service:
#        systemctl --user daemon-reload
#        systemctl --user enable --now tilt2middle.service
#    Path used on this machine: /home/matt/.config/systemd/user/tilt2middle.service
#    Logs / status:
#        journalctl --user -u tilt2middle -f
#        systemctl --user status tilt2middle
#
#    Service file contents:
#        [Unit]
#        Description=Tilt wheel to middle-mouse remap
#        After=graphical-session.target
#        [Service]
#        ExecStart=/usr/bin/python3 /home/matt/tilt2middle.py
#        Restart=on-failure
#        [Install]
#        WantedBy=graphical-session.target
#
# 5) Tuning:
#        --debounce 0.2   longer hold if the button still flickers
#        --left/--right   button codes instead of wheel pulses (with --buttons)
#        --device         force a specific /dev/input/eventN
#
# NOTE: if the script prints "WARNING: the desktop cannot read the virtual
# device", step 2 was not done (the compositor never sees the remapped input).
###############################################################################

Requires read/write on the device and /dev/uinput (root, or the 'input'+'uinput'
groups / udev ACLs - normally granted to the active session user).

The uinput VIRTUAL device it creates is usually NOT readable by your desktop
(likewise keyd's). If the script exits with an access warning, install one udev
rule (as root) and reload udev - see `--udev-rule`.

Usage:
    python3 tilt2middle.py [--device /dev/input/eventN] [--debounce 0.15] [--verbose]
    python3 tilt2middle.py --buttons --left BTN_SIDE --right BTN_EXTRA
    python3 tilt2middle.py --identify      # print live events to find the tilt codes
    python3 tilt2middle.py --udev-rule     # print the access rule to install
    python3 tilt2middle.py --list          # show devices and their capabilities


DISCLAIMER: I DID NOT WRITE THIS. CLAUDE DID, THIS IS VIBECODED!!!! (claude was running locally though dont worry it wasnt through datacentres) BUT STILL DONT TAKE THIS AS MY WORK!!!!!!! I DIDNT MAKE THIS!!!!!!!!!! RAHH!!!!!!!!!! 
