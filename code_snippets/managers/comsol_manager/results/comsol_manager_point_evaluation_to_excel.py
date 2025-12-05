from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version and open the file
comsol_manager = ComsolManager(version='6.2')
comsol = comsol_manager.comsol_model(file_path=r"../test.mph")

# point_evaluation_to_excel() function returns a pandas DataFrame with the variable values at the specified points and datasets.
# So we need to create a list with the tags (defined in Geometry) of the points we want to evaluate
point_list = ['pt1', 'pt2', 'pt3', 'pt4', 'pt5', 'pt6', ]

# We define the datasets we want to use and the variables we want to evaluate at each dataset
# Every dataset needs its own list of variables
dataset = ['dset1','dset2']
varlist = [["p", "dl.U"],["p", "dl.U"]]

# Then we call the function with the list of datasets, the list of list of variables and the list of points.
# The order is used to choose if we want all the points data for a variable and then change to the next variable (order=0) or if we want all the variables data for a point and then change to the next point (order=1)
# i.e.: order=0 -> p@pt1, p@pt2, ..., dl.U@pt1, dl.U@pt2, ...
#       order=1 -> p@pt1, dl.U@pt1, p@pt2, dl.U@pt2, ...

# The function returns a pandas DataFrame with the results and can also save it to an Excel file if file_name is provided
df = comsol.results.point_evaluation_to_excel(dataset, varlist, point_list, order=0, file_name="point_evaluation.xlsx")
