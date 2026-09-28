"""Detect and describe a PFLOTRAN case folder as an expandable asset group.

The ``.in`` deck is the source of truth: it tells us which auxiliary files are a
mesh, materials, boundaries, datasets, a restart or a chemistry database. Files
that the deck does not reference (snapshots, xmf, domain, mass balance, log) are
recovered with filename pattern sweeps keyed off the deck stem.

Detection is deliberately cheap — it never reads large mesh/HDF5 payloads, only
filenames, sizes and (for the small ``.mat`` guard) a few header bytes — so it is
safe to run against multi-hundred-megabyte cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydelling.managers.pflotran_study import PflotranStudy

# Roles a component can take. Kept in sync with the backend ingestion.
ROLE_INPUT_FILE = "input_file"
ROLE_MESH = "mesh"
ROLE_DOMAIN_H5 = "domain_h5"
ROLE_MATERIAL_IDS = "material_ids"
ROLE_BOUNDARY_EX = "boundary_ex"
ROLE_BC_DATASET_H5 = "bc_dataset_h5"
ROLE_RESTART = "restart"
ROLE_GEOCHEM_DB = "geochem_db"
ROLE_OUTPUT_SNAPSHOT = "output_snapshot"
ROLE_OUTPUT_XMF = "output_xmf"
ROLE_OBSERVATION = "observation"
ROLE_MASS_BALANCE = "mass_balance"
ROLE_LOG = "log"
ROLE_OTHER = "other"

# Fixed display / grouping order for the roles.
ROLE_ORDER = [
    ROLE_INPUT_FILE,
    ROLE_MESH,
    ROLE_DOMAIN_H5,
    ROLE_MATERIAL_IDS,
    ROLE_BOUNDARY_EX,
    ROLE_BC_DATASET_H5,
    ROLE_RESTART,
    ROLE_GEOCHEM_DB,
    ROLE_OUTPUT_SNAPSHOT,
    ROLE_OUTPUT_XMF,
    ROLE_OBSERVATION,
    ROLE_MASS_BALANCE,
    ROLE_LOG,
    ROLE_OTHER,
]

# Semantic navigation groups shared by case import, the Assets sidebar, and
# assistant context. These are intentionally broader than file roles: a
# boundary region (``.ex``) and its time-varying HDF5 dataset belong together
# from a user's point of view even though they need different parsers.
PFLOTRAN_ASSET_GROUPS = (
    {"key": "case", "label": "Case", "roles": (ROLE_INPUT_FILE,)},
    {"key": "domain", "label": "Domain", "roles": (ROLE_MESH, ROLE_DOMAIN_H5)},
    {"key": "materials", "label": "Materials", "roles": (ROLE_MATERIAL_IDS,)},
    {
        "key": "boundary_conditions",
        "label": "Boundary Conditions",
        "roles": (ROLE_BOUNDARY_EX, ROLE_BC_DATASET_H5),
    },
    {"key": "initial_state", "label": "Initial State", "roles": (ROLE_RESTART,)},
    {"key": "chemistry", "label": "Chemistry", "roles": (ROLE_GEOCHEM_DB,)},
    {
        "key": "results",
        "label": "Results",
        "roles": (
            ROLE_OUTPUT_SNAPSHOT,
            ROLE_OUTPUT_XMF,
            ROLE_OBSERVATION,
            ROLE_MASS_BALANCE,
            ROLE_LOG,
        ),
    },
    {"key": "other", "label": "Other", "roles": (ROLE_OTHER,)},
)

PFLOTRAN_GROUP_BY_ROLE = {
    role: group["key"]
    for group in PFLOTRAN_ASSET_GROUPS
    for role in group["roles"]
}


def pflotran_group_for_role(role: str | None) -> str:
    """Return the stable semantic group key for a detected component role."""
    return PFLOTRAN_GROUP_BY_ROLE.get(role or "", "other")

# macOS / editor junk that should never become a component.
_JUNK_NAMES = {".DS_Store", "Thumbs.db"}

# A MATLAB v5+ ``.mat`` file starts with this ASCII banner; a PFLOTRAN region
# ``.mat`` is an ASCII list of cell IDs, so this lets us guard against a
# genuine MATLAB file sneaking in under the same extension.
_MATLAB_MAGIC = b"MATLAB"

_SNAPSHOT_RE = re.compile(r"-(\d+)\.h5$", re.IGNORECASE)
_XMF_RE = re.compile(r"-(\d+)\.xmf$", re.IGNORECASE)
_OBS_RE = re.compile(r"-obs-?(\d+)\.(tec|pft)$", re.IGNORECASE)


@dataclass
class PflotranCaseComponent:
    """One file that belongs to a PFLOTRAN case, tagged with its role."""

    relative_path: str
    role: str
    detail: dict = field(default_factory=dict)
    size_bytes: Optional[int] = None
    referenced: bool = False

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "role": self.role,
            "detail": self.detail,
            "size_bytes": self.size_bytes,
            "referenced": self.referenced,
        }


@dataclass
class PflotranCaseModel:
    """Structured description of a detected PFLOTRAN case folder."""

    root: Path
    input_file: str
    stem: str
    components: list[PflotranCaseComponent]
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def components_by_role(self, role: str) -> list[PflotranCaseComponent]:
        return [c for c in self.components if c.role == role]

    def to_dict(self) -> dict:
        return {
            "input_file": self.input_file,
            "stem": self.stem,
            "summary": self.summary,
            "warnings": self.warnings,
            "components": [c.to_dict() for c in self.components],
        }


def _clean_token(token: str) -> str:
    return token.strip().strip("'").strip('"')


def _resolve(root: Path, token: str) -> tuple[str, bool]:
    """Resolve a deck path token to a root-relative posix path + existence flag."""
    raw = _clean_token(token)
    candidate = (root / raw).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        # Referenced outside the case root; keep the raw token for the warning.
        return raw, candidate.exists()
    return relative, candidate.exists()


def _looks_like_matlab(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(_MATLAB_MAGIC)) == _MATLAB_MAGIC
    except OSError:
        return False


def _find_input_deck(root: Path) -> Optional[Path]:
    """Return the ``.in`` deck that declares a SIMULATION card, if any."""
    candidates = sorted(p for p in root.glob("*.in") if p.is_file())
    for path in candidates:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if re.search(r"(?im)^\s*SIMULATION\b", text):
            return path
    return None


def _regions_in_blocks(text: str, keyword: str) -> set[str]:
    """Region names referenced inside blocks opened by ``keyword``.

    Handles ``STRATA`` (``STRATA ... REGION x ... END``) and
    ``BOUNDARY_CONDITION name ... REGION x ... END`` by scanning from each
    keyword occurrence to the nearest following ``REGION`` line.
    """
    names: set[str] = set()
    pattern = re.compile(
        rf"(?is)\b{keyword}\b.*?\bREGION\s+(\S+)",
    )
    for match in pattern.finditer(text):
        names.add(match.group(1))
    return names


def _parse_dataset_blocks(lines: list[str]) -> list[dict]:
    """Return top-level DATASET blocks as {name, filename, hdf5_dataset_name}.

    Robust to the ``get_datasets`` limitation that drops the first block: we scan
    for lines that *start* with ``DATASET`` (block headers), which excludes the
    ``... DATASET name`` references inside FLOW_CONDITION blocks.
    """
    blocks: list[dict] = []
    current: Optional[dict] = None
    for raw in lines:
        stripped = raw.strip()
        header = re.match(r"(?i)^DATASET\s+(\S+)\s*$", stripped)
        if header:
            current = {"name": header.group(1), "filename": None, "hdf5_dataset_name": None}
            blocks.append(current)
            continue
        if current is None:
            continue
        if re.match(r"(?i)^END\b", stripped) or stripped == "/":
            current = None
            continue
        filename = re.match(r"(?i)^FILENAME\s+(\S+)", stripped)
        if filename:
            current["filename"] = _clean_token(filename.group(1))
            continue
        hdf5 = re.match(r"(?i)^HDF5_DATASET_NAME\s+(\S+)", stripped)
        if hdf5:
            current["hdf5_dataset_name"] = _clean_token(hdf5.group(1))
    return blocks


def _parse_materials(text: str) -> list[dict]:
    materials: list[dict] = []
    for match in re.finditer(
        r"(?is)\bMATERIAL_PROPERTY\s+(\S+)(.*?)\bEND\b", text
    ):
        name = match.group(1)
        body = match.group(2)
        id_match = re.search(r"(?im)^\s*ID\s+(\d+)", body)
        properties: dict[str, float] = {}
        for raw_line in body.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            property_match = re.match(
                r"^([A-Z][A-Z0-9_]*)\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[dDeE][-+]?\d+)?)\b",
                line,
                re.IGNORECASE,
            )
            if not property_match or property_match.group(1).upper() == "ID":
                continue
            try:
                value = float(property_match.group(2).replace("D", "e").replace("d", "e"))
            except ValueError:
                continue
            properties[property_match.group(1).upper()] = value
        materials.append(
            {
                "name": name,
                "id": int(id_match.group(1)) if id_match else None,
                "properties": properties,
            }
        )
    return materials


def _strata_materials(text: str) -> dict[str, str]:
    """Map REGION names to MATERIAL_PROPERTY names from STRATA blocks."""
    assignments: dict[str, str] = {}
    for block in re.finditer(r"(?is)\bSTRATA\b(.*?)\bEND\b", text):
        body = block.group(1)
        region = re.search(r"(?im)^\s*REGION\s+(\S+)", body)
        material = re.search(r"(?im)^\s*MATERIAL\s+(\S+)", body)
        if region and material:
            assignments[_clean_token(region.group(1))] = _clean_token(
                material.group(1)
            )
    return assignments


def detect_pflotran_case(root: str | Path) -> Optional[PflotranCaseModel]:
    """Detect a PFLOTRAN case rooted at ``root``.

    Returns ``None`` when the folder does not contain a ``.in`` deck with a
    SIMULATION card.
    """
    root = Path(root)
    if not root.is_dir():
        return None
    deck_path = _find_input_deck(root)
    if deck_path is None:
        return None

    text = deck_path.read_text(errors="ignore")
    lines = text.splitlines()
    stem = deck_path.stem

    warnings: list[str] = []
    # role assignments keyed by root-relative posix path
    roles: dict[str, str] = {}
    details: dict[str, dict] = {}
    referenced: set[str] = set()

    def assign(relative: str, role: str, detail: dict | None = None, ref: bool = False) -> None:
        roles[relative] = role
        if detail:
            details.setdefault(relative, {}).update(detail)
        if ref:
            referenced.add(relative)

    def resolve_ref(token: str, role: str, detail: dict | None = None) -> Optional[str]:
        relative, exists = _resolve(root, token)
        if not exists:
            warnings.append(f"{role}: referenced file not found: {_clean_token(token)}")
            return None
        assign(relative, role, detail, ref=True)
        return relative

    # --- the deck itself ------------------------------------------------------
    deck_relative = deck_path.relative_to(root).as_posix()

    study: Optional[PflotranStudy] = None
    try:
        study = PflotranStudy(str(deck_path))
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"input_file: could not fully parse deck ({exc!r})")

    final_time = None
    final_time_unit = "y"
    if study is not None:
        try:
            final_time = study.get_simulation_time("y")
        except Exception:
            final_time = None

    simulation_type = None
    sim_match = re.search(r"(?im)^\s*SIMULATION_TYPE\s+(\S+)", text)
    if sim_match:
        simulation_type = sim_match.group(1)
    modes = [
        m.group(1).upper()
        for m in re.finditer(r"(?im)^\s*MODE\s+(\S+)", text)
    ]
    # PRIMARY_SPECIES is a block; collect the species names inside it.
    species: list[str] = []
    ps_block = re.search(r"(?is)\bPRIMARY_SPECIES\b(.*?)/", text)
    if ps_block:
        species = [tok for tok in ps_block.group(1).split() if tok and not tok.startswith("#")]

    assign(
        deck_relative,
        ROLE_INPUT_FILE,
        {
            "simulation_type": simulation_type,
            "modes": modes,
            "final_time": final_time,
            "final_time_unit": final_time_unit,
            "primary_species": species,
        },
        ref=True,
    )

    # --- mesh (GRID TYPE unstructured_explicit/implicit <path>) ---------------
    grid_match = re.search(
        r"(?im)^\s*TYPE\s+(unstructured_explicit|unstructured_implicit)\s+(\S+)", text
    )
    if grid_match:
        resolve_ref(
            grid_match.group(2),
            ROLE_MESH,
            {"grid_type": grid_match.group(1).lower()},
        )

    # --- restart (RESTART block FILENAME) -------------------------------------
    restart_match = re.search(r"(?ims)^\s*RESTART\b.*?^\s*FILENAME\s+(\S+)", text)
    if restart_match:
        resolve_ref(restart_match.group(1), ROLE_RESTART)

    # --- chemistry database ---------------------------------------------------
    db_match = re.search(r"(?im)^\s*DATABASE\s+(\S+)", text)
    if db_match:
        resolve_ref(db_match.group(1), ROLE_GEOCHEM_DB)

    # --- datasets (BC HDF5) ---------------------------------------------------
    for block in _parse_dataset_blocks(lines):
        if not block.get("filename"):
            continue
        resolve_ref(
            block["filename"],
            ROLE_BC_DATASET_H5,
            {
                "dataset_name": block["name"],
                "hdf5_dataset_name": block.get("hdf5_dataset_name"),
            },
        )

    # --- region files (materials vs boundaries, by deck usage) ----------------
    strata_regions = _regions_in_blocks(text, "STRATA")
    strata_materials = _strata_materials(text)
    bc_regions = _regions_in_blocks(text, "BOUNDARY_CONDITION")
    if study is not None:
        try:
            region_names = study.get_regions()
        except Exception:
            region_names = []
        for region in region_names:
            try:
                token = study.get_region_file(region)
            except Exception:
                token = None
            if not token:
                continue
            relative, exists = _resolve(root, token)
            if not exists:
                warnings.append(
                    f"region {region}: referenced file not found: {_clean_token(token)}"
                )
                continue
            if region in strata_regions:
                role = ROLE_MATERIAL_IDS
            elif region in bc_regions:
                role = ROLE_BOUNDARY_EX
            elif relative.lower().endswith(".ex"):
                role = ROLE_BOUNDARY_EX
            else:
                role = ROLE_MATERIAL_IDS
            if role == ROLE_MATERIAL_IDS and _looks_like_matlab(root / relative):
                warnings.append(
                    f"region {region}: {relative} looks like a MATLAB file, not a "
                    "PFLOTRAN region cell-id list"
                )
                role = ROLE_OTHER
            detail = {"region": region}
            if role == ROLE_MATERIAL_IDS and region in strata_materials:
                detail["material"] = strata_materials[region]
            assign(relative, role, detail, ref=True)

    # --- pattern sweep for un-referenced outputs ------------------------------
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in _JUNK_NAMES or path.name.startswith("._"):
            continue
        if "__MACOSX" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in roles:
            continue
        name = path.name
        snap = _SNAPSHOT_RE.search(name)
        xmf = _XMF_RE.search(name)
        obs = _OBS_RE.search(name)
        if name.startswith(stem + "-") and obs:
            assign(relative, ROLE_OBSERVATION, {"rank": int(obs.group(1))})
        elif name.startswith(stem + "-") and snap:
            assign(relative, ROLE_OUTPUT_SNAPSHOT, {"index": int(snap.group(1))})
        elif name.startswith(stem + "-") and xmf:
            assign(relative, ROLE_OUTPUT_XMF, {"index": int(xmf.group(1))})
        elif name == f"{stem}.h5":
            # Structured-grid runs write one HDF5 holding every timestep.
            assign(relative, ROLE_OUTPUT_SNAPSHOT, {"single_file": True})
        elif name.endswith("-domain.h5"):
            assign(relative, ROLE_DOMAIN_H5, {"primary": name == f"{stem}-domain.h5"})
        elif name.endswith("-mas.dat"):
            assign(relative, ROLE_MASS_BALANCE)
        elif name.endswith(".out"):
            assign(relative, ROLE_LOG)
        else:
            assign(relative, ROLE_OTHER)

    # --- assemble components --------------------------------------------------
    components: list[PflotranCaseComponent] = []
    for relative, role in roles.items():
        abs_path = root / relative
        try:
            size = abs_path.stat().st_size
        except OSError:
            size = None
        components.append(
            PflotranCaseComponent(
                relative_path=relative,
                role=role,
                detail=details.get(relative, {}),
                size_bytes=size,
                referenced=relative in referenced,
            )
        )
    components.sort(key=lambda c: (ROLE_ORDER.index(c.role), c.relative_path))

    role_counts: dict[str, int] = {}
    for component in components:
        role_counts[component.role] = role_counts.get(component.role, 0) + 1

    materials = _parse_materials(text)
    material_by_name = {material["name"]: material for material in materials}
    for component in components:
        if component.role != ROLE_MATERIAL_IDS:
            continue
        material_name = component.detail.get("material") or component.detail.get("region")
        material = material_by_name.get(material_name)
        if material:
            component.detail["material"] = material["name"]
            component.detail["material_id"] = material["id"]
            component.detail["material_properties"] = material["properties"]
    domain_components = [c for c in components if c.role == ROLE_DOMAIN_H5]
    primary_domain = next(
        (c.relative_path for c in domain_components if c.detail.get("primary")),
        domain_components[0].relative_path if domain_components else None,
    )
    mesh_component = next((c for c in components if c.role == ROLE_MESH), None)
    unreferenced = [c.relative_path for c in components if c.role == ROLE_OTHER]
    asset_groups = []
    for order, group in enumerate(PFLOTRAN_ASSET_GROUPS):
        roles = tuple(group["roles"])
        count = sum(role_counts.get(role, 0) for role in roles)
        if not count:
            continue
        asset_groups.append(
            {
                "key": group["key"],
                "label": group["label"],
                "order": order,
                "count": count,
                "roles": [role for role in roles if role_counts.get(role, 0)],
            }
        )

    summary = {
        "engine": "pflotran",
        "stem": stem,
        "simulation_type": simulation_type,
        "modes": modes,
        "final_time": final_time,
        "final_time_unit": final_time_unit,
        "primary_species": species,
        "materials": materials,
        "mesh": mesh_component.relative_path if mesh_component else None,
        "grid_type": (mesh_component.detail.get("grid_type") if mesh_component else None),
        "domain_h5": primary_domain,
        "n_snapshots": role_counts.get(ROLE_OUTPUT_SNAPSHOT, 0),
        "n_materials": role_counts.get(ROLE_MATERIAL_IDS, 0),
        "n_boundaries": role_counts.get(ROLE_BOUNDARY_EX, 0),
        "n_datasets": role_counts.get(ROLE_BC_DATASET_H5, 0),
        "n_components": len(components),
        "role_counts": role_counts,
        "asset_groups": asset_groups,
        "unreferenced_files": unreferenced,
    }
    if unreferenced:
        warnings.append(
            f"{len(unreferenced)} file(s) not referenced by the deck: "
            + ", ".join(unreferenced[:10])
            + ("…" if len(unreferenced) > 10 else "")
        )

    return PflotranCaseModel(
        root=root,
        input_file=deck_relative,
        stem=stem,
        components=components,
        summary=summary,
        warnings=warnings,
    )
