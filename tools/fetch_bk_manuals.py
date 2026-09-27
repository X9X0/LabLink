"""Find and download B&K programming manuals for the SCPI families we drive.

B&K publish on S3 under a handful of naming conventions; there is no
index, so this probes the patterns per family and keeps what answers.
Only programming manuals -- the user guides do not carry the SCPI
tree, and it is the command spellings we are after.
"""
import os
import sys
import urllib.error
import urllib.request

BASE = "https://bkpmedia.s3.us-west-1.amazonaws.com/downloads"
OUT = "//wsl.localhost/Ubuntu/home/stevecap/Manuals/BK/Programming"

#: SCPI families from server/equipment/bk_registry.py, plus the concrete
#: models behind the ones registered under a series name.
FAMILIES = [
    # DC loads
    "8500B", "8500", "8510B", "8600", "8601", "8602", "8610", "8612",
    "8614", "8616", "8620", "8625", "8542B",
    # DC supplies
    "9115", "9116", "9129B", "9130B", "9130C", "9131B", "9132B", "9140",
    "9141", "9200", "9205B", "9206B", "9240", "9241", "9242", "9250",
    "1696B", "1785B", "1900B",
    # Multimeters / counters / misc
    "5490C", "5491C", "5492C", "5493C", "5335B", "2510B", "2194",
    "2680", "2840", "4088", "8460", "8550", "9800", "9810", "9830B",
    "BA6010", "MDL", "MR", "RFM3000",
]

PATTERNS = [
    "{f}_Series_programming_manual.pdf",
    "{f}_programming_manual.pdf",
    "{f}_Programming_Manual.pdf",
    "{f}-Series_programming_manual.pdf",
    "{f}_series_programming_manual.pdf",
    "{f}_Series_Programming_Manual.pdf",
]

DIRS = ["programming_manuals/en-us", "manuals/en-us"]


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:
        return None, 0


def fetch(url, dest):
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            body = r.read()
    except Exception as e:
        return None, repr(e)
    if not body.startswith(b"%PDF"):
        return None, "not a pdf"
    with open(dest, "wb") as f:
        f.write(body)
    return len(body), None


def main():
    os.makedirs(OUT, exist_ok=True)
    got, missing = [], []
    for family in FAMILIES:
        found = False
        for folder in DIRS:
            for pattern in PATTERNS:
                name = pattern.format(f=family)
                url = f"{BASE}/{folder}/{name}"
                status, size = head(url)
                if status != 200:
                    continue
                dest = os.path.join(OUT, f"{family}__{name}")
                if os.path.exists(dest):
                    print(f"  have  {family:<8} {name}")
                    found = True
                    break
                n, err = fetch(url, dest)
                if n:
                    print(f"  got   {family:<8} {name}  ({n // 1024} KB)")
                    got.append((family, name, n))
                    found = True
                    break
                print(f"  bad   {family:<8} {name}: {err}")
            if found:
                break
        if not found:
            missing.append(family)

    print(f"\ndownloaded {len(got)}; no programming manual found for "
          f"{len(missing)}:")
    print("   " + " ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
