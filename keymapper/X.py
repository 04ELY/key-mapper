#!/usr/bin/python3
# -*- coding: utf-8 -*-
# key-mapper - GUI for device specific keyboard mappings
# Copyright (C) 2020 sezanzeb <proxima@hip70890b.de>
#
# This file is part of key-mapper.
#
# key-mapper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# key-mapper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with key-mapper.  If not, see <https://www.gnu.org/licenses/>.


"""Stuff that interacts with the X Server, be it commands or config files.

TODO create a base class to standardize the interface if a different
  display server should be supported.

Resources:
[1] https://wiki.archlinux.org/index.php/Keyboard_input
[2] http://people.uleth.ca/~daniel.odonnell/Blog/custom-keyboard-in-linuxx11
[3] https://www.x.org/releases/X11R7.7/doc/xorg-docs/input/XKB-Enhancing.html
"""


import os
import re
import subprocess

from keymapper.paths import CONFIG_PATH, SYMBOLS_PATH, KEYCODES_PATH
from keymapper.logger import logger
from keymapper.data import get_data_path
from keymapper.presets import get_presets
from keymapper.linux import get_devices


def get_keycode(device, letter):
    """Get the keycode that is configured for the given letter."""
    # TODO I have no idea how to do this
    # in /usr/share/X11/xkb/keycodes the mapping is made
    return ''


def create_preset(device, name=None):
    """Create an empty preset."""
    existing_names = get_presets(device)
    if name is None:
        name = 'new preset'

    # find a name that is not already taken
    if name in existing_names:
        i = 2
        while f'{name} {i}' in existing_names:
            i += 1
        name = f'{name} {i}'

    create_setxkbmap_config(device, name, [])
    return name


def create_setxkbmap_config(device, preset, mappings):
    """Generate a config file for setxkbmap.

    The file is created in ~/.config/key-mapper/<device>/<preset> and,
    in order to find all presets in the home dir to make backing them up
    more intuitive, a symlink is created in
    /usr/share/X11/xkb/symbols/key-mapper/<device>/<preset> to point to it.
    The file in home doesn't have underscore to be more beautiful on the
    frontend, while the symlink doesn't contain any whitespaces.
    """
    create_identity_mapping()

    config_path = os.path.join(CONFIG_PATH, device, preset)
    # setxkbmap cannot handle spaces
    usr_path = os.path.join(SYMBOLS_PATH, device, preset).replace(' ', '_')

    if not os.path.exists(config_path):
        logger.info('Creating config file "%s"', config_path)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        os.mknod(config_path)
    if not os.path.exists(usr_path):
        logger.info('Creating symlink in "%s"', usr_path)
        os.makedirs(os.path.dirname(usr_path), exist_ok=True)
        os.symlink(config_path, usr_path)

    logger.info('Writing key mappings')
    with open(config_path, 'w') as f:
        f.write(generate_symbols_file_content(device, preset, mappings))


def apply_preset(device, preset):
    """Apply a preset to the device."""
    # apply it to every device that hangs on the same usb port, because I
    # have no idea how to figure out which one of those 3 devices that are
    # all named after my mouse to use.
    device_underscored = device.replace(' ', '_')
    preset_underscored = preset.replace(' ', '_')

    group = get_devices()[device]

    for xinput_name, xinput_id in get_xinput_id_mapping():
        if xinput_name not in group['devices']:
            continue
        layout_name = (
            'key-mapper'
            f'/{device_underscored}'
            f'/{preset_underscored}'
        )
        cmd = [
            'setxkbmap',
            '-layout', layout_name,
            '-keycodes', 'key-mapper',
            '-device', str(xinput_id)
        ]
        logger.debug('Running `%s`', ' '.join(cmd))
        subprocess.run(cmd)


def create_identity_mapping():
    """Because the concept of "reasonable symbolic names" [3] doesn't apply
    when mouse buttons are all over the place. Create an identity mapping
    to make generating "symbols" files easier. Keycode 10 -> "<10>"

    This has the added benefit that keycodes reported by xev can be
    identified in the symbols file.
    """
    # TODO don't create this again if it already exists, as soon as this
    #   stuff is stable.

    xkb_keycodes = []
    # the maximum specified in /usr/share/X11/xkb/keycodes is usually 255
    # and the minimum 8
    maximum = 255
    minimum = 8
    for code in range(minimum, maximum + 1):
        xkb_keycodes.append(f'<{code}> = {code};')

    template_path = os.path.join(get_data_path(), 'xkb_keycodes_template')
    with open(template_path, 'r') as template_file:
        template = template_file.read()

    result = template.format(
        minimum=minimum,
        maximum=maximum,
        xkb_keycodes='\n    '.join(xkb_keycodes)
    )

    logger.info('Creating "%s"', KEYCODES_PATH)
    with open(KEYCODES_PATH, 'w') as keycodes:
        keycodes.write(result)


def generate_symbols_file_content(device, preset, mappings):
    """Create config contents to be placed in /usr/share/X11/xkb/symbols.

    Parameters
    ----------
    device : string
    preset : string
    mappings : array
        tuples of code, character
    """
    system_default = 'us'  # TODO get the system default

    # If the symbols file contains key codes that are not present in
    # the keycodes file, THE WHOLE X SESSION WILL CRASH!
    if not os.path.exists(KEYCODES_PATH):
        raise ValueError('Expected the keycodes file to exist.')
    with open(KEYCODES_PATH, 'r') as f:
        keycodes = re.findall(r'<.+?>', f.read())

    xkb_symbols = []
    for code, character in mappings:
        if f'<{code}>' not in keycodes:
            logger.error(f'Unknown keycode <{code}> for "{character}"')
        xkb_symbols.append(f'key <{code}> {{ [ {character} ] }};')

    template_path = os.path.join(get_data_path(), 'xkb_symbols_template')
    with open(template_path, 'r') as template_file:
        template = template_file.read()

    result = template.format(
        name=f'{device}/{preset}',
        xkb_symbols='\n    '.join(xkb_symbols),
        system_default=system_default
    )

    return result


def get_xinput_id_mapping():
    """Run xinput and get a list of name, id tuplies.

    The ids are needed for setxkbmap. There might be duplicate names with
    different ids.
    """
    names = subprocess.check_output(
        ['xinput', 'list', '--name-only']
    ).decode().split('\n')
    ids = subprocess.check_output(
        ['xinput', 'list', '--id-only']
    ).decode().split('\n')

    names = [name for name in names if name != '']
    ids = [int(id) for id in ids if id != '']
    return zip(names, ids)