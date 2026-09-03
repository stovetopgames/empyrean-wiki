"""Parsers for Pokemon Essentials v17 PBS text files."""
import csv
import io
import os
import re


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8-sig", "replace").replace("\r\n", "\n").replace("\r", "\n")


def read_csv_rows(path):
    """Yield non-comment CSV rows, honouring quoted fields containing commas."""
    text = read_text(path)
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield next(csv.reader(io.StringIO(line)))


def read_sections(path):
    """Parse `[section]` + `Key=Value` files into [(section, {key: value})]."""
    out = []
    cur = None
    for line in read_text(path).split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = (m.group(1), {})
            out.append(cur)
            continue
        if cur is None or "=" not in line:
            continue
        k, _, v = line.partition("=")
        cur[1][k.strip()] = v.strip()
    return out


def read_list_sections(path):
    """Parse `[section]` + comma-separated payload lines (tm.txt style).

    Returns [(section, [entries], heading)] where heading is the most recent
    `# Heading` banner comment, which tm.txt uses to group TMs vs tutors.
    """
    out = []
    cur = None
    heading = None
    prev_was_rule = False
    for line in read_text(path).split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if set(line) <= set("#=- "):
                prev_was_rule = True
            elif prev_was_rule and body:
                heading = body
                prev_was_rule = False
            continue
        prev_was_rule = False
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = (m.group(1), [], heading)
            out.append(cur)
            continue
        if cur is not None:
            cur[1].extend(x.strip() for x in line.split(",") if x.strip())
    return out


STAT_ORDER = ["hp", "attack", "defense", "speed", "spatk", "spdef"]


def split_ints(s):
    return [int(x) for x in s.split(",") if x.strip() != ""]


def titlecase_name(internal):
    return internal.replace("_", " ").title()
