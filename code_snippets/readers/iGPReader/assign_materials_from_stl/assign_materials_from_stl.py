from pydelling.readers.iGPReader import iGPReader

igp_path = r"assign_materials_stl_benchmark.gid"
project_name = "code_snippet_assign_materials_from_stl"

iGPReader = iGPReader(path=igp_path, project_name=project_name)

stl_files = ["Mat1.stl", "Mat2.stl"]
mat_dict = {0: "Material_1", 1: "Material_2"}

iGPReader.assign_material_from_stl(material_dict=mat_dict, stl_files=stl_files)

iGPReader.implicit_to_explicit()
