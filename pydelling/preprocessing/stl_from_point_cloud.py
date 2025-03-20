# import logging
# from pathlib import Path
#
# import numpy as np
# import open3d as o3d
# import pandas as pd
# import vtk
#
# from pydelling.config import config
# from pydelling.preprocessing import BasePreprocessing
# from pydelling.utils.decorators import set_run
#
# logger = logging.getLogger(__name__)
#
#
# class STLFromPointCloud(BasePreprocessing):
#     preprocessed_data: np.ndarray
#     is_run: bool = False
#     stl_mesh: o3d.geometry.TriangleMesh
#
#     def __init__(self, data: pd.DataFrame = None, filename: str = None):
#         super().__init__(data, filename)
#
#
#     @set_run
#     def run(self, method="ball_pivoting", *args, **kwargs):
#         logger.info("Preprocessing cloud of points")
#         assert self.is_data_ok(), "Data is not properly set-up"
#         self.point_cloud = o3d.geometry.PointCloud()
#         self.point_cloud.points = o3d.utility.Vector3dVector(self.data)
#         self.point_cloud.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=1.5, 