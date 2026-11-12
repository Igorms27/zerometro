"""The Witcher 3 (PC): descomprime o .sav (LZ4) e lê os "facts" das missões."""
import base64
import glob
import os
import re
import struct

from . import paths

ID, NAME, PLATFORM = "w3", "The Witcher 3", "PC"
STEAM_APPID = "292030"
LABELS = {"base": "História principal", "hos": "Hearts of Stone", "baw": "Blood and Wine"}


def save_dirs():
    out = []
    for docs in paths.documents_dirs():
        out.append(os.path.join(docs, "The Witcher 3", "gamesaves"))
    return out

# ---------- leitura do save ----------

def lz4_block(src, out):
    i, n = 0, len(src)
    while i < n:
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        if off >= ml:
            out += out[start:start + ml]
        else:
            for k in range(ml):
                out.append(out[start + k])


def decompress(data):
    if data[:8] != b"SNFHFZLC":
        raise ValueError("not_w3_save")
    count, pos = struct.unpack_from("<II", data, 8)
    out = bytearray()
    for c in range(count):
        cs, _ds, _end = struct.unpack_from("<III", data, 16 + c * 12)
        # os blocos ficam em sequência; o 3º campo nem sempre bate com o arquivo
        lz4_block(data[pos:pos + cs], out); pos += cs
    return bytes(out)


FACT_RE = re.compile(rb"([\x81-\xff])([A-Za-z0-9_ \-]{1,127})\x00\x00([\x01-\x20])\x00")


def read_facts(b):
    facts = {}
    for m in FACT_RE.finditer(b):
        name = m.group(2)
        if len(name) != (m.group(1)[0] & 0x7F):
            continue
        p, ok, max_t, v = m.end(), True, -1.0, 0
        for _ in range(m.group(3)[0]):
            if p + 10 > len(b):
                ok = False; break
            vv, t, x = struct.unpack_from("<hff", b, p); p += 10
            if not (x == -1.0 or 0 <= x < 1e9) or not (0 <= t < 1e8):
                ok = False; break
            if t >= max_t:
                max_t, v = t, vv
        if not ok:
            continue
        key = name.decode()
        if key not in facts or max_t > facts[key][1]:
            facts[key] = (v, max_t)
    return facts

# ---------- cálculo (igual ao da página) ----------

def qs(prefix, a, b):
    return [prefix + str(i).zfill(2) for i in range(a, b + 1)]

CONTENT = [
    ("base", [
        dict(title="Prólogo", codes=["q001", "q002"], h=4),
        dict(title="Velen", codes=qs("q1", 1, 11), h=11, region=True),
        dict(title="Novigrad", codes=qs("q3", 1, 11), h=13, region=True),
        dict(title="Skellige", codes=qs("q2", 1, 10), h=9, region=True),
        dict(title="Kaer Morhen", codes=["q401", "q402", "q403"], h=6, doneFacts=["q403_completed"]),
        dict(title="Reta final", codes=qs("q5", 1, 5), h=8.5, doneFacts=["q501_eredin_died"]),
    ]),
    ("hos", [
        dict(title="Missão de abertura", codes=["q601"], h=2),
        dict(title="Primeiro desejo", codes=["q602"], h=2.5),
        dict(title="Segundo desejo", codes=["q603"], h=2.5),
        dict(title="Terceiro desejo", codes=["q604"], h=2),
        dict(title="Desfecho", codes=["q605"], h=1, doneFacts=["q605_mirror_won", "q605_mirror_lost", "q605_odimm_won", "q605_done", "q605_completed"]),
    ]),
    ("baw", [
        dict(title="Parte 1", codes=["q701"], h=3),
        dict(title="Parte 2", codes=["q702"], h=3.5),
        dict(title="Parte 3", codes=["q703"], h=3.5),
        dict(title="Parte 4", codes=["q704"], h=3),
        dict(title="Parte 5", codes=["q705"], h=3),
    ]),
]

CODE_RE = re.compile(r"^(?:actor_|BookReadState_)?(q\d{3})[_ ]", re.I)
NOW_RE = re.compile(r"^(q\d|mq\d|sq\d|actor_|statistic_|BookReadState_)", re.I)
clamp = lambda x, a, b: max(a, min(b, x))


def analyze(raw_save):
    facts = read_facts(decompress(raw_save))
    if len(facts) < 50:
        raise ValueError("no_facts")
    by_code, story, now = {}, {}, 0.0
    for name, (v, t) in facts.items():
        if t < 1e7 and NOW_RE.match(name):
            now = max(now, t)
        m = CODE_RE.match(name)
        if m:
            by_code.setdefault(m.group(1).lower(), []).append(t)
            if not name.lower().startswith("actor_"):
                story.setdefault(m.group(1).lower(), 0)
                story[m.group(1).lower()] += 1
    # mortes/nocautes (actor_) acontecem soltas pelo mapa; só fatos de história contam como início
    started = lambda c: story.get(c, 0) >= 3

    results = []
    for key, defs in CONTENT:
        segs = []
        for sd in defs:
            times = [t for c in sd["codes"] if started(c) for t in by_code[c]]
            srt = sorted(times)
            done_names = sd.get("doneFacts") or [x for c in sd["codes"] for x in (c + "_done", c + "_completed")]
            segs.append(dict(sd, started=bool(times),
                             start=srt[min(len(srt) - 1, int(len(srt) * .2))] if srt else None,
                             end=max(times) if times else None,
                             codesStarted=sum(1 for c in sd["codes"] if started(c)),
                             doneFact=any(n in facts for n in done_names)))
        for i, s in enumerate(segs):
            later = segs[i + 1:]
            if s.get("region"):
                s["done"] = s["doneFact"] or any((not x.get("region")) and x["started"] for x in later)
            else:
                s["done"] = s["doneFact"] or any(x["started"] for x in later)
        ratios = []
        if key != "base":  # no jogo base as regiões se misturam; ritmo não confiável
            for i, s in enumerate(segs):
                if s.get("region") or not s["done"] or not s["started"]:
                    continue
                prev = segs[i - 1] if i > 0 else None
                st = prev["end"] if (prev and prev["done"] and prev["end"] is not None and not prev.get("region") and prev["end"] <= s["end"]) else s["start"]
                dur = (s["end"] - st) / 3600
                if dur > .05:
                    ratios.append(dur / s["h"])
        results.append((key, segs, ratios))

    all_r = [r for _, _, rs in results for r in rs]
    global_pace = clamp(sum(all_r) / len(all_r), .25, 3) if all_r else 1.0

    contents = []
    for key, segs, ratios in results:
        pace = clamp(sum(ratios) / len(ratios), .25, 3) if ratios else global_pace
        for i, s in enumerate(segs):
            if s["done"]:
                s["frac"] = 1.0
            elif not s["started"]:
                s["frac"] = 0.0
            elif s.get("region"):
                s["frac"] = clamp(s["codesStarted"] / len(s["codes"]), .05, .95)
            else:
                prev = segs[i - 1] if i > 0 else None
                st = min(s["start"], prev["end"]) if (prev and prev["done"] and prev["end"] is not None and not prev.get("region") and prev["end"] <= now) else s["start"]
                s["frac"] = clamp(((now - st) / 3600) / (s["h"] * pace), .05, .9)
        total = sum(s["h"] for s in segs)
        got = sum(s["h"] * s["frac"] for s in segs)
        finished = all(s["done"] for s in segs)
        any_started = any(s["started"] or s["done"] for s in segs)
        contents.append(dict(
            key=key, status="zerado" if finished else ("andamento" if any_started else "nao_iniciado"),
            pct=round(100.0 if finished else got / total * 100, 1), total=total,
            left=round(total - got, 2), pace=round(pace, 2),
            lastT=max([0] + [s["end"] or 0 for s in segs]),
            segs=[dict(title=s["title"], h=s["h"], frac=round(s["frac"], 2), done=bool(s["done"])) for s in segs]))

    def pick(st):
        c = sorted([c for c in contents if c["status"] == st], key=lambda c: -c["lastT"])
        return c[0] if c else None
    current = pick("andamento") or pick("zerado") or contents[0]
    for c in contents:
        del c["lastT"]
    return dict(current=current["key"], playH=round(now / 3600, 1), contents=contents)



def latest(cache):
    files = []
    for d in save_dirs():
        files += glob.glob(os.path.join(d, "*.sav"))
    if not files:
        return None
    path = max(files, key=os.path.getmtime)
    mtime = os.path.getmtime(path)
    key = (ID, path, mtime)
    if key not in cache:
        with open(path, "rb") as f:
            res = analyze(f.read())
        cover = None
        png = os.path.splitext(path)[0] + ".png"
        if os.path.exists(png) and os.path.getsize(png) < 180000:
            with open(png, "rb") as f:
                cover = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        res.update(saveFile=os.path.basename(path), saveDate=int(mtime * 1000), cover=cover, source="save")
        cache[key] = res
    return cache[key]
