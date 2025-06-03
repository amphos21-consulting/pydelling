"""
This code snippet attempts to do the following:

- Replace the TORTUOSITY_X parameter from the matrix MATERIAL from the existing value to 0.5,
- Replace one of the coordinates of the fracture REGION from the existing value to "9. 1e-4 1.".
- Add a line in CHEMISTRY/OUTPUT called PH.
- Remove the LOG_FORMULATION line from CHEMISTRY.
- Save the modified file.
"""
import pydelling.managers as pm

pf_study = pm.PflotranStudy("structured.in")
pf_study.replace_after_finding(["MATERIAL_PROPERTY matrix", "TORTUOSITY_X"], "    TORTUOSITY_X 0.5")
pf_study.replace_after_finding(["REGION fracture", "COORDINATES"], "    9. 1e-4 1.", 2)
pf_study.add_after_finding(["CHEMISTRY", "OUTPUT"], "    PH")
pf_study.remove_after_finding(["CHEMISTRY", "LOG_FORMULATION"])
pf_study.to_file(output_folder=".", output_file="structured_modif.in")
