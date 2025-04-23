from pydelling.readers.iGPReader import iGPReader
from mpi4py import MPI
import logging
logger = logging.getLogger(__name__)

logger.info("Run script manually with:")
logger.info("mpirun -np {num_of_processes} --bind-to core python assign_materials_from_stl_parallel.py")

igp_path = r"assign_materials_stl_benchmark.gid"
project_name = "code_snippet_assign_materials_from_stl"

comm = MPI.COMM_WORLD
size = comm.Get_size()
rank = comm.Get_rank()

iGPReader = iGPReader(path=igp_path, project_name=project_name)

stl_files = ["Mat1.stl", "Mat2.stl"]
mat_dict = {0: "Material_1", 1: "Material_2"}

iGPReader.assign_material_from_stl(material_dict=mat_dict, stl_files=stl_files, mpi_comm=comm, rank=rank, size=size)

if rank==0: iGPReader.implicit_to_explicit()
