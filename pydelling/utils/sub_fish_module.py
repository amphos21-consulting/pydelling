"""
Subsurface Fracture Independent Solutions Helper (SubFISH)
"""
import logging

import mpmath as mp
import numpy as np
import scipy.special as scsp

logger = logging.getLogger(__name__)

class SubfishException(Exception):
    """Exception raised by SubFISH transport helper routines.

    Category: utilities.
    Tags: subfish, exception, transport.
    Usage: to recognize errors originating from the
        SubFISH analytical solution module.
    """

    pass


def calculate_tang(tang_data):
    logger.info('Calculating Tang solution')
    # Load parameters
    b = tang_data["b"]
    theta = tang_data["poros"]
    tau = tang_data["tort"]
    alpha = tang_data["alpha"]
    D_star = tang_data["Dw"]
    my_lambda = tang_data["lambda"]
    R_prime = tang_data["Rm"]
    R = tang_data["Rf"]
    v = tang_data["v"]
    l = tang_data["l"]

    min_time = float(tang_data["min_time"])
    max_time = float(tang_data["max_time"])
