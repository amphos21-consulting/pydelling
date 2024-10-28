from pathlib import Path
import numpy as np
from typing import List
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)


def read_dfn_from_file(polygon_filename: str or Path = None,
                       aperture_filename: str or Path = None,
                       hydraulic_aperture_filename : str or Path = None,
                       radius_filename: str or Path = None,
                       rock_type_filename: str or Path = None,
                       polygon_vertex: List=None,
                       ):
    if polygon_vertex is None:
        polygon_vertex = []
    polygon_filename = Path(polygon_filename)
    logger.info(f'Reading polygon file: {polygon_filename}')
    logger.info(f'Reading apertures')
    with open(aperture_filename, 'r') as f:
        # f.readline()
        _apertures = []
        for line in tqdm(f.readlines(), desc='Reading apertures'):
            if 'aperture' in line:
                continue
            split_line = line.strip().split(' ')
            _apertures.append(float(split_line[-1]))

    if hydraulic_aperture_filename is None:
        hydraulic_aperture = []
    else:
        logger.info(f'Reading hydraulic apertures')
        with open(hydraulic_aperture_filename, 'r') as f:
            # f.readline()
            hydraulic_aperture = []
            for line in tqdm(f.readlines(), desc='Reading hydraulic apertures'):
                if 'hydraulic_aperture' in line:
                    continue
                split_line = line.strip().split(' ')
                hydraulic_aperture.append(float(split_line[-1]))

    logger.info(f'Reading radii')
    with open(radius_filename, 'r') as f:
        f.readline()
        f.readline()
        _radii = []
        for line in tqdm(f.readlines(), desc='Reading radii'):
            split_line = line.strip().split(' ')
            mean_radius = np.sqrt(float(split_line[0]) * float(split_line[1]))
            _radii.append(mean_radius)

    logger.info(f'Reading polygons')
    with open(polygon_filename, 'r') as f:
        f.readline()
        polygons = []
        apertures = []
        radii = []
        idx = 0
        for line in tqdm(f.readlines(), desc='Reading polygons'):
            split_line = line.strip().replace(' ', '').replace('}', '').split('{')
            split_line = [np.array(x.split(',')).astype(float) for x in split_line]
            # split_line = np.array(split_line)
            if int(split_line[0]) in polygon_vertex:
                polygons.append(split_line[1:])
                apertures.append(_apertures[idx])
                radii.append(_radii[idx])
            idx += 1

    if rock_type_filename is None:
        _rock_type = []
    else:
        logger.info(f'Reading rock type')
        with open(rock_type_filename, 'r') as f:
            # f.readline()
            _rock_type = []
            for line in tqdm(f.readlines(), desc='Reading rock type'):
                if 'Fracture' in line:
                    continue
                split_line = line.strip().split(' ')
                _rock_type.append(float(split_line[-1]))
    output_dict = {'polygons': polygons,
                    'apertures': apertures,
                    'radii': radii,
                    'rock_type': _rock_type,
                    'hydraulic_aperture': hydraulic_aperture}

    return output_dict



