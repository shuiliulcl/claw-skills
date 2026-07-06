#!/usr/bin/env python
"""Query X6 SceneObj and optional Spawner config data without external deps."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS, "pkgrel": PKG_REL_NS}


@dataclass
class SceneObject:
    obj_id: str
    name: str
    bp_path: str
    obj_type: str
    comp_name: str
    obj_tag: str
    source: str
    sheet: str = ""
    row: int = 0
    score: float = 0.0


@dataclass
class Spawner:
    spawner_id: str
    datalayer_id: str
    name: str
    position: str
    rotation: str
    scale: str
    project: str
    obj_id: str
    target_id: str
    filter_uid: str
    scheme: str
    info_type: str
    source: str
    sheet: str = ""
    row: int = 0


def norm(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def is_int_text(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", str(text or "").strip()))


def text_of(elem: Optional[ET.Element]) -> str:
    return "".join(elem.itertext()) if elem is not None else ""


def cell_col(ref: str) -> str:
    match = re.match(r"([A-Z]+)", ref or "")
    return match.group(1) if match else ""


def col_to_num(col: str) -> int:
    value = 0
    for ch in col:
        value = value * 26 + ord(ch) - 64
    return value


def read_xlsx_rows(path: Path) -> Iterable[Tuple[str, int, Dict[str, str]]]:
    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings: List[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for item in root.findall("main:si", NS):
                    shared_strings.append(text_of(item))

            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_to_target: Dict[str, str] = {}
            for rel in rels.findall("pkgrel:Relationship", NS):
                target = rel.attrib.get("Target", "")
                if not target.startswith("/"):
                    target = "xl/" + target
                rid_to_target[rel.attrib["Id"]] = str(PurePosixPath(target))

            for sheet in workbook.findall("main:sheets/main:sheet", NS):
                sheet_name = sheet.attrib.get("name", "")
                rid = sheet.attrib.get(f"{{{REL_NS}}}id")
                sheet_path = rid_to_target.get(rid or "")
                if not sheet_path or sheet_path not in zf.namelist():
                    continue

                sheet_root = ET.fromstring(zf.read(sheet_path))
                for row in sheet_root.findall(".//main:sheetData/main:row", NS):
                    values: Dict[str, str] = {}
                    for cell in row.findall("main:c", NS):
                        col = cell_col(cell.attrib.get("r", ""))
                        cell_type = cell.attrib.get("t")
                        value = ""
                        if cell_type == "s":
                            v = cell.find("main:v", NS)
                            if v is not None and v.text is not None:
                                index = int(v.text)
                                if 0 <= index < len(shared_strings):
                                    value = shared_strings[index]
                        elif cell_type == "inlineStr":
                            value = text_of(cell.find("main:is", NS))
                        else:
                            v = cell.find("main:v", NS)
                            value = v.text if v is not None and v.text is not None else ""
                        if value != "":
                            values[col] = value.strip()
                    if values:
                        yield sheet_name, int(row.attrib.get("r", "0")), values
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return


def workspace_root(path_text: str) -> Path:
    root = Path(path_text).resolve()
    if (root / "X6Game").exists():
        return root
    if root.name == "X6Game" and root.exists():
        return root.parent
    raise SystemExit(f"workspace does not look like an X6Game workspace: {root}")


def load_scene_objects_from_txt(root: Path) -> List[SceneObject]:
    txt_root = root / "X6Game" / "DesignerConfigurations" / "obj" / "场景对象表" / "DontDeleteMe"
    objects: List[SceneObject] = []
    if not txt_root.exists():
        return objects

    txt_files = list(txt_root.glob("场景对象表-*.txt")) + list(txt_root.glob("交互物原型表.txt"))
    for path in sorted(txt_files):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row_num, row in enumerate(reader, start=1):
                if len(row) < 4 or not is_int_text(row[1]):
                    continue
                objects.append(
                    SceneObject(
                        obj_id=row[1].strip(),
                        name=row[2].strip() if len(row) > 2 else "",
                        bp_path=row[3].strip() if len(row) > 3 else "",
                        obj_type=row[11].strip() if len(row) > 11 else "",
                        comp_name=row[16].strip() if len(row) > 16 else "",
                        obj_tag=row[10].strip() if len(row) > 10 else "",
                        source=str(path),
                        row=row_num,
                    )
                )
    return objects


def load_scene_objects_from_xlsx(root: Path) -> List[SceneObject]:
    xlsx_root = root / "X6Game" / "DesignerConfigurations" / "obj" / "场景对象表"
    objects: List[SceneObject] = []
    if not xlsx_root.exists():
        return objects

    for path in sorted(xlsx_root.glob("*.xlsx")):
        for sheet, row_num, values in read_xlsx_rows(path):
            obj_id = values.get("B", "").strip()
            if not is_int_text(obj_id):
                continue
            objects.append(
                SceneObject(
                    obj_id=obj_id,
                    name=values.get("C", "").strip(),
                    bp_path=values.get("D", "").strip(),
                    obj_type=values.get("L", "").strip(),
                    comp_name=values.get("Q", "").strip(),
                    obj_tag=values.get("K", "").strip(),
                    source=str(path),
                    sheet=sheet,
                    row=row_num,
                )
            )
    return objects


def load_scene_objects(root: Path) -> List[SceneObject]:
    objects = load_scene_objects_from_txt(root)
    if objects:
        return objects
    return load_scene_objects_from_xlsx(root)


def object_haystack(obj: SceneObject) -> str:
    return "\t".join([obj.obj_id, obj.name, obj.bp_path, obj.obj_type, obj.comp_name, obj.obj_tag])


def score_object(obj: SceneObject, query: str, mode: str) -> float:
    query_norm = norm(query)
    if not query_norm:
        return 0.0
    if mode in ("auto", "id") and is_int_text(query) and obj.obj_id == query.strip():
        return 2.0
    if mode == "id":
        return 0.0

    haystack = norm(object_haystack(obj))
    if query_norm in haystack:
        return 1.5

    fields = [obj.name, obj.bp_path, obj.comp_name, obj.obj_tag, obj.obj_type]
    return max(SequenceMatcher(None, query_norm, norm(field)).ratio() for field in fields if field)


def find_scene_objects(objects: List[SceneObject], query: str, mode: str, threshold: float) -> List[SceneObject]:
    results: List[SceneObject] = []
    for obj in objects:
        score = score_object(obj, query, mode)
        if score >= threshold:
            copied = SceneObject(**{k: v for k, v in asdict(obj).items() if k != "score"})
            copied.score = score
            results.append(copied)
    results.sort(key=lambda item: (-item.score, item.obj_id, item.name))
    return results


def load_spawners_for_obj_ids(root: Path, obj_ids: set[str]) -> List[Spawner]:
    spawner_root = root / "X6Game" / "DesignerConfigs" / "map" / "spawners" / "spawner"
    spawners: List[Spawner] = []
    if not spawner_root.exists() or not obj_ids:
        return spawners

    for path in sorted(spawner_root.rglob("*.xlsx")):
        for sheet, row_num, values in read_xlsx_rows(path):
            obj_id = values.get("X", "").strip()
            if obj_id not in obj_ids:
                continue
            spawners.append(
                Spawner(
                    spawner_id=values.get("B", "").strip(),
                    datalayer_id=values.get("E", "").strip(),
                    name=values.get("F", "").strip(),
                    position=values.get("G", "").strip(),
                    rotation=values.get("H", "").strip(),
                    scale=values.get("I", "").strip(),
                    project=values.get("A", "").strip(),
                    obj_id=obj_id,
                    target_id=values.get("Y", "").strip(),
                    filter_uid=values.get("M", "").strip(),
                    scheme=values.get("O", "").strip(),
                    info_type=values.get("T", "").strip(),
                    source=str(path),
                    sheet=sheet,
                    row=row_num,
                )
            )
    spawners.sort(key=lambda item: (item.obj_id, item.datalayer_id, item.spawner_id))
    return spawners


def compact_path(path_text: str, root: Path) -> str:
    try:
        return str(Path(path_text).resolve().relative_to(root))
    except Exception:
        return path_text


def print_text(objects: List[SceneObject], spawners: List[Spawner], root: Path, limit: int) -> None:
    print(f"SceneObj matches: {len(objects)}")
    for obj in objects[:limit]:
        print(
            f"- ObjID {obj.obj_id} | {obj.name or obj.comp_name or '(no name)'} | "
            f"type={obj.obj_type or '-'} | score={obj.score:.2f}"
        )
        print(f"  BP: {obj.bp_path or '-'}")
        loc = compact_path(obj.source, root)
        if obj.sheet:
            print(f"  Source: {loc} | sheet={obj.sheet} | row={obj.row}")
        else:
            print(f"  Source: {loc}:{obj.row}")

    if len(objects) > limit:
        print(f"... {len(objects) - limit} more SceneObj matches hidden by --limit")

    if spawners:
        print(f"\nSpawner matches: {len(spawners)}")
        for item in spawners[:limit]:
            print(
                f"- spawner_id {item.spawner_id} | obj_id={item.obj_id} | "
                f"datalayer={item.datalayer_id} | {item.name}"
            )
            print(f"  project={item.project or '-'} | pos={item.position or '-'} | rot={item.rotation or '-'}")
            print(f"  Source: {compact_path(item.source, root)} | sheet={item.sheet} | row={item.row}")
        if len(spawners) > limit:
            print(f"... {len(spawners) - limit} more Spawner matches hidden by --limit")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find X6 SceneObj / interactive object config info.")
    parser.add_argument("query", help="ObjID, BP path/name, Chinese name, or fuzzy keyword")
    parser.add_argument("--workspace", default=".", help="X6 workspace root or X6Game directory")
    parser.add_argument("--mode", choices=["auto", "id", "keyword"], default="auto")
    parser.add_argument("--threshold", type=float, default=0.55, help="Fuzzy score threshold for keyword search")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--with-spawners", action="store_true", help="Also scan TbSpawner rows for matched ObjIDs")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    root = workspace_root(args.workspace)
    objects = load_scene_objects(root)
    if not objects:
        raise SystemExit("no SceneObj rows found under DesignerConfigurations/obj/场景对象表")

    mode = args.mode
    threshold = args.threshold
    if mode in ("auto", "id") and is_int_text(args.query):
        threshold = 2.0
    results = find_scene_objects(objects, args.query, mode, threshold)

    spawners: List[Spawner] = []
    if args.with_spawners and results:
        ids = {item.obj_id for item in results[: args.limit]}
        spawners = load_spawners_for_obj_ids(root, ids)

    if args.json:
        print(json.dumps({"scene_objects": [asdict(item) for item in results], "spawners": [asdict(item) for item in spawners]}, ensure_ascii=False, indent=2))
    else:
        print_text(results, spawners, root, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
