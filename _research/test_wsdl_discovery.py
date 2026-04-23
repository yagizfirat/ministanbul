"""
WSDL Discovery — Faz 1.5 Pre-flight #2 devamı
----------------------------------------------
Amaç: İETT SeferGerceklesme.asmx servisinin expose ettiği operation
isimlerini listeleyip GetIettArsivGorev_json yerine doğru method
adını bulmak.

Bir önceki çağrı (test_arsiv_gorev_today.py) Layer7 gateway'den
"Service Not Found / unsupported operation" aldı — method adı
yanlış. WSDL discovery ile tam operation listesi alınır.

KURAL: TEK GET, loop/retry YOK. WSDL çağrısı rate limiter'a
genelde dahil değil (test edilmedi, ama ayrı path).

Base: test_ibb_token.py'deki endpoint + requests kullanımı, ama SOAP
envelope yerine düz GET. SOAPAction header yok.
"""

import re
import sys
from pathlib import Path

import requests

WSDL_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx?WSDL"

HEADERS = {
    "User-Agent": "miniistanbul-research/0.1 (wsdl-discovery)",
}

OUTPUT_FILE = Path(__file__).parent / "soap_wsdl.xml"


def detect_type(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<?xml") or "<wsdl:definitions" in stripped[:500] or "<definitions" in stripped[:500]:
        return "XML (WSDL)"
    if stripped.lower().startswith("<!doctype html") or stripped.lower().startswith("<html"):
        return "HTML (muhtemelen error page)"
    if "Policy Falsified" in text or "soap:Fault" in text:
        return "SOAP Fault"
    return f"other (starts: {stripped[:60]!r})"


def extract_operations(wsdl: str) -> list[str]:
    """WSDL içindeki tüm <operation name="..."> / <wsdl:operation name="..."> değerlerini topla.
    Aynı isim birden fazla section'da (portType, binding) çıkabilir, unique'le.
    """
    pat = re.compile(r"<(?:wsdl:)?operation\s+[^>]*?name=\"([^\"]+)\"", re.IGNORECASE)
    names = pat.findall(wsdl)
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def extract_messages(wsdl: str) -> list[tuple[str, list[str]]]:
    """<message name="X"><part name="p" type="t"/></message> parse et.
    Returns [(message_name, [part_descriptors]), ...].
    """
    msg_pat = re.compile(
        r"<(?:wsdl:)?message\s+[^>]*?name=\"([^\"]+)\"[^>]*>(.*?)</(?:wsdl:)?message>",
        re.DOTALL | re.IGNORECASE,
    )
    part_pat = re.compile(
        r"<(?:wsdl:)?part\s+([^/>]+)/?>",
        re.IGNORECASE,
    )
    result = []
    for m in msg_pat.finditer(wsdl):
        name = m.group(1)
        body = m.group(2)
        parts = []
        for p in part_pat.finditer(body):
            attrs = p.group(1).strip()
            parts.append(attrs)
        result.append((name, parts))
    return result


def main():
    print("=" * 60)
    print("WSDL DISCOVERY — tek GET")
    print(f"URL: {WSDL_URL}")
    print("=" * 60)

    try:
        r = requests.get(WSDL_URL, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"\n[HATA] İstek başarısız: {e}")
        sys.exit(1)

    text = r.text
    size = len(text.encode("utf-8"))

    OUTPUT_FILE.write_text(text, encoding="utf-8")

    print(f"\n--- HTTP ---")
    print(f"  Status code: {r.status_code}")
    print(f"  Response size: {size} byte ({size/1024:.1f} KB)")
    print(f"  Content-Type: {r.headers.get('Content-Type', '(yok)')}")
    rtype = detect_type(text)
    print(f"  Tip: {rtype}")

    if "Policy Falsified" in text or "soap:Fault" in text:
        print(f"\n[UYARI] Gateway reddi. İlk 400 char:")
        print(f"  {text[:400]}")
        sys.exit(2)

    if not rtype.startswith("XML"):
        print(f"\n[UYARI] WSDL beklenirken başka bir şey geldi. İlk 400 char:")
        print(f"  {text[:400]}")
        sys.exit(2)

    ops = extract_operations(text)
    print(f"\n--- Operations ({len(ops)} unique) ---")
    for op in ops:
        marker = ""
        lower = op.lower()
        if "arsiv" in lower or "gorev" in lower:
            marker = "  ← HIGHLIGHT"
        print(f"  {op}{marker}")

    highlighted = [o for o in ops if ("arsiv" in o.lower() or "gorev" in o.lower())]
    print(f"\n--- 'Arsiv' veya 'Gorev' içeren ({len(highlighted)}) ---")
    if highlighted:
        for h in highlighted:
            print(f"  {h}")
    else:
        print("  (hiç yok — method adı tamamen farklı olabilir)")

    msgs = extract_messages(text)
    print(f"\n--- Messages ({len(msgs)}) ---")
    relevant = [
        (n, p) for (n, p) in msgs
        if "arsiv" in n.lower() or "gorev" in n.lower()
    ]
    if relevant:
        print(f"  (Arsiv/Gorev ile ilgili {len(relevant)} mesaj)")
        for name, parts in relevant:
            print(f"\n  {name}")
            for p in parts:
                print(f"    part: {p}")
    else:
        print(f"  İlk 10 mesaj ve part'ları:")
        for name, parts in msgs[:10]:
            print(f"    {name}: {len(parts)} part")
            for p in parts[:2]:
                print(f"      - {p[:120]}")

    print(f"\n--- Çıktı ---")
    print(f"  Ham WSDL yazıldı: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
