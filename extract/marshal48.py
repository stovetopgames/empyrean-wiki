"""Minimal Ruby Marshal 4.8 reader, sufficient for RPG Maker XP .rxdata files."""


class RObj:
    __slots__ = ("cls", "ivars")

    def __init__(self, cls):
        self.cls = cls
        self.ivars = {}

    def __repr__(self):
        return "<%s %s>" % (self.cls, sorted(self.ivars)[:6])


class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0
        self.objects = []
        self.symbols = []

    def byte(self):
        b = self.d[self.i]
        self.i += 1
        return b

    def long(self):
        c = self.byte()
        if c == 0:
            return 0
        sc = c - 256 if c > 127 else c
        if sc > 0:
            if sc > 4:
                return sc - 5
            n = 0
            for k in range(sc):
                n |= self.byte() << (8 * k)
            return n
        if sc < -4:
            return sc + 5
        n = -1
        for k in range(-sc):
            n &= ~(0xFF << (8 * k))
            n |= self.byte() << (8 * k)
        return n

    def _key(self, k):
        if isinstance(k, tuple):
            return k[1]
        if isinstance(k, bytes):
            return k.decode("utf-8", "replace")
        return k

    def read(self):
        t = chr(self.byte())
        if t == "0":
            return None
        if t == "T":
            return True
        if t == "F":
            return False
        if t == "i":
            return self.long()
        if t == ":":
            n = self.long()
            s = self.d[self.i:self.i + n].decode("utf-8", "replace")
            self.i += n
            self.symbols.append(s)
            return ("SYM", s)
        if t == ";":
            return ("SYM", self.symbols[self.long()])
        if t == "@":
            return self.objects[self.long()]
        if t == '"':
            n = self.long()
            s = self.d[self.i:self.i + n]
            self.i += n
            self.objects.append(s)
            return s
        if t == "[":
            n = self.long()
            a = []
            self.objects.append(a)
            for _ in range(n):
                a.append(self.read())
            return a
        if t == "{":
            n = self.long()
            h = {}
            self.objects.append(h)
            for _ in range(n):
                k = self.read()
                h[self._key(k)] = self.read()
            return h
        if t == "o":
            cls = self.read()[1]
            o = RObj(cls)
            self.objects.append(o)
            for _ in range(self.long()):
                k = self.read()[1]
                o.ivars[k.lstrip("@")] = self.read()
            return o
        if t == "u":
            cls = self.read()[1]
            n = self.long()
            o = RObj(cls)
            o.ivars["_raw"] = self.d[self.i:self.i + n]
            self.i += n
            self.objects.append(o)
            return o
        if t == "I":
            v = self.read()
            for _ in range(self.long()):
                self.read()
                self.read()
            return v
        if t == "l":
            sign = chr(self.byte())
            n = self.long() * 2
            raw = self.d[self.i:self.i + n]
            self.i += n
            v = int.from_bytes(raw, "little")
            return -v if sign == "-" else v
        if t == "f":
            n = self.long()
            s = self.d[self.i:self.i + n]
            self.i += n
            self.objects.append(s)
            try:
                return float(s)
            except ValueError:
                return 0.0
        raise ValueError("unhandled Marshal type %r at offset %d" % (t, self.i))


def load(path):
    with open(path, "rb") as fh:
        d = fh.read()
    if d[0] != 4 or d[1] != 8:
        raise ValueError("not Marshal 4.8: %s" % path)
    r = Reader(d)
    r.i = 2
    return r.read()
