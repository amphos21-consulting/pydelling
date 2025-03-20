"""
read_feflow_dat.py
====================
Reads a FEFLOW field and plots the field.
"""
import matplotlib.pyplot as plt
from pydelling.readers.feflow_reader import FeflowReader

path_dat = "c_layer_b_tf.dat"
reader = FeflowReader()
field = reader.read_field_dat(path_dat)
reader.plot_point_data(field)
plt.axis("off")
plt.show()
