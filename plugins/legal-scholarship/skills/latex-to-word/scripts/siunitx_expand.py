# -*- coding: utf-8 -*-
"""Small deterministic renderer for common siunitx inline commands."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


SUPERSCRIPTS = str.maketrans({
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
})


PREFIXES = {
    "kilo": "k",
    "milli": "m",
    "micro": "μ",
    "nano": "n",
    "pico": "p",
    "femto": "f",
    "mega": "M",
    "giga": "G",
    "tera": "T",
    "centi": "c",
    "deci": "d",
    "deca": "da",
    "hecto": "h",
    "atto": "a",
    "zepto": "z",
}


UNITS = {
    "meter": "m",
    "metre": "m",
    "gram": "g",
    "second": "s",
    "kilogram": "kg",
    "mole": "mol",
    "kelvin": "K",
    "ampere": "A",
    "candela": "cd",
    "coulomb": "C",
    "joule": "J",
    "watt": "W",
    "newton": "N",
    "pascal": "Pa",
    "hertz": "Hz",
    "volt": "V",
    "ohm": "Ω",
    "farad": "F",
    "tesla": "T",
    "weber": "Wb",
    "henry": "H",
    "siemens": "S",
    "lumen": "lm",
    "lux": "lx",
    "becquerel": "Bq",
    "gray": "Gy",
    "sievert": "Sv",
    "katal": "kat",
    "liter": "L",
    "litre": "L",
    "radian": "rad",
    "steradian": "sr",
    "degree": "°",
    "percent": "%",
}


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _matching(text: str, open_pos: int, open_char: str, close_char: str) -> int:
    depth = 0
    escaped = False
    for pos in range(open_pos, len(text)):
        ch = text[pos]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return pos
    raise ValueError("unmatched group")


def _read_group(text: str, pos: int) -> tuple[str, int]:
    pos = _skip_ws(text, pos)
    if pos >= len(text) or text[pos] != "{":
        raise ValueError("expected braced group")
    end = _matching(text, pos, "{", "}")
    return text[pos + 1:end], end + 1


def _skip_optional_args(text: str, pos: int) -> int:
    pos = _skip_ws(text, pos)
    while pos < len(text) and text[pos] == "[":
        end = _matching(text, pos, "[", "]")
        pos = _skip_ws(text, end + 1)
    return pos


def superscript(text: str) -> str:
    return str(text).translate(SUPERSCRIPTS)


def format_siunitx_number(value: str) -> str:
    s = value.strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))[eE]([+-]?\d+)", s)
    if not match:
        return s
    mantissa = match.group(1)
    exp = str(int(match.group(2)))
    return rf"{mantissa}×10\textsuperscript{{{exp}}}"


def format_bare_s_number(value: str) -> str:
    s = value.strip()
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+", s):
        return format_siunitx_number(s)
    return value


def format_separate_uncertainty(value: str) -> str:
    s = value.strip()
    match = re.fullmatch(r"([+-]?(?:\d+)(?:\.(\d+))?)\((\d+)\)", s)
    if not match:
        return value
    number = match.group(1)
    fractional = match.group(2) or ""
    digits = match.group(3)
    places = len(fractional)
    try:
        uncertainty = Decimal(digits) * (Decimal(10) ** Decimal(-places))
    except InvalidOperation:
        return value
    if places > 0:
        uncertainty_s = f"{uncertainty:.{places}f}"
    else:
        uncertainty_s = str(uncertainty.quantize(Decimal(1)))
    return f"{number} ± {uncertainty_s}"


def _append_power(result: str, power: str) -> str:
    if not result:
        return result
    return result + superscript(power)


def format_siunitx_unit(unit_tex: str) -> str:
    result = ""
    pending_prefix = ""
    i = 0
    while i < len(unit_tex):
        ch = unit_tex[i]
        if ch.isspace() or ch in "{}":
            i += 1
            continue
        if ch != "\\":
            result += ch
            i += 1
            continue

        match = re.match(r"\\([A-Za-z]+)", unit_tex[i:])
        if not match:
            i += 1
            continue
        name = match.group(1)
        i += match.end()

        if name in PREFIXES:
            pending_prefix = PREFIXES[name]
            continue
        if name == "per":
            result += "/" if result and not result.endswith("/") else "/"
            pending_prefix = ""
            continue
        if name == "squared":
            result = _append_power(result, "2")
            continue
        if name == "cubed":
            result = _append_power(result, "3")
            continue
        if name in {"tothe", "raisetothe"}:
            try:
                power, i = _read_group(unit_tex, i)
            except ValueError:
                power = ""
            if power:
                result = _append_power(result, power.strip())
            continue
        if name == "times":
            result += "×"
            pending_prefix = ""
            continue
        if name in UNITS:
            symbol = UNITS[name]
            if pending_prefix and name not in {"kilogram"}:
                symbol = pending_prefix + symbol
            result += symbol
            pending_prefix = ""
            continue

        pending_prefix = ""
    return result.strip()


def _read_command_name(text: str, pos: int) -> tuple[str, int] | None:
    if pos >= len(text) or text[pos] != "\\":
        return None
    match = re.match(r"\\([A-Za-z]+)", text[pos:])
    if not match:
        return None
    return match.group(1), pos + match.end()


def expand_siunitx_commands(text: str) -> str:
    if not any(token in text for token in (r"\si", r"\SI", r"\num", r"\tablenum", r"\sisetup")):
        return text

    out: list[str] = []
    i = 0
    while i < len(text):
        command = _read_command_name(text, i)
        if command is None:
            out.append(text[i])
            i += 1
            continue

        name, after_name = command
        if name not in {"si", "SI", "num", "tablenum", "sisetup"}:
            out.append(text[i:after_name])
            i = after_name
            continue

        try:
            pos = _skip_optional_args(text, after_name)
            if name == "sisetup":
                _setup, end = _read_group(text, pos)
                i = end
                continue
            if name == "si":
                unit, end = _read_group(text, pos)
                out.append(format_siunitx_unit(unit))
                i = end
                continue
            if name in {"num", "tablenum"}:
                number, end = _read_group(text, pos)
                out.append(format_siunitx_number(number))
                i = end
                continue
            if name == "SI":
                number, pos = _read_group(text, pos)
                unit, end = _read_group(text, pos)
                rendered_unit = format_siunitx_unit(unit)
                rendered_number = format_siunitx_number(number)
                out.append(f"{rendered_number} {rendered_unit}".rstrip())
                i = end
                continue
        except ValueError:
            out.append(text[i:after_name])
            i = after_name
            continue

    return "".join(out)
