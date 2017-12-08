import ase.io
from mdf_toolbox import toolbox


# List of parsers at bottom


def omniparse(data_file, special_formats=None):
    """Parse a data file however possible.

    Arguments:
    data_file (file object): The data file.
    special_formats (dict): Run parsers with these parameters.

    Returns:
    dict: The metadata parsed from the file. Will be empty if no selected parser can parse data.
    """
    if special_formats is None:
        special_formats = {}
    record = {}
    # Check all parsers
    for par_name, par_func in ALL_PARSERS.items():
        if not "exclusive" in special_formats.keys() or par_name in special_formats.keys():
            try:
                parser_res = par_func(data_file, params=special_formats.get(par_name, None)
            # Exception indicates no data parsed
            except Exception as e:
                pass
            else:
                record[parser_dict["block"]] = toolbox.dict_merge(
                                                record[parser_dict["block"]],
                                                parser_res)
    return record


def parse_ase(data_file, **params):
    """Parser for data in ASE-readable formats.
    If ASE is incapable of reading the file, an exception will be raised.

    Arguments:
    data_file (file object or str): Data file, or path to the data file.
    params (any): Ignored.

    Returns:
    dict: Useful data ASE could pull out of the file.
    """
    ase_template = {
        # "constraints": None,              # No get()
        # "all_distances": None,
        # "angular_momentum": None,
        # "atomic_numbers": None,
        # "cell": None,
        "cell_lengths_and_angles": None,
        # "celldisp": None,
        # "center_of_mass": None,
        # "charges": None,
        "chemical_formula": None,
        # "chemical_symbols": None,
        # "dipole_moment": None,
        # "forces": None,
        # "forces_raw": None,               # No get()
        # "initial_charges": None,
        # "initial_magnetic_moments": None,
        # "kinetic_energy": None,
        # "magnetic_moment": None,
        # "magnetic_moments": None,
        # "masses": None,
        # "momenta": None,
        # "moments_of_inertia": None,
        # "number_of_atoms": None,
        "pbc": None,
        # "positions": None,
        # "potential_energies": None,
        # "potential_energy": None,
        # "potential_energy_raw": None,     # No get()
        # "reciprocal_cell": None,
        # "scaled_positions": None,
        # "stress": None,
        # "stresses": None,
        # "tags": None,
        "temperature": None,
        # "total_energy": None,
        # "velocities": None,
        "volume": None,
        # "filetype": None,                  # No get()
        # "num_frames": None,                # No get()
        # "num_atoms": None                  # No get()
        }

    # Read the file and process it if the reading succeeds
    result = ase.io.read(data_file)
    if not result:
        raise ValueError("No data")

    ase_dict = ase_template.copy()
    # Data with easy .get() functions
    for key in ase_dict.keys():
        try:
            ase_dict[key] = eval("result.get_" + key + "()")
        # Exceptions can be generally ignored
        except Exception as e:
            pass

    # Data without a .get()
    try:
        ase_dict["filetype"] = ase.io.formats.filetype(data_file)
    except Exception as e:
        pass
    try:
        ase_dict["num_atoms"] = len(result)
    except Exception as e:
        pass
#        if type(result) is list:
#            ase_dict["num_frames"] = len(result)
#        else:
#            ase_dict["num_atoms"] = len(result)

    # Fix up the extracted data
    none_keys = []
    for key in ase_dict.keys():
        # numpy ndarrays aren't JSON serializable
        if 'numpy' in str(type(ase_dict[key])).lower():
            ase_dict[key] = ase_dict[key].tolist()

        # None values aren't useful
        if ase_dict[key] is None:
            none_keys.append(key)
        # Remake lists with valid values
        elif type(ase_dict[key]) is list:
            new_list = []
            for elem in ase_dict[key]:
                # FixAtoms aren't JSON serializable
                if 'fixatoms' in str(elem).lower():
                    new_elem = elem.get_indices().tolist()
                else:
                    new_elem = elem
                # Only add elements with data
                if new_elem:
                    new_list.append(new_elem)
            # Only add lists with data
            if new_list:
                ase_dict[key] = new_list
            else:
                none_keys.append(key)
    # None keys aren't useful
    for key in none_keys:
        ase_dict.pop(key)

    if not ase_dict:
        raise ValueError("All data None")

    # Return correct block
    return {
        "materials": ase_dict
    }


def parse_csv(data_file, params=None):
    """Parse a CSV."""
    if not params:
        return {}
    


# Dict of all parsers as parser:function
ALL_PARSERS = {
    "ase": parse_ase,
    "csv": parse_csv,
    "json": parse_json
}
