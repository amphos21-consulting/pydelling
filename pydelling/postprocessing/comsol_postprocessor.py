import numpy as np
import pandas as pd
import mph
import re
from tqdm import tqdm
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ComsolPostprocessor:
    """
    A class to handle postprocessing of COMSOL simulation results.
    """

    def __init__(self,
                file_path: str,
                version: str | None = None,
                comp_tag: str = 'comp1',
                geom_tag: str = 'geom1',
                ):
        """
        Initialize the ComsolPostprocessor with the path to the COMSOL file.

        Parameters:
            file_path (str): Path to the COMSOL file.
            version (str or bool): The version of COMSOL to use. If False, the default version is used.
            comp_tag (str): The tag of the component in the COMSOL model. Defaults to 'comp1'.
            geom_tag (str): The tag of the geometry in the specified component. Defaults to 'geom1'.
        """
        self.file_path = file_path
        self.client = mph.start(version=version)
        self.model_standalone = self.client.load(file_path)
        self.model = self.model_standalone.java
        self.comp = self.model.modelNode(comp_tag)
        self.geom = self.comp.geom(geom_tag)


    def get_variable_evolution_at_point(self, 
                                        dataset: str, 
                                        var_list: list, 
                                        point_list: list):
        """
        Get the evolution of specified variables at specified points over time.

        Parameters:
            dataset (str): The tag of the dataset of the solution.
            var_list (list of str): A list with the names of the variables to evaluate.
            point_list (list of list): A list of points' geomertry tags where the variable evolution is to be computed.
            coord_labels (list of str): A list with the names of the coordinates to evaluate. Defaults to ['r', 'z'].
        Returns:
            tuple: t (numpy.ndarray): A 1D array of unique time steps (in days) from the dataset.
            tuple: var_list (list of list of lists): A list with a list of lists for each variable where each inner list contains the variable values
            at the corresponding point in `point_list` over time.
        """
        points = [self.geom.feature(name) for name in point_list]

        # Get coordinates of points
        coords_list = []
        for point in points:
            coords = point.getDoubleArray('p')
            coords_list.append(coords)

        datasetname = self.model.result().dataset(dataset).name()
        datasetname = str(datasetname.replace('/', '//'))
        
        coord_java = list(self.comp.spatialCoord())
        coord_labels = [str(coord_java[i]) for i in range(len(coord_java))]

        if self.geom.getSDim() == 2:
            if self.geom.isAxisymmetric():
                coord_labels = [coord_labels[0], coord_labels[2]]
            else:
                coord_labels = [coord_labels[0], coord_labels[1]]
        elif self.geom.getSDim() == 1:
            coord_labels = coord_labels[0]

        x, y = self.model_standalone.evaluate(coord_labels, dataset=datasetname)
        t = self.model_standalone.evaluate('t', unit='d', dataset=datasetname)
        t = np.unique(t)
        var_results = []
        var_eval = []
        for i in range(len(var_list)):
            var = self.model_standalone.evaluate(var_list[i], dataset=datasetname)
            var_eval.append(var)
            var_results.append([[] for _ in range(len(coords_list))])
        
        for n in tqdm(range(len(t)),desc="Processing time steps"):
            mesh_coords = np.array([x[n], y[n]]).T
            points_idx = []
            for i in range(len(coords_list)):
                distances = np.linalg.norm(mesh_coords - coords_list[i], axis=1)
                nearest_idx = np.argmin(distances)
                points_idx.append(nearest_idx)
                for k in range(len(var_list)):
                    var_results[k][i].append(var_eval[k][n][points_idx[i]])
        return t, var_results
    
    def point_evaluation_to_excel(self,
                                  dataset,
                                  var_list: list,
                                  point_list: list,
                                  order: int = 0,
                                  export: bool = True,
                                  file_name: str = 'point_evaluation.xlsx',
                                  ):
        """
        Evaluate the variables at the specified points and save the results to an Excel file.

        Parameters:
            dataset (str or list): A dataset or a list of datasets to evaluate.
            var_list (list): A list of variables to evaluate. Or a list of lists of variables, one list for each dataset.
            point_list (list): A list of points to evaluate.
            order (int): The order of the evaluation. Defaults to 0. 0 stands for every point for each variable, and 1 for every variable for each point.
            file_name (str): The name of the Excel file to save the results. Defaults to 'point_evaluation.xlsx'.
        """
        if isinstance(dataset, str):
            dataset = [dataset]

        headlist = ['t']
        var_list_temp = var_list[0] if isinstance(var_list[0], list) else var_list
        if order == 0:
            for i, var in enumerate(var_list_temp):
                for j, point in enumerate(point_list):
                    headlist.append(f'{var}_{point}')
        elif order == 1:
            for i, point in enumerate(point_list):
                for j, var in enumerate(var_list_temp):
                    headlist.append(f'{point}_{var}')
        else:
            raise ValueError("order must be 0 or 1")
        
        df = pd.DataFrame(columns=headlist)

        for ds_idx, ds in enumerate(dataset):
            var_list_temp = var_list[ds_idx] if isinstance(var_list[0], list) else var_list
            df_temp = pd.DataFrame()
            t, var_results = self.get_variable_evolution_at_point(ds, var_list_temp, point_list)
            df_temp['t'] = t
            if order == 0:
                for i, var in enumerate(var_list_temp):
                    for j, point in enumerate(point_list):
                        df_temp[f'{var}_{point}'] = var_results[i][j]
            elif order == 1:
                for i, point in enumerate(point_list):
                    for j, var in enumerate(var_list_temp):
                        df_temp[f'{point}_{var}'] = var_results[j][i]
            else:
                raise ValueError("order must be 0 or 1")
            df_temp.columns = headlist
            df = pd.concat([df, df_temp], ignore_index=True)

        # Save to Excel
        logger.info(f"Saving results to {file_name}")
        df.to_excel(file_name, index=False)

        return df

    def plot_profiles():
        pass

    def duplicate_plot(self,
                       template: str,
                       expression: str,
                       unit: str | None = None,
                       label: str | None = None,
                       color_table: str | None = None,
                       color_table_discrete: int | None = None,
                       color_table_reverse: bool = False,
                       color_table_sym: bool = False,
                       dataset: str | None = None,
                       time: float | None = None,
                       rangelist: list | None = None,
                       export: bool = False,
                       export_properties: dict | None = None,
                       export_path: str | None = None,
                       ):
        """
        Plot the results of a COMSOL simulation using a template of a 2D or 3D surface.

        Parameters:
            template (str): The tag of the template to use for the plot.
            expression (str): The expression to plot.
            unit (str or None): The unit of the expression. If None default unit is used.
            label (str or None): The label to use for the plot. If None, the template label is used.
            color_table (str or None): The name of the color table to use for the plot. If None, the template color table is used.
            color_table_discrete (int or None): The number of discrete colors to use for the plot. If None, the color table is used as default.
            color_table_reverse (bool): If True, the color table is reversed. Defaults to False.
            color_table_sym (bool): If True, the color table is symmetric. Defaults to False.
            dataset (str or None): The name of the dataset to use for the plot. If None, the template dataset is used.
            time (float or None): The time step to use for the plot. If None, the template time step is used.
            rangelist (list or None): The range of the plot. If None, automatic range is used.
            export (bool): If True, the plot is exported to a file. Defaults to False.
            export_properties (dict) [width, height, resolution, font_size]: A dictionary with the properties of the export. If None, the default properties are used.
            export_path (str or None): The path to the folder to save the exported plot. If None, the default path is used.
        """

        tags = self.model.result().tags()
        last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if re.findall(r'\d+', str(tag))])

        original_pg = self.model.result(template)
        plot_group = self.model.result().duplicate(f'pg{last_tag+1}', template)
        if label is not None: plot_group.label(label)
        surface = plot_group.feature(plot_group.feature().tags()[0])
        surface.set('expr', expression)
        if unit is not None: surface.set('unit', unit)

        if color_table is not None: surface.set('colortable', color_table)
        if color_table_discrete is None: surface.set('colortabletype', 'continuous')
        if color_table_discrete is not None:
            surface.set('colortabletype', 'discrete')
            surface.set('bandcount', float(color_table_discrete))
        if color_table_reverse: surface.set('colortablerev', 'on')
        if not color_table_reverse: surface.set('colortablerev', 'off')
        if color_table_sym: surface.set('colortablesym', 'on')
        if not color_table_sym: surface.set('colortablesym', 'off')

        if dataset is not None: plot_group.set('data', dataset)
        if time is not None: plot_group.set('t', float(time))
        if rangelist is not None:
            surface.set('rangecoloractive', 'on')
            surface.set('rangecolormin', float(rangelist[0]))
            surface.set('rangecolormax', float(rangelist[1]))
        else: surface.set('rangecoloractive', 'off')

        plot_group.run()

        if export:
            # Check if 'img1' already exists, if so, remove it before creating
            export_tags = self.model.result().export().tags()
            if 'img1' in export_tags:
                image_export = self.model.result().export().feature('img1')
            else: image_export = self.model.result().export().create('img1', 'Image')

            image_export.set('plotgroup', f'pg{last_tag+1}')
            logger.info(f"Exporting image pg{last_tag+1}_{expression}.png")
            if export_path is None:
                image_export.set('pngfilename', f'pg{last_tag+1}_{expression}.png')
            else:
                image_export.set('pngfilename', f'{export_path}/pg{last_tag+1}_{expression}.png')
            if export_properties is not None:
                image_export.set('resolution', float(export_properties['resolution']))
                image_export.set('unit', 'px')
                image_export.set('size','manualweb')
                image_export.set('width', float(export_properties['width']))
                image_export.set('height', float(export_properties['height']))
                image_export.set('fontsize', float(export_properties['font_size']))
            image_export.run()
        

    def create_special_dataset():
        pass

    def save(self, save_path: str = None):
        """
        Save the COMSOL model to a file.
        Parameters:
            save_path (str): The path to save the COMSOL model. If None, the original file path + _postprocess is used.
        """
        if save_path is None: self.model.save(self.file_path.split('.')[0] + '_postprocess.mph')
        else: self.model.save(save_path)
        self.client.close()