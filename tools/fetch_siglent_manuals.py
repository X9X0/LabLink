"""Download Siglent programming guides.

Eight B&K families in our registry are Siglent-protocol rebadges --
2190D/E and 2550/2560 (scopes), 4050/4050B and 4060/4060B (generators)
-- so these guides cover instruments we already claim to drive, under
B&K model numbers.

Worth saying: Siglent's shorthand is not SCPI's. "C1:BSWV WVTP,SINE"
is their own long/short pairing (BASIC_WAVE / BSWV), documented
explicitly per command rather than derived from capitalisation. The
uppercase-run rule does not apply, so these need reading on their own
terms.
"""
import os
import sys
import urllib.error
import urllib.request

OUT = "//wsl.localhost/Ubuntu/home/stevecap/Manuals/Siglent/Programming"

GUIDES = [
    # Oscilloscopes -- behind B&K 2190D/E, 2550, 2560
    ("SDS_Series_ProgrammingGuide_EN11D.pdf",
     "https://siglentna.com/wp-content/uploads/dlm_uploads/2023/04/SDS-Series_ProgrammingGuide_EN11D.pdf"),
    ("SDS2000XPlus_ProgrammingGuide_PG01-E11A.pdf",
     "https://siglentna.com/wp-content/uploads/dlm_uploads/2021/01/SDS2000X-Plus_ProgrammingGuide_PG01-E11A.pdf"),
    ("SDS1000_2000X_2000XE_ProgrammingGuide_PG01-E02D.pdf",
     "https://int.siglent.com/u_file/document/SDS1000%20Series&SDS2000X&SDS2000X-E_ProgrammingGuide_PG01-E02D.pdf"),
    ("SDS1000XHD_ProgrammingGuide_EN11F.pdf",
     "https://www.siglenteu.com/wp-content/uploads/dlm_uploads/2024/02/SDS1000XHD_Series_ProgrammingGuide_EN11F.pdf"),
    ("SDS_ProgrammingGuide_forSDS.pdf",
     "https://siglentna.com/wp-content/uploads/dlm_uploads/2017/10/ProgrammingGuide_forSDS-1-1.pdf"),
    ("SIGLENT_Digital_Oscilloscopes_Remote_Control_Manual.pdf",
     "https://int.siglent.com/upload_file/user/SDS1000X+/SIGLENT_Digital_Oscilloscopes_Remote_Control_Manual.pdf"),
    # Function / arbitrary waveform generators -- behind B&K 4050/4060
    ("SDG_Remote_Control_Manual_Rev1.0.pdf",
     "https://int.siglent.com/upload_file/user/SDG2000X/SDG_Remote_Control_Manual(Rev1.0).pdf"),
    ("SDG_ProgrammingGuide_PG_E03B.pdf",
     "https://siglentna.com/USA_website_2014/Documents/Program_Material/SDG_ProgrammingGuide_PG_E03B.pdf"),
]


def fetch(url, dest):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; manual-archive/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, repr(e)[:70]
    if not body.startswith(b"%PDF"):
        return None, f"not a pdf ({body[:12]!r})"
    with open(dest, "wb") as f:
        f.write(body)
    return len(body), None


def main():
    os.makedirs(OUT, exist_ok=True)
    got, failed = 0, []
    for name, url in GUIDES:
        dest = os.path.join(OUT, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  have  {name}")
            got += 1
            continue
        size, err = fetch(url, dest)
        if size:
            print(f"  got   {name}  ({size // 1024} KB)")
            got += 1
        else:
            print(f"  FAIL  {name}: {err}")
            failed.append((name, url, err))
    print(f"\n{got} of {len(GUIDES)} guides")
    for name, url, err in failed:
        print(f"   missing {name}: {err}\n      {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
