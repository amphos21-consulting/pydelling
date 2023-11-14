#Radionuclide transport with matrix diffusion and decay, no sorption
import sys
import os
try:
   pflotran_dir = os.environ['PFLOTRAN_DIR']
except KeyError:
   print('PFLOTRAN_DIR must point to PFLOTRAN installation directory and be defined in system environment variables.')
   sys.exit(1)

sys.path.append(pflotran_dir + '/src/python')

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import math
import pflotran as pft

files = []
path = []
path.append('.')

VARIABLES=["Time [y]","pH","Total Tracer [M]","Total H+ [M]","Total Br- [M]","Total HCO3- [M]","Total Ca++ [M]","Total Cl- [M]","Total K+ [M]","Total Mg++ [M]","Total Na+ [M]","Total S_siO4-- [M]","Total H4(SiO4) [M]","Total Fe++ [M]","Total Al+++ [M]","Total O2(aq) [M]","Total HS_di- [M]"]
rates =   [0, 0, 79904, 61016.8, 40078, 35453, 39098.3, 24305, 22989.769, 96060, 60080, 55845, 26981, 0, 32070]
models = ['minerals_eq_exch_max_chlorite','minerals_eq_exch_max','minerals_eq_exch_min_chlorite','minerals_eq_exch_min','minerals_eq']


files.append('input_1D_NoMatrix_minerals_eq_exch_max_chlorite-obs-1.pft')
files.append('input_1D_NoMatrix_minerals_eq_exch_max-obs-1.pft')
files.append('input_1D_NoMatrix_minerals_eq_exch_min_chlorite-obs-1.pft')
files.append('input_1D_NoMatrix_minerals_eq_exch_min-obs-1.pft')
files.append('input_1D_NoMatrix_minerals_eq-obs-1.pft')
filenames = pft.get_full_paths(path,files)
convert_to_mgL = True


for i in range(3,18):
	f = plt.figure(figsize=(8,6))
	plt.subplot(1,1,1)
	f.suptitle(VARIABLES[i-1] + " at Observation Point 4",fontsize=16)
	plt.xlabel('Time [y]')
	
	for ifile in range(len(filenames)):
		data = pft.Dataset(filenames[ifile], 1, i)
		if rates[i - 3] > 0 and convert_to_mgL:
			plt.ylabel('Total [mg/L]')
			plt.plot(data.get_array('x'),data.get_array('y')*rates[i - 3],label=models[ifile])
		else:
			plt.ylabel('Total [M]')
			plt.plot(data.get_array('x'),data.get_array('y'),label=models[ifile])

	plt.legend(loc=0)
	plt.savefig('OP4_' + VARIABLES[i-1] + '.png')














