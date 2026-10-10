"""PubMed: biomedical and life-science literature from the US National Library of Medicine (E-utilities), with
publication types (trial, systematic review, guideline, ...) and retraction flags. Part of the medicine pack."""

from __future__ import annotations

from typing import Any

import kit

NAME = "pubmed"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# PubMed publication types, strongest evidence first: the first match decides the evidence type.
TYPES = (
    ("Meta-Analysis", "review"), ("Systematic Review", "review"), ("Randomized Controlled Trial", "peer-reviewed"),
    ("Practice Guideline", "report"), ("Guideline", "report"), ("Review", "review"), ("Clinical Trial", "peer-reviewed"),
    ("Dataset", "dataset"), ("Preprint", "preprint"), ("Editorial", "commentary"), ("Comment", "commentary"),
    ("Letter", "commentary"), ("News", "journalism"), ("Journal Article", "peer-reviewed"),
)
WITHDRAWN = {"Retracted Publication", "Retraction of Publication"}


def evidence_type(publication_types: list[str]) -> str:
    return next((evidence for name, evidence in TYPES if name in publication_types), "unknown")


def abstracts(ids: list[str], options: dict[str, Any]) -> dict[str, str]:
    """The abstracts of the given PubMed ids, from efetch's XML (esummary has none)."""
    data, _ = kit.fetch(f"{EUTILS}/efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"},
                        options["interval"])
    found = {}
    for article in kit.xml_root(data).iter("PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        parts = [" ".join("".join(node.itertext()).split()) for node in article.iter("AbstractText")]
        found[pmid] = " ".join(part for part in parts if part)
    return found


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    term = query
    if filters.get("type"):
        term += f' AND "{filters["type"]}"[pt]'
    params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": min(max(limit, 1), 100), "sort": "relevance"}
    if since:
        params.update({"datetype": "pdat", "mindate": since.replace("-", "/"), "maxdate": "3000"})
    ids = kit.fetch_json(f"{EUTILS}/esearch.fcgi", params, options["interval"]).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    result = kit.fetch_json(f"{EUTILS}/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}, options["interval"]).get("result", {})
    texts = abstracts(ids, options)

    def convert(pmid: str) -> dict[str, Any]:
        item = result[pmid]
        doi = next((entry["value"] for entry in item.get("articleids", []) if entry.get("idtype") == "doi"), None)
        types = item.get("pubtype", [])
        return kit.record(
            NAME, item["title"].rstrip("."), f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", evidence_type(types), doi=doi,
            authors=[author.get("name", "") for author in item.get("authors", []) if author.get("authtype", "Author") == "Author"],
            date=kit.iso_date(item.get("sortpubdate", "")[:10].replace("/", "-")), abstract=texts.get(pmid, ""),
            extra={"pmid": pmid, "venue": item.get("fulljournalname"), "publicationTypes": types, "retracted": bool(WITHDRAWN & set(types))},
        )

    return kit.each([pmid for pmid in ids if pmid in result], convert)
