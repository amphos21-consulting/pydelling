from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')
comsol = manager.comsol_model(f"test.mph")
# ComsolManager.ComsolModel is the object that manage a COMSOL file
# A ComsolModel has a subclass ComsolStudy
# In order to run a sequence, a list of ComsolStudy's has to be given
std1 = comsol.study('std1')
std2 = comsol.study('std2')
studies = [std1, std2]

comp = comsol.component('comp1')

# Finally, run the sequence
comsol.run_sequence(studies,
                    comp,
                    'minpt1',
                    'dl.pA')

