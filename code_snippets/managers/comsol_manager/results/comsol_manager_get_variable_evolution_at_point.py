import numpy as np
import matplotlib.pyplot as plt
from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version and open the file
comsol_manager = ComsolManager(version='6.2')
comsol = comsol_manager.comsol_model(file_path=r"../test.mph")
# Load a custom style that emulates COMSOL plots (optional)
plt.style.use(r"COMSOLstyle.mplstyle")


# get_variable_evolution_at_point() function returns the time and the variable values at the specified points.
# So we need to create a list with the tags (defined in Geometry) of the points we want to evaluate
point_list = ['pt1', 'pt2', 'pt3', 'pt4', 'pt5', 'pt6']


# Then we call the function with the dataset tag of the solution we want to use, the list of variables we want to evaluate and the list of points
# It returns the time and a list of lists with the variable values at each point
t, var = comsol.results.get_variable_evolution_at_point('dset2', ["p", "dl.U"], point_list)


# Now we can plot the results

point_labels = ['P00', 'P01', 'P02', 'P03', 'P04', 'P05']

for i in range(len(point_list)):
    plt.plot(t, np.array(var[0][i])/1e3, label=point_labels[i])
plt.xlabel("Time (d)")
plt.ylabel("Pressure (kPa)")
plt.legend()
plt.show()

for i in range(len(point_list)):
    plt.plot(t, var[1][i], label=point_labels[i])
plt.xlabel("Time (d)")
plt.ylabel("Velocity (m/s)")
plt.legend()
plt.show()
