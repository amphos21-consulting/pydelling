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

path = []
path.append('.')

VARIABLES=["X [m]","Y [m]","Z [m]","pH","Total Tracer [M]","Total H+ [M]","Total Br- [M]","Total HCO3- [M]","Total Ca++ [M]","Total Cl- [M]","Total K+ [M]","Total Mg++ [M]","Total Na+ [M]","Total S_siO4-- [M]","Total H4(SiO4) [M]","Total Fe++ [M]","Total Al+++ [M]","Total O2(aq) [M]","Total HS_di- [M]"]
rates =   [0, 0, 79904, 61016.8, 40078, 35453, 39098.3, 24305, 22989.769, 96060, 60080, 55845, 26981, 0, 32070]

files = pft.get_tec_filenames('input_1D_NoMatrix_minerals_eq',[0,1,2,3,4,5,6])
filenames = pft.get_full_paths(path,files)
convert_to_mgL = True



for i in range(4,19):
	f = plt.figure(figsize=(6,6))
	plt.subplot(1,1,1)
	f.suptitle(VARIABLES[i],fontsize=16)
	plt.ylabel('Z [m]')

	for ifile in range(len(filenames)):
		data = pft.Dataset(filenames[ifile],i + 1,3)
		if rates[i - 4] > 0 and convert_to_mgL:
			plt.xlabel('Total [mg/L]')
			plt.plot(data.get_array('x')*rates[i - 4],data.get_array('y')-1000,label='{} years'.format(data.title))
		else:
			plt.xlabel('Total [M]')
			plt.plot(data.get_array('x'),data.get_array('y')-1000,label='{} years'.format(data.title))

	plt.legend(loc=0)
	plt.savefig('minerals_eq_' + VARIABLES[i] + '.png')






