"""Normalize GROBID TEI XML into section records."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}


@dataclass(frozen=True, slots=True)
class SectionRecord:
    """One section row ready for persistence, using local parent links."""

    id: int
    parent_id: int | None
    section_path: str
    title: str
    ordinal: int
    page_start: int | None
    page_end: int | None
    char_start: int | None
    char_end: int | None
    body_text: str


def tei_to_sections(tei_xml: str) -> list[SectionRecord]:
    """Walk TEI ``<body>`` divs into nested section records in document order."""

    root = ElementTree.fromstring(tei_xml)
    body = root.find(".//tei:text/tei:body", NS)
    if body is None:
        body = root.find(f".//{{{TEI_NS}}}body")
    if body is None:
        return []

    sections: list[SectionRecord] = []
    untitled_counter = 0

    def next_untitled() -> str:
        nonlocal untitled_counter
        untitled_counter += 1
        return f"Untitled section {untitled_counter}"

    def walk(
        div: ElementTree.Element,
        *,
        parent_id: int | None,
        path_prefix: list[str],
    ) -> None:
        nonlocal sections
        title = _heading_text(div) or next_untitled()
        path_parts = [*path_prefix, title]
        section_path = "/".join(path_parts)
        body_text = _own_body_text(div)
        page_start, page_end = _page_range(div)
        section_id = len(sections) + 1
        sections.append(
            SectionRecord(
                id=section_id,
                parent_id=parent_id,
                section_path=section_path,
                title=title,
                ordinal=len(sections),
                page_start=page_start,
                page_end=page_end,
                char_start=0 if body_text else None,
                char_end=len(body_text) if body_text else None,
                body_text=body_text,
            )
        )
        for child in list(div):
            if _local_name(child.tag) == "div":
                walk(child, parent_id=section_id, path_prefix=path_parts)

    for child in list(body):
        if _local_name(child.tag) == "div":
            walk(child, parent_id=None, path_prefix=[])

    return sections


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _heading_text(div: ElementTree.Element) -> str | None:
    for child in list(div):
        if _local_name(child.tag) == "head":
            text = "".join(child.itertext()).strip()
            return text or None
    return None


def _own_body_text(div: ElementTree.Element) -> str:
    paragraphs: list[str] = []
    for child in list(div):
        if _local_name(child.tag) == "p":
            text = "".join(child.itertext()).strip()
            if text:
                paragraphs.append(text)
    return "\n".join(paragraphs)


def _page_range(div: ElementTree.Element) -> tuple[int | None, int | None]:
    pages: list[int] = []
    for child in list(div):
        if _local_name(child.tag) != "p":
            continue
        pages.extend(_pages_from_coords(child.get("coords")))
    if not pages:
        return None, None
    return min(pages), max(pages)


def _pages_from_coords(coords: str | None) -> list[int]:
    if not coords:
        return []
    pages: list[int] = []
    for coordinate_group in coords.split(";"):
        page = coordinate_group.split(",", 1)[0].strip()
        try:
            pages.append(int(float(page)))
        except ValueError:
            continue
    return pages


__all__ = ["SectionRecord", "tei_to_sections"]
