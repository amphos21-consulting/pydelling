"""Generic detached SSH worker: python -m pydelling.managers.batch_worker job folder."""

import json
import sys
from pathlib import Path

from .batch import LocalExecutor, atomic_json, cancel_requested
from .pflotran_manager import PflotranManager
from .pflotran_study import PflotranStudy


def main():
    job = json.loads(Path(sys.argv[1]).read_text())
    folder = Path(sys.argv[2])
    manager = PflotranManager()
    for description in job["studies"]:
        base = Path(job["inputs"]) / description["name"]
        study = PflotranStudy(str(base / description["input"]), study_name=description["name"])
        for name in description["auxiliary"]:
            study.add_auxiliary_file(base / "input_files" / name)
        manager.add_study(study)
    executor = LocalExecutor(**job["executor"])
    with executor.pipeline(folder):
        atomic_json(folder / "campaign.json", {"state": "running"})
        try:
            result = manager.run_batch(
                executor,
                folder,
                job["requirements"],
                resume=job["resume"],
                provenance=job["provenance"],
                batch_name=job["batch_name"],
            )
            state = "completed" if result.successful else "failed"
            if not result.successful and cancel_requested(folder):
                state = "cancelled"
            atomic_json(folder / "campaign.json", {"state": state})
        except Exception as exc:
            atomic_json(folder / "campaign.json", {"state": "failed", "error": str(exc)})
            raise


if __name__ == "__main__":
    main()
