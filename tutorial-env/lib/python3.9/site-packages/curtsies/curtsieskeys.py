"""All the key sequences"""
# If you add a binding, add something about your setup
# if you can figure out why it's different

# Special names are for multi-character keys, or key names
# that would be hard to write in a config file

# TODO add PAD keys hack as in bpython.cli

# fmt: off
CURTSIES_NAMES = {
    b' ':          '<SPACE>',
    b'\x1b ':      '<Esc+SPACE>',
    b'\t':         '<TAB>',
    b'\x1b[Z':     '<Shift-TAB>',
    b'\x1b[A':     '<UP>',
    b'\x1b[B':     '<DOWN>',
    b'\x1b[C':     '<RIGHT>',
    b'\x1b[D':     '<LEFT>',
    b'\x1bOA':     '<UP>',         # in issue 92 its shown these should be normal arrows,
    b'\x1bOB':     '<DOWN>',       # not ctrl-arrows as we previously had them.
    b'\x1bOC':     '<RIGHT>',
    b'\x1bOD':     '<LEFT>',

    b'\x1b[1;5A':  '<Ctrl-UP>',
    b'\x1b[1;5B':  '<Ctrl-DOWN>',
    b'\x1b[1;5C':  '<Ctrl-RIGHT>', # reported by myint
    b'\x1b[1;5D':  '<Ctrl-LEFT>',  # reported by myint

    b'\x1b[5A':    '<Ctrl-UP>',    # not sure about these, someone wanted them for bpython
    b'\x1b[5B':    '<Ctrl-DOWN>',
    b'\x1b[5C':    '<Ctrl-RIGHT>',
    b'\x1b[5D':    '<Ctrl-LEFT>',

    b'\x1b[1;9A':  '<Esc+UP>',
    b'\x1b[1;9B':  '<Esc+DOWN>',
    b'\x1b[1;9C':  '<Esc+RIGHT>',
    b'\x1b[1;9D':  '<Esc+LEFT>',

    b'\x1b[1;10A': '<Esc+Shift-UP>',
    b'\x1b[1;10B': '<Esc+Shift-DOWN>',
    b'\x1b[1;10C': '<Esc+Shift-RIGHT>',
    b'\x1b[1;10D': '<Esc+Shift-LEFT>',

    b'\x1bOP':     '<F1>',
    b'\x1bOQ':     '<F2>',
    b'\x1bOR':     '<F3>',
    b'\x1bOS':     '<F4>',

    # see bpython #626
    b'\x1b[11~':   '<F1>',
    b'\x1b[12~':   '<F2>',
    b'\x1b[13~':   '<F3>',
    b'\x1b[14~':   '<F4>',

    b'\x1b[15~':   '<F5>',
    b'\x1b[17~':   '<F6>',
    b'\x1b[18~':   '<F7>',
    b'\x1b[19~':   '<F8>',
    b'\x1b[20~':   '<F9>',
    b'\x1b[21~':   '<F10>',
    b'\x1b[23~':   '<F11>',
    b'\x1b[24~':   '<F12>',
    b'\x00':       '<Ctrl-SPACE>',
    b'\x1c':       '<Ctrl-\\>',
    b'\x1d':       '<Ctrl-]>',
    b'\x1e':       '<Ctrl-6>',
    b'\x1f':       '<Ctrl-/>',
    b'\x7f':       '<BACKSPACE>',    # for some folks this is ctrl-backspace apparently
    b'\x1b\x7f':   '<Esc+BACKSPACE>',
    b'\xff':       '<Meta-BACKSPACE>',
    b'\x1b\x1b[A': '<Esc+UP>',    # uncertain about these four
    b'\x1b\x1b[B': '<Esc+DOWN>',
    b'\x1b\x1b[C': '<Esc+RIGHT>',
    b'\x1b\x1b[D': '<Esc+LEFT>',
    b'\x1b':       '<ESC>',
    b'\x1b[1~':    '<HOME>',
    b'\x1b[4~':    '<END>',
    b'\x1b\x1b[5~':'<Esc+PAGEUP>',
    b'\x1b\x1b[6~':'<Esc+PAGEDOWN>',

    b'\x1b[H':     '<HOME>',    # reported by amorozov in bpython #490
    b'\x1b[F':     '<END>',     # reported by amorozov in bpython #490

    b'\x1bOH':     '<HOME>',    # reported by mixmastamyk in curtsies #78
    b'\x1bOF':     '<END>',     # reported by mixmastamyk in curtsies #78

    # not fixing for back compat.
    # (b"\x1b[1~": u'<FIND>',       # find

    b"\x1b[2~": '<INSERT>',       # insert (0)
    b"\x1b[3~": '<DELETE>',       # delete (.), "Execute"
    b"\x1b[3;5~": '<Ctrl-DELETE>',

    # st (simple terminal) see issue #169
    b"\x1b[4h": '<INSERT>',
    b"\x1b[P": '<DELETE>',

    # not fixing for back compat.
    # (b"\x1b[4~": u'<SELECT>',       # select

    b"\x1b[5~": '<PAGEUP>',       # pgup   (9)
    b"\x1b[6~": '<PAGEDOWN>',     # pgdown (3)
    b"\x1b[7~": '<HOME>',         # home
    b"\x1b[8~": '<END>',          # end
    b"\x1b[OA": '<UP>',           # up     (8)
    b"\x1b[OB": '<DOWN>',         # down   (2)
    b"\x1b[OC": '<RIGHT>',        # right  (6)
    b"\x1b[OD": '<LEFT>',         # left   (4)
    b"\x1b[OF": '<END>',          # end    (1)
    b"\x1b[OH": '<HOME>',         # home   (7)

    # reported by cool-RR
    b"\x1b[[A": '<F1>',
    b"\x1b[[B": '<F2>',
    b"\x1b[[C": '<F3>',
    b"\x1b[[D": '<F4>',
    b"\x1b[[E": '<F5>',
    # cool-RR says the rest were good: see issue #99

    # reported by alethiophile see issue #119
    b"\x1b[1;3C": '<Meta-RIGHT>',      # alt-right
    b"\x1b[1;3B": '<Meta-DOWN>',       # alt-down
    b"\x1b[1;3D": '<Meta-LEFT>',       # alt-left
    b"\x1b[1;3A": '<Meta-UP>',         # alt-up
    b"\x1b[5;3~": '<Meta-PAGEUP>',     # alt-pageup
    b"\x1b[6;3~": '<Meta-PAGEDOWN>',   # alt-pagedown
    b"\x1b[1;3H": '<Meta-HOME>',       # alt-home
    b"\x1b[1;3F": '<Meta-END>',        # alt-end
    b"\x1b[1;2C": '<Shift-RIGHT>',
    b"\x1b[1;2B": '<Shift-RIGHT>',
    b"\x1b[1;2D": '<Shift-RIGHT>',
    b"\x1b[1;2A": '<Shift-RIGHT>',
    b"\x1b[3;2~": '<Shift-DELETE>',
    b"\x1b[5;2~": '<Shift-PAGEUP>',
    b"\x1b[6;2~": '<Shift-PAGEDOWN>',
    b"\x1b[1;2H": '<Shift-HOME>',
    b"\x1b[1;2F": '<Shift-END>',
    # end of keys reported by alethiophile
}
# fmt: on
