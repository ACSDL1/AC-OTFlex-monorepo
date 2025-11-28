#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gripper slot tuner: edit pick/place/safe_z for slots in an otflex_file JSON.

Usage:
  python tools/gripper_tuner.py --file devices/otflex_deck_default.json

This is a simple text UI to review and edit numbers. It does not move hardware.
"""

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True, help='Path to otflex deck json (otflex_file)')
    args = ap.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding='utf-8'))
    gs = data.setdefault('gripper_slots', {})

    print('Slots available:', ', '.join(sorted(gs.keys())))
    print('Enter commands: list | show <slot> | set <slot> pick x y z | set <slot> place x y z | set <slot> safe_z z | save | quit')
    while True:
        try:
            cmd = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nBye')
            break
        if not cmd:
            continue
        if cmd == 'list':
            for k in sorted(gs.keys()):
                print(k)
            continue
        if cmd.startswith('show '):
            _, slot = cmd.split(maxsplit=1)
            print(json.dumps(gs.get(slot, {}), indent=2))
            continue
        if cmd.startswith('set '):
            parts = cmd.split()
            if len(parts) < 4:
                print('Usage: set <slot> pick|place|safe_z ...')
                continue
            slot, field = parts[1], parts[2]
            rec = gs.setdefault(slot, {})
            if field in ('pick','place'):
                if len(parts) != 6:
                    print('Usage: set <slot> pick|place x y z')
                    continue
                rec[field] = [float(parts[3]), float(parts[4]), float(parts[5])]
            elif field == 'safe_z':
                if len(parts) != 4:
                    print('Usage: set <slot> safe_z z')
                    continue
                rec[field] = float(parts[3])
            else:
                print('Unknown field')
            continue
        if cmd == 'save':
            path.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print('Saved')
            continue
        if cmd in ('quit','exit'): break
        print('Unknown command')

if __name__ == '__main__':
    main()

