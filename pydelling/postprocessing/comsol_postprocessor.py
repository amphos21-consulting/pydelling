import numpy as np
import pandas as pd
import mph
import re
import jpype
from tqdm import tqdm
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ComsolPostprocessor:
    """
    A class to handle postprocessing of COMSOL simulation results.

    Warning: A valid COMSOL installation is required to use this class as well as java 11 or higher. Moreover, the oficial version of python is recommended, since the Microsoft Store version could cause issues with the COMSOL API.

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

    class ComsolSurface:
        """
        A class to handle the properties of a COMSOL Surface.
        """
        def __init__(self,
                     dataset: str,
                     expression: str,
                     unit: str | None = None,
                     color_table: str | None = None,
                     color_table_discrete: int | bool = False,
                     color_table_reverse: bool = False,
                     color_table_sym: bool = False,
                     rangelist: list | None = None,
                     selection: list | None = None | bool,
                     ):
            """
            A class to handle the properties of a COMSOL Surface.
            Parameters:
                dataset (str): The name of the dataset to use for the plot. If parent, the plot group dataset is used.
                expression (str): The expression to plot.
                unit (str or None): The unit of the expression. If None default unit is used.
                color_table (str or None): The name of the color table to use for the plot. If None, the template color table is used.
                color_table_discrete (int or False): The number of discrete colors to use for the plot. If False, the color table is used as default.
                color_table_reverse (bool): If True, the color table is reversed. Defaults to False.
                color_table_sym (bool): If True, the color table is symmetric. Defaults to False.
                rangelist (list or None): The range of the plot. If None, automatic range is used.
                selection (list or None or False): A list of the domains in the selection. If None, the template selection is used. If False, all domains are used.
            """
            self.dataset = dataset
            self.expression = expression
            self.unit = unit
            self.color_table = color_table
            self.color_table_discrete = color_table_discrete
            self.color_table_reverse = color_table_reverse
            self.color_table_sym = color_table_sym
            self.rangelist = rangelist
            self.selection = selection
    
    class ComsolExportPlot:
        def __init__(self,
                     width: int,
                     height: int,
                     resolution: int,
                     font_size: int,
                     ):
            """
            A class to handle the properties of a COMSOL plot export.
            Parameters:
                width (int): The width of the plot in pixels.
                height (int): The height of the plot in pixels.
                resolution (int): The resolution of the plot in dpi.
                font_size (int): The font size of the plot.
            """
            self.width = width
            self.height = height
            self.resolution = resolution
            self.font_size = font_size

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
            tuple: **t** (numpy.ndarray) and **var_list** (list of list of lists). (i) A 1D array of unique time steps (in days) from the dataset.
            (ii) A list with a list of lists for each variable where each inner list contains the variable values
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

    def edit_plot(self,
                  duplicate: bool,
                  template: str,
                  surface_dict_list: ComsolSurface | list[ComsolSurface],
                  label: str | None = None,                    
                  dataset: str | None = None,
                  time: float | None = None,
                  export: bool = False,
                  export_properties: ComsolExportPlot | None = None,
                  export_path: str | None = None,
                ):
        """
        Plot the results of a COMSOL simulation using a template of a 2D or 3D surface.

        Parameters:
            duplicate (bool): If True, a new plot group is created. If False, the existing plot group is used.
            template (str): The tag of the template to use for the plot.
            label (str or None): The label of the plot group. If None, the label is not set. If duplicate is False, plot group name will not change but label will be used as name of exported file.
            surface_dict_list (ComsolSurface or list of ComsolSurface): A ComsolSurface object or a list of ComsolSurface objects with the properties of the surface plot(s).
            dataset (str or None): The name of the dataset to use for the plot. If None, the template dataset is used.
            time (float or None): The time step to use for the plot. If None, the template time step is used.
            export (bool): If True, the plot is exported to a file. Defaults to False.
            export_properties (ComsolExportProperties | None): A ComsolExportProperties object with the properties of the export. If None, the default properties are used.
            export_path (str or None): The path to the folder to save the exported plot. If None, the default path is used.
        """

        tags = self.model.result().tags()
        last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if re.findall(r'\d+', str(tag))])

        original_pg = self.model.result(template)
        if duplicate:
            plot_group = self.model.result().duplicate(f'pg{last_tag+1}', template)
        else:
            plot_group = original_pg

        if label is not None: plot_group.label(label)
        if isinstance(surface_dict_list, list):
            N_surfaces = len(surface_dict_list)
        elif isinstance(surface_dict_list, dict):
            N_surfaces = 1
            surface_dict_list = [surface_dict_list]

        def config_surface(surface, surface_dict):
            surface.set('expr', surface_dict.expression)
            if surface_dict.unit is not None: surface.set('unit', surface_dict.unit)

            if surface_dict.color_table is not None: surface.set('colortable', surface_dict.color_table)
            if surface_dict.color_table_discrete is False: surface.set('colortabletype', 'continuous')
            if surface_dict.color_table_discrete:
                surface.set('colortabletype', 'discrete')
                surface.set('bandcount', float(surface_dict.color_table_discrete))
            if surface_dict.color_table_reverse: surface.set('colortablerev', 'on')
            if not surface_dict.color_table_reverse: surface.set('colortablerev', 'off')
            if surface_dict.color_table_sym: surface.set('colortablesym', 'on')
            if not surface_dict.color_table_sym: surface.set('colortablesym', 'off')

            if surface_dict.rangelist is not None:
                surface.set('rangecoloractive', 'on')
                surface.set('rangecolormin', float(surface_dict.rangelist[0]))
                surface.set('rangecolormax', float(surface_dict.rangelist[1]))
            else: surface.set('rangecoloractive', 'off')

            if surface_dict.selection is not None:
                try:
                    surface.feature('sel1')
                except:
                    surface.create('sel1', 'Selection')

                if surface_dict.selection is False:
                    surface.feature('sel1').active(False)
                else:
                    JIntArray = jpype.JArray(jpype.JInt)
                    intlist = JIntArray(surface_dict.selection)
                    surface.feature('sel1').selection().set(intlist)

            if dataset is not None: plot_group.set('data', dataset)
            if time is not None: plot_group.set('t', float(time))

        if N_surfaces == 1:
            surface_dict = surface_dict_list[0]
            surface = plot_group.feature(plot_group.feature().tags()[0])
            config_surface(surface, surface_dict)

        elif N_surfaces > 1:
            if dataset is not None: plot_group.set('data', dataset)
            if time is not None: plot_group.set('t', float(time))

            for i in range(N_surfaces):
                surface_dict = surface_dict_list[i]
                surface = plot_group.feature(plot_group.feature().tags()[i])
                config_surface(surface, surface_dict)

        plot_group.run()

        if export:
            # Check if 'img1' already exists, if so, remove it before creating
            export_tags = self.model.result().export().tags()
            if 'img1' in export_tags:
                image_export = self.model.result().export().remove('img1')
            image_export = self.model.result().export().create('img1', 'Image')

            image_export.set('plotgroup', f'pg{last_tag+1}')
            if label is None:
                raise ValueError("If exporting, label must be set to name the exported file.")
            logger.info(f"Exporting image pg{last_tag+1}_{label}.png")
            if export_path is None:
                image_export.set('pngfilename', f'pg{last_tag+1}_{label}.png')
            else:
                image_export.set('pngfilename', f'{export_path}/pg{last_tag+1}_{label}.png')
            if export_properties is not None:
                image_export.set('resolution', float(export_properties.resolution))
                image_export.set('unit', 'px')
                image_export.set('size','manualweb')
                image_export.set('width', float(export_properties.width))
                image_export.set('height', float(export_properties.height))
                image_export.set('fontsize', float(export_properties.font_size))
            image_export.run()
        
    def run_derived_value(self,
                          derived_value_tag: str,
                          table_tag: str | None = None,
                          export_path: str | None = None,
                          ifexists: str = 'overwrite',
                          ):
        """
        Run a derived value and optionally export the results to a file.
        Arguments:
            derived_value_tag (str): The tag of the derived value to run.
            table_tag (str | None): The tag of the table to export the results to. If None, a new table is created.
            export_path (str | None): The path to export the results to. If None, the results are not exported.
            ifexists (str): What to do if the export file already exists. Options are 'overwrite' and 'append'. Defaults to 'overwrite'.
        """
        if table_tag is None:
            tables = self.model.result().table().tags()
            last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tables if tag.startswith('tbl') and re.findall(r'\d+', str(tag))])
            table_tag = f'tbl{last_tag+1}'
            self.model.result().table().create(table_tag, 'Table')
        else:
            self.model.result().table(table_tag).clearTableData()
        
        logger.info(f"Running derived value {derived_value_tag}")
        self.model.result().numerical(derived_value_tag).set('table', table_tag)
        self.model.result().numerical(derived_value_tag).setResult()

        if export_path is not None:
            logger.info(f"Exporting derived value {derived_value_tag} to {export_path}")
            export_list = self.model.result().export().tags()
            if 'tbl1' in export_list:
                export = self.model.result().export('tbl1')
            else:
                export = self.model.result().export().create('tbl1', 'Table')
            export.set('header', False)
            export.set('table', table_tag)
            export.set('ifexists', ifexists)
            export.set('filename', export_path)
            export.run()


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