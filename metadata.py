import re, json, time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import requests
from rapidfuzz import fuzz

GROBID_URL = "http://localhost:8070/api/processHeaderDocument"
S2_MATCH   = "https://api.semanticscholar.org/graph/v1/paper/search/match"
OPENALEX   = "https://api.openalex.org/works"
TIMEOUT    = 30
MATCH_MIN  = 0.90
TEI        = {"t": "http://www.tei-c.org/ns/1.0"}
S2_FIELDS  = "title,authors,year,venue,externalIds,abstract"
HEADERS    = {"User-Agent": "metadata-pipeline/1.0 (mailto:you@example.com)"}
MAILTO     = "you@example.com"           # polite-pool for OpenAlex


@dataclass
class PaperMeta:
    title: Optional[str] = None
    authors: list = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    abstract: Optional[str] = None
    source: str = "local"          # semantic-scholar | openalex | grobid | failed | error
    match_score: float = 0.0


def _sim(a, b):
    return fuzz.token_sort_ratio((a or "").lower(), (b or "").lower()) / 100


def _abstract_from_inverted(inv):
    """Rebuild the abstract from OpenAlex's word->positions inverted index."""
    if not inv:
        return None
    pos = {p: w for w, ps in inv.items() for p in ps}
    return " ".join(pos[i] for i in sorted(pos))


# ---------------------------------------------------------------- title extraction
def grobid_header(pdf_path):
    try:
        with open(pdf_path, "rb") as f:
            r = requests.post(GROBID_URL, files={"input": f},
                              headers=HEADERS, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except (requests.RequestException, ET.ParseError) as e:
        print(f"  [grobid] failed: {e}")
        return None

    t = root.find(".//t:titleStmt/t:title[@level='a']", TEI)
    if t is None:
        t = root.find(".//t:titleStmt/t:title", TEI)
    title = re.sub(r"\s+", " ", "".join(t.itertext())).strip() if t is not None else None

    authors = []
    for a in root.findall(".//t:titleStmt/t:author", TEI):
        fore = " ".join(x.text or "" for x in a.findall(".//t:forename", TEI))
        sur  = " ".join(x.text or "" for x in a.findall(".//t:surname", TEI))
        if (fore + sur).strip():
            authors.append(f"{fore} {sur}".strip())

    doi_el = root.find(".//t:idno[@type='DOI']", TEI)
    return {"title": title, "authors": authors,
            "doi": doi_el.text if doi_el is not None else None}


def search_s2(title):
    """Semantic Scholar match endpoint: single best match, 404 if none."""
    for attempt in range(3):
        try:
            r = requests.get(S2_MATCH, params={"query": title, "fields": S2_FIELDS},
                             headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 404:            # S2's explicit "no match"
                return None
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            p = r.json()["data"][0]
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"  [s2] failed: {e}")
            return None

        score = _sim(title, p.get("title"))
        if score < MATCH_MIN:
            return None
        ext = p.get("externalIds") or {}
        return {"title": p["title"],
                "authors": [a["name"] for a in p.get("authors", [])],
                "year": p.get("year"),
                "venue": p.get("venue") or None,
                "doi": ext.get("DOI"),
                "arxiv_id": ext.get("ArXiv"),
                "abstract": p.get("abstract"),
                "source": "semantic-scholar",
                "match_score": score}
    return None


def search_openalex(title):
    """OpenAlex full-text search; top relevance hits, take best fuzzy match."""
    try:
        r = requests.get(OPENALEX,
                         params={"search": title, "per-page": 5, "mailto": MAILTO},
                         headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results", [])
    except requests.RequestException as e:
        print(f"  [openalex] failed: {e}")
        return None

    best, best_score = None, 0.0
    for w in results:
        score = _sim(title, w.get("title") or "")
        if score > best_score:
            best, best_score = w, score

    if best is None or best_score < MATCH_MIN:
        return None
    return {"title": best["title"],
            "authors": [a["author"]["display_name"]
                        for a in best.get("authorships", []) if a.get("author")],
            "year": best.get("publication_year"),
            "venue": ((best.get("primary_location") or {})
                      .get("source") or {}).get("display_name"),
            "doi": (best.get("doi") or "").replace("https://doi.org/", "") or None,
            "arxiv_id": None,
            "abstract": _abstract_from_inverted(best.get("abstract_inverted_index")),
            "source": "openalex",
            "match_score": best_score}


def resolve_paper(pdf_path):
    g = grobid_header(pdf_path)
    title = g and g["title"]
    if not title:
        return PaperMeta(source="failed")

    for finder in (search_s2, search_openalex):
        hit = finder(title)
        if hit:
            hit["authors"] = hit["authors"] or g["authors"]
            hit["doi"]     = hit["doi"] or g["doi"]
            return PaperMeta(**hit)

    # no API confirmed the title — keep GROBID's own output
    return PaperMeta(title=g["title"], authors=g["authors"], doi=g["doi"],
                     source="grobid", match_score=0.5)


def process_folder(input_dir, output_dir):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs found in {input_dir}")
        return

    print(f"processing {len(pdfs)} PDF(s) from {input_dir}\n")
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name}")
        try:
            meta = asdict(resolve_paper(pdf))
        except Exception as e:                  
            meta = asdict(PaperMeta(source="error"))
            print(f"  unexpected error: {e}")

        out = output_dir / (pdf.stem + ".json")
        out.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"  -> {out.name}  (source: {meta['source']}, "
              f"score: {meta['match_score']})\n")

        if i < len(pdfs):
            time.sleep(1)                       # stay under S2's rate limit

