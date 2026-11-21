"""Loader for real infrared images of an induction motor (Najafi et al., Mendeley, CC BY 4.0)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ingest.loaders.common import RAW, require

IMG_DIR = RAW / "motor_thermal" / "extracted" / "IR-Motor-bmp"
GT_DIR = RAW / "motor_thermal" / "extracted" / "40_GT_with_Refrences" / "Subset_40_Thermal_GT"

# Folder name -> condition, following the dataset readme (stator short-circuit rate per phase,
# number of phases affected, stuck rotor, cooling fan failure, healthy no-load reference).
CONDITIONS = {
    "Noload": ("healthy", "Healthy motor, no load"),
    "Fan": ("cooling_fan_failure", "Cooling fan failure"),
    "Rotor-0": ("stuck_rotor", "Stuck rotor"),
    "A10": ("stator_short_circuit", "10% short-circuit, phase A"),
    "A30": ("stator_short_circuit", "30% short-circuit, phase A"),
    "A50": ("stator_short_circuit", "50% short-circuit, phase A"),
    "A&C10": ("stator_short_circuit", "10% short-circuit, phases A and C"),
    "A&C30": ("stator_short_circuit", "30% short-circuit, phases A and C"),
    "A&B50": ("stator_short_circuit", "50% short-circuit, phases A and B"),
    "A&C&B10": ("stator_short_circuit", "10% short-circuit, three phases"),
    "A&C&B30": ("stator_short_circuit", "30% short-circuit, three phases"),
}


def list_motor_thermal_images() -> pd.DataFrame:
    """One row per image: path, folder, fault class, human description, is_fault."""
    require("motor_thermal", IMG_DIR)
    rows = []
    for folder, (fault, desc) in CONDITIONS.items():
        for p in sorted((IMG_DIR / folder).glob("*.bmp")):
            rows.append({"path": str(p), "folder": folder, "fault": fault, "description": desc,
                         "is_fault": fault != "healthy"})
    return pd.DataFrame(rows)


def read_image(path: str) -> np.ndarray:
    """Return the image as an RGB uint8 array (H, W, 3)."""
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))
