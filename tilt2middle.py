#!/usr/bin/env python3
"""
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
"""

import argparse
import glob
import os
import select
import signal
import sys
import time

import evdev
from evdev import UInput, ecodes as e

DEFAULT_LEFT = 0x113   # BTN_SIDE
DEFAULT_RIGHT = 0x114  # BTN_EXTRA
DEBOUNCE = 0.15        # seconds to keep holding after the last tilt activity
# Horizontal (tilt) wheel signals. Modern mice emit the hi-res flavour (0x0c);
# legacy REL_HWHEEL (0x06) is swallowed too so nothing leaks to apps.
WHEEL_CODES = {e.REL_HWHEEL, e.REL_HWHEEL_HI_RES}


UDEV_RULE = 'KERNEL=="event[0-9]*", SUBSYSTEM=="input", ACTION=="add", TAG+="uaccess"'
UDEV_INSTALL = """sudo tee /etc/udev/rules.d/99-uinput-uaccess.rules >/dev/null <<'EOF'
%s
EOF
sudo udevadm control --reload
sudo udevadm trigger
""" % UDEV_RULE


def virtual_node_path(name: str) -> str:
    """Find /dev/input/eventN for a freshly created uinput device by its name."""
    for _ in range(80):
        for p in glob.glob("/sys/class/input/event*/device/name"):
            try:
                with open(p) as f:
                    if f.read().strip() == name:
                        node = "/dev/input/" + p.split("/")[-3]
                        if os.path.exists(node):
                            return node
            except OSError:
                continue
        time.sleep(0.05)
    return None


def warn_virtual_unreadable(node: str) -> None:
    sys.stderr.write(
        f"WARNING: the desktop cannot read the virtual device {node} - "
        "the remap will not reach it.\n"
        "Install the uaccess udev rule once (as root), then rerun:\n\n"
        + UDEV_INSTALL + "\n"
    )


def parse_code(text: str) -> int:
    text = str(text).strip()
    if text.isdigit():
        return int(text)
    if text.lower().startswith("0x"):
        return int(text, 16)
    for candidate in (text.upper(), "BTN_" + text.upper(), "KEY_" + text.upper()):
        if hasattr(e, candidate):
            return getattr(e, candidate)
    raise SystemExit(f"cannot parse evdev code: {text!r}")


def fmt(code: int, evtype: int = e.EV_KEY) -> str:
    table = {e.EV_KEY: e.KEY, e.EV_REL: e.REL, e.EV_ABS: e.ABS}.get(evtype, e.KEY)
    name = table.get(code)
    return f"{name} (0x{code:x})" if name else f"0x{code:x}"


def button_codes(dev) -> list:
    keys = dev.capabilities(verbose=False).get(e.EV_KEY, [])
    return sorted(c for c in keys if isinstance(c, int) and e.BTN_MOUSE <= c <= 0x117)


def list_devices() -> None:
    print(f"{'PATH':<22}{'NAME':<36} BUTTONS / REL")
    found = False
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        caps = dev.capabilities(verbose=False)
        btns = [fmt(c) for c in button_codes(dev)]
        rels = [fmt(c, e.EV_REL) for c in caps.get(e.EV_REL, []) if isinstance(c, int)]
        if not (btns or rels):
            dev.close()
            continue
        found = True
        desc = ", ".join(btns + (["| "] if btns and rels else []) + rels)
        print(f"{path:<22}{dev.name[:36]:<36} {desc}")
        dev.close()
    if not found:
        print("No readable input devices (need root or 'input' group).")


def find_device_keys(needed: set) -> tuple:
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        keys = set(dev.capabilities(verbose=False).get(e.EV_KEY, []))
        if needed.issubset(keys):
            return dev, path
        dev.close()
    return None, None


def find_device_rel(relcodes: set) -> tuple:
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        caps = dev.capabilities(verbose=False)
        rels = set(rel for rel in caps.get(e.EV_REL, []) if isinstance(rel, int))
        if relcodes & rels:
            keys = set(caps.get(e.EV_KEY, []))
            if e.BTN_LEFT in keys:  # prefer the pointer interface, not the media-keys one
                return dev, path
        dev.close()
    return None, None


def fail_search(need_txt: str) -> None:
    sys.stderr.write(f"Auto-detect failed: no device with {need_txt}.\n")
    sys.stderr.write("Run `--list` or `--identify` to inspect your devices.\n")
    raise SystemExit(2)


def identify(args) -> None:
    if args.device:
        src = evdev.InputDevice(args.device)
    else:
        sources = []
        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                d = evdev.InputDevice(path)
            except OSError:
                continue
            caps = d.capabilities(verbose=False)
            if button_codes(d) or caps.get(e.EV_REL, []):
                sources.append(d)
        if not sources:
            raise SystemExit("no readable input devices (need root or 'input' group)")
        src = max(sources, key=lambda d: len(button_codes(d)) +
                  len(d.capabilities(verbose=False).get(e.EV_REL, [])))
    print(f"Listening on {src.name} (not grabbed - events go to the desktop too).")
    print("Tilt the wheel left/right and press buttons. Ctrl-C to stop.")
    try:
        while True:
            ready, _, _ = select.select([src], [], [], 0.2)
            if not ready:
                continue
            for ev in src.read():
                if ev.type in (e.EV_KEY, e.EV_REL):
                    print(f"{ev.timestamp():.3f}  {'EV_KEY' if ev.type == e.EV_KEY else 'EV_REL':<7} "
                          f"{fmt(ev.code, ev.type):<24} value={ev.value}")
    except KeyboardInterrupt:
        print()


def build_events(src, swallowed_keys=set(), swallowed_rels=set()) -> dict:
    caps = src.capabilities(verbose=False)
    events = {}
    for evtype in (e.EV_KEY, e.EV_REL):
        codes = [c for c in caps.get(evtype, []) if isinstance(c, int)]
        if evtype == e.EV_KEY:
            codes = [c for c in codes if c not in swallowed_keys]
        elif evtype == e.EV_REL:
            codes = [c for c in codes if c not in swallowed_rels]
        if evtype == e.EV_KEY and codes and e.BTN_MIDDLE not in codes:
            codes.append(e.BTN_MIDDLE)
        if codes:
            events[evtype] = sorted(codes)
    if not events:
        events = {e.EV_KEY: [e.BTN_MIDDLE]}
    return events


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="tilt2middle",
        description=("Remap mouse tilt-left/right (horizontal wheel or buttons) "
                     "to a debounced middle click."),
        epilog="Exit: Ctrl-C.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--list", action="store_true", help="list devices and their capabilities")
    ap.add_argument("--identify", action="store_true",
                    help="print live events from the device so you can find the tilt signals")
    ap.add_argument("--device", metavar="PATH", help="/dev/input/eventN to use (skip auto-detect)")
    ap.add_argument("--buttons", action="store_true",
                    help="treat tilt as button events instead of REL_HWHEEL")
    ap.add_argument("--udev-rule", action="store_true",
                    help="print the udev rule granting the desktop access to virtual devices")
    ap.add_argument("--left", default="0x113", metavar="CODE",
                    help="tilt-left button code (only with --buttons)")
    ap.add_argument("--right", default="0x114", metavar="CODE",
                    help="tilt-right button code (only with --buttons)")
    ap.add_argument("--debounce", type=float, default=DEBOUNCE,
                    help="seconds to keep middle held after the last tilt signal")
    ap.add_argument("--verbose", action="store_true", help="log remap decisions")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return 0
    if args.identify:
        identify(args)
        return 0
    if args.udev_rule:
        print(UDEV_RULE)
        return 0

    if args.debounce < 0.02:
        raise SystemExit("--debounce must be >= 0.02 seconds")

    wheel_mode = not args.buttons
    middle = e.BTN_MIDDLE

    if wheel_mode:
        src, path = (evdev.InputDevice(args.device), args.device) if args.device else \
            find_device_rel(WHEEL_CODES)
        if src is None:
            fail_search(f"REL_HWHEEL / REL_HWHEEL_HI_RES (horizontal wheel tilt)")
        swallowed_keys, swallowed_rels = set(), set(WHEEL_CODES)
        trigger_txt = "REL_HWHEEL_HI_RES / REL_HWHEEL (horizontal tilt)"
    else:
        left, right = parse_code(args.left), parse_code(args.right)
        if left == right:
            raise SystemExit("tilt left and right buttons must differ")
        tilt_codes = {left, right}
        src, path = (evdev.InputDevice(args.device), args.device) if args.device else \
            find_device_keys(tilt_codes)
        if src is None:
            fail_search(f"both buttons {[fmt(c) for c in tilt_codes]}")
        swallowed_keys, swallowed_rels = set(tilt_codes), set()
        trigger_txt = f"{fmt(left)} / {fmt(right)}"

    print(f"Device: {src.name}")

    try:
        src.grab()
    except OSError as exc:
        raise SystemExit(f"cannot grab {src.name}: {exc}\n(another process holds it, or no permission)")

    ui = UInput(events=build_events(src, swallowed_keys, swallowed_rels),
                name="tilt2middle", version=1)
    vnode = virtual_node_path("tilt2middle")
    if vnode:
        try:
            evdev.InputDevice(vnode).close()
        except OSError:
            warn_virtual_unreadable(vnode)
    print(f"Remapping {trigger_txt} -> middle button")
    print(f"Hold deadzone: {args.debounce:g}s  (Ctrl-C to quit)")

    pressed = {}
    hold = False
    virtual_pressed = False
    last_activity = 0.0
    poll_timeout = min(args.debounce, 0.05)

    running = True

    def stop(_sig, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def middle_set(state: bool):
        nonlocal virtual_pressed
        if state and not virtual_pressed:
            ui.write(e.EV_KEY, middle, 1)
            ui.syn()
            virtual_pressed = True
        elif not state and virtual_pressed:
            ui.write(e.EV_KEY, middle, 0)
            ui.syn()
            virtual_pressed = False

    def is_tilt(ev) -> bool:
        if wheel_mode:
            return ev.type == e.EV_REL and ev.code in WHEEL_CODES
        return ev.type == e.EV_KEY and ev.code in pressed

    try:
        while running:
            ready, _, _ = select.select([src], [], [], poll_timeout)
            if not ready:
                now = time.monotonic()
                if hold and not any(pressed.values()) and now - last_activity >= args.debounce:
                    middle_set(False)
                    hold = False
                    if args.verbose:
                        print("deadzone passed: middle released")
                continue

            try:
                batch = src.read()
            except (BlockingIOError, OSError):
                continue

            for ev in batch:
                if is_tilt(ev):
                    now = time.monotonic()
                    if not wheel_mode:
                        if ev.value != 0:
                            pressed[ev.code] = True
                        else:
                            pressed[ev.code] = False
                    if not hold:
                        middle_set(True)
                        hold = True
                        if args.verbose:
                            print(f"tilt {fmt(ev.code, ev.type)} -> middle held")
                    last_activity = now
                    continue

                if ev.type == e.EV_KEY and ev.code == middle:
                    if hold:
                        continue  # swallow physical middle events while we hold
                    if ev.value and not virtual_pressed:
                        middle_set(True)
                    elif not ev.value and virtual_pressed:
                        middle_set(False)
                    continue

                ui.write(ev.type, ev.code, ev.value)
            ui.syn()
    finally:
        if hold or virtual_pressed:
            middle_set(False)
        try:
            src.ungrab()
        except Exception:
            pass
        ui.close()
        print("exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())