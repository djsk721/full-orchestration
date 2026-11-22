"""Extract editable SSH connection values without invoking OpenSSH."""
from __future__ import annotations

import getpass
import glob
import re
import shlex
from fnmatch import fnmatchcase
from heapq import nsmallest
from pathlib import Path


_DIRECTIVE = re.compile(r"\s*([a-z]+)(?:\s*=\s*|\s+)(.+)", re.IGNORECASE)
_ALIAS = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}")
_FIELDS = {"hostname", "user", "port", "identityfile", "proxyjump", "proxycommand"}
_DIRECTIVES = _FIELDS | {"host", "match", "include"}
_TOKEN = re.compile(r"%.")
_FILE_LIMIT = 32
_FILE_BYTES = 128 * 1024
_ALIAS_LIMIT = 256


def _words(value):
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""  # Preserve Windows paths and domain-qualified users.
    return tuple(lexer)


def _home_path(value, home):
    return home / value[2:] if value.startswith(("~/", "~\\")) else Path(value)


def _read_rules(home, root):
    files = 0
    aliases = {}

    def read(path, parents=()):
        nonlocal files
        if files >= _FILE_LIMIT:
            return
        try:
            path = path.resolve()
            if path in parents or not path.is_relative_to(root) or not path.is_file():
                return
            files += 1
            with path.open("rb") as stream:
                source = stream.read(_FILE_BYTES + 1)
            if len(source) > _FILE_BYTES or b"\0" in source:
                return
        except (OSError, ValueError, RuntimeError):
            return

        in_match = False
        for line in source.decode("utf-8-sig", errors="replace").splitlines():
            entry = _DIRECTIVE.fullmatch(line)
            if not entry or entry[1].lower() not in _DIRECTIVES:
                continue
            keyword = entry[1].lower()
            try:
                args = _words(entry[2])
            except ValueError:
                args = ()
            if keyword == "match":
                in_match = True
                yield keyword, None
            elif keyword == "host":
                in_match = False
                for pattern in args:
                    if len(aliases) < _ALIAS_LIMIT and _ALIAS.fullmatch(pattern):
                        aliases.setdefault(pattern.casefold(), pattern)
                yield keyword, args
            elif in_match:
                continue
            elif keyword == "include":
                for pattern in args:
                    candidate = (home / ".ssh") / _home_path(pattern, home)
                    # Use the original home spelling for Include, then verify the resolved file.
                    relative = next((candidate.relative_to(base) for base in (home / ".ssh", root)
                                     if candidate.is_relative_to(base)), None)
                    if files >= _FILE_LIMIT or relative is None or ".." in relative.parts:
                        continue
                    for child in nsmallest(_FILE_LIMIT - files, glob.iglob(str(relative), root_dir=root)):
                        if files >= _FILE_LIMIT:
                            break
                        yield keyword, tuple(read(root / child, (*parents, path)))
            elif args:
                yield keyword, args[0]

    return tuple(read(root / "config")), aliases


def _host_matches(patterns, alias):
    selected = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        pattern = pattern.removeprefix("!").casefold().replace("[", "[[]")
        if fnmatchcase(alias, pattern):
            if negated:
                return False
            selected = True
    return selected


def _resolve(rules, alias, options, identities):
    active = True
    found = False
    for keyword, value in rules:
        if keyword == "host":
            active = _host_matches(value, alias)
            found |= active and any(pattern.casefold() == alias for pattern in value)
        elif keyword == "match":
            active = False
        elif active:
            if keyword == "include":
                found |= _resolve(value, alias, options, identities)
            elif keyword == "identityfile":
                identities.append(value)
            else:
                key = "proxy" if keyword in {"proxyjump", "proxycommand"} else keyword
                options.setdefault(key, value)
    return found


def _identity_path(identities, home, tokens):
    for value in identities:
        if value.casefold() == "none" or "${" in value or any(token not in tokens for token in _TOKEN.findall(value)):
            continue
        path = _home_path(_TOKEN.sub(lambda match: tokens[match[0]], value), home)
        if path.is_absolute():
            return str(path)
    return ""


def local_ssh_hosts(home=None, *, local_user=None):
    """Return literal aliases and direct-connection values from the current user's .ssh."""
    try:
        home = Path.home() if home is None else Path(home).absolute()
        root = (home / ".ssh").resolve()
    except (OSError, RuntimeError):
        return {}
    if local_user is None:
        try:
            local_user = getpass.getuser()
        except (OSError, KeyError):
            local_user = ""
    rules, aliases = _read_rules(home, root)
    hosts = {}
    for needle, alias in aliases.items():
        options, identities = {}, []
        if not _resolve(rules, needle, options, identities):
            continue
        host = _TOKEN.sub(lambda match: {"%h": alias, "%%": "%"}.get(match[0], match[0]),
                          options.get("hostname", alias))
        user, port = options.get("user", local_user), options.get("port", "22")
        tokens = {"%d": str(home), "%h": host, "%n": alias, "%p": port, "%r": user, "%%": "%"}
        hosts[alias] = {"host": host, "user": user, "port": port,
                        "identity": _identity_path(identities, home, tokens),
                        "proxy": options.get("proxy", "none").casefold() != "none"}
    return hosts
