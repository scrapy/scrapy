# -*- coding: utf-8 -*-
"""
    sphinx.util.texescape
    ~~~~~~~~~~~~~~~~~~~~~

    TeX escaping helper.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from __future__ import unicode_literals

tex_replacements = [
    # map TeX special chars
    ('$', r'\$'),
    ('%', r'\%'),
    ('&', r'\&'),
    ('#', r'\#'),
    ('_', r'\_'),
    ('{', r'\{'),
    ('}', r'\}'),
    ('[', r'{[}'),
    (']', r'{]}'),
    ('`', r'{}`'),
    ('\\', r'\textbackslash{}'),
    ('~', r'\textasciitilde{}'),
    ('<', r'\textless{}'),
    ('>', r'\textgreater{}'),
    ('^', r'\textasciicircum{}'),
    # map special Unicode characters to TeX commands
    ('¶', r'\P{}'),
    ('§', r'\S{}'),
    ('€', r'\texteuro{}'),
    ('∞', r'\(\infty\)'),
    ('±', r'\(\pm\)'),
    ('→', r'\(\rightarrow\)'),
    ('‣', r'\(\rightarrow\)'),
    ('✓', r'\(\checkmark\)'),
    # used to separate -- in options
    ('﻿', r'{}'),
    # map some special Unicode characters to similar ASCII ones
    ('─', r'-'),
    ('⎽', r'\_'),
    ('╲', r'\textbackslash{}'),
    ('|', r'\textbar{}'),
    ('│', r'\textbar{}'),
    ('ℯ', r'e'),
    ('ⅈ', r'i'),
    ('⁰', r'$^\text{0}$'),
    ('¹', r'$^\text{1}$'),
    ('²', r'$^\text{2}$'),
    ('³', r'$^\text{3}$'),
    ('⁴', r'$^\text{4}$'),
    ('⁵', r'$^\text{5}$'),
    ('⁶', r'$^\text{6}$'),
    ('⁷', r'$^\text{7}$'),
    ('⁸', r'$^\text{8}$'),
    ('⁹', r'$^\text{9}$'),
    ('₀', r'$_\text{0}$'),
    ('₁', r'$_\text{1}$'),
    ('₂', r'$_\text{2}$'),
    ('₃', r'$_\text{3}$'),
    ('₄', r'$_\text{4}$'),
    ('₅', r'$_\text{5}$'),
    ('₆', r'$_\text{6}$'),
    ('₇', r'$_\text{7}$'),
    ('₈', r'$_\text{8}$'),
    ('₉', r'$_\text{9}$'),
    # map Greek alphabet
    ('α', r'\(\alpha\)'),
    ('β', r'\(\beta\)'),
    ('γ', r'\(\gamma\)'),
    ('δ', r'\(\delta\)'),
    ('ε', r'\(\epsilon\)'),
    ('ζ', r'\(\zeta\)'),
    ('η', r'\(\eta\)'),
    ('θ', r'\(\theta\)'),
    ('ι', r'\(\iota\)'),
    ('κ', r'\(\kappa\)'),
    ('λ', r'\(\lambda\)'),
    ('μ', r'\(\mu\)'),
    ('ν', r'\(\nu\)'),
    ('ξ', r'\(\xi\)'),
    ('ο', r'o'),
    ('π', r'\(\pi\)'),
    ('ρ', r'\(\rho\)'),
    ('σ', r'\(\sigma\)'),
    ('τ', r'\(\tau\)'),
    ('υ', '\\(\\upsilon\\)'),
    ('φ', r'\(\phi\)'),
    ('χ', r'\(\chi\)'),
    ('ψ', r'\(\psi\)'),
    ('ω', r'\(\omega\)'),
    ('Α', r'A'),
    ('Β', r'B'),
    ('Γ', r'\(\Gamma\)'),
    ('Δ', r'\(\Delta\)'),
    ('Ε', r'E'),
    ('Ζ', r'Z'),
    ('Η', r'H'),
    ('Θ', r'\(\Theta\)'),
    ('Ι', r'I'),
    ('Κ', r'K'),
    ('Λ', r'\(\Lambda\)'),
    ('Μ', r'M'),
    ('Ν', r'N'),
    ('Ξ', r'\(\Xi\)'),
    ('Ο', r'O'),
    ('Π', r'\(\Pi\)'),
    ('Ρ', r'P'),
    ('Σ', r'\(\Sigma\)'),
    ('Τ', r'T'),
    ('Υ', '\\(\\Upsilon\\)'),
    ('Φ', r'\(\Phi\)'),
    ('Χ', r'X'),
    ('Ψ', r'\(\Psi\)'),
    ('Ω', r'\(\Omega\)'),
    ('Ω', r'\(\Omega\)'),
]

tex_escape_map = {}
tex_replace_map = {}
tex_hl_escape_map_new = {}


def init():
    for a, b in tex_replacements:
        tex_escape_map[ord(a)] = b
        tex_replace_map[ord(a)] = '_'

    for a, b in tex_replacements:
        if a in '[]{}\\':
            continue
        tex_hl_escape_map_new[ord(a)] = b
