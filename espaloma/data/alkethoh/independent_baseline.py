# separate parameters for every atom, bond, angle, torsion, up to symmetry

import numpy as np
from espaloma.data.alkethoh.data import offmols
from openeye import oechem
from openforcefield.topology import Molecule
from tqdm import tqdm


def atom_symmetry_classes(offmol: Molecule):
    oemol = offmol.to_openeye()
    oechem.OEPerceiveSymmetry(oemol)
    symmetry_classes = np.array([atom.GetSymmetryClass() for atom in oemol.GetAtoms()])
    return symmetry_classes


def canonicalize_order(tup):
    return min(tup, tup[::-1])


def get_unique_bonds(offmol):
    """
    pair_inds:
        array of shape (n_bonds, 2)
    bond_inds:
        array of shape (n_bonds,)
    """

    sym = atom_symmetry_classes(offmol)

    pair_inds = []
    bond_tups = []

    for bond in offmol.bonds:
        pair_inds.append((bond.atom1_index, bond.atom2_index))
        tup = (sym[bond.atom1_index], sym[bond.atom2_index])
        bond_tups.append(canonicalize_order(tup))

    pair_inds = np.array(pair_inds)

    bond_set = set(bond_tups)
    bond_ind_map = dict(zip(bond_set, range(len(bond_set))))
    bond_inds = np.array([bond_ind_map[tup] for tup in bond_tups])

    return pair_inds, bond_inds


def get_unique_angles(offmol):
    """
    triple_inds:
        array of shape (n_angles, 3)
    angle_inds:
        array of shape (n_angles,)
    """

    sym = atom_symmetry_classes(offmol)

    triple_inds = []
    angle_tups = []

    for angle in offmol.angles:
        triple_inds.append(tuple((atom.molecule_atom_index for atom in angle)))
        tup = tuple(sym[atom.molecule_atom_index] for atom in angle)
        angle_tups.append(canonicalize_order(tup))

    triple_inds = np.array(triple_inds)

    angle_set = set(angle_tups)
    angle_ind_map = dict(zip(angle_set, range(len(angle_set))))
    angle_inds = np.array([angle_ind_map[tup] for tup in angle_tups])

    return triple_inds, angle_inds


def get_unique_torsions(offmol):
    """
    quad_inds:
        array of shape (n_angles, 4)
    torsion_inds:
        array of shape (n_angles,)
    """

    sym = atom_symmetry_classes(offmol)

    quad_inds = []
    torsion_tups = []

    for torsion in offmol.propers:
        quad_inds.append(tuple((atom.molecule_atom_index for atom in torsion)))
        tup = tuple(sym[atom.molecule_atom_index] for atom in torsion)
        torsion_tups.append(canonicalize_order(tup))

    quad_inds = np.array(quad_inds)

    torsion_set = set(torsion_tups)
    torsion_ind_map = dict(zip(torsion_set, range(len(torsion_set))))
    torsion_inds = np.array([torsion_ind_map[tup] for tup in torsion_tups])

    return quad_inds, torsion_inds


# TODO: make the import structure clearer
from espaloma.data.alkethoh.mm_utils import harmonic_bond_potential, harmonic_angle_potential, \
    periodic_torsion_potential
from espaloma.data.alkethoh.neural_baseline import compute_distances, compute_angles, compute_torsions
from espaloma.data.alkethoh.neural_baseline import get_snapshots_and_energies


def compute_harmonic_bond_potential(xyz, params, pair_inds, bond_inds):
    """
    :param xyz:
    :param params:
        array of length 2 * n_unique
    :param pair_inds:
        array of shape (len(offmol.bonds), 2)
    :param bond_inds:
        numpy array of length len(offmol.bonds),
        taking integer values in range 0 through n_unique
    :return:
    """

    n_unique = int(len(params) / 2)
    ks, r0s = params[:n_unique], params[n_unique:]
    k, r0 = ks[bond_inds], r0s[bond_inds]

    r = compute_distances(xyz, pair_inds)
    return np.sum(harmonic_bond_potential(r, k, r0), axis=1)


def compute_harmonic_angle_potential(xyz, params, triple_inds, angle_inds):
    """

    :param xyz:
    :param params:
        array of length 2 * n_unique
    :param triple_inds:
        array of shape (len(offmol.angles), 3)
    :param angle_inds:
        numpy array of length len(offmol.angles),
        taking integer values in range 0 through n_unique
    :return:
    """

    n_unique = int(len(params) / 2)
    ks, theta0s = params[:n_unique], params[n_unique:]
    k, theta0 = ks[angle_inds], theta0s[angle_inds]

    theta = compute_angles(xyz, triple_inds)
    return np.sum(harmonic_angle_potential(theta, k, theta0), axis=1)


n_periodicities = 6
periodicities = np.arange(n_periodicities) + 1


def compute_periodic_torsion_potential(xyz, params, quad_inds, torsion_inds):
    """

    :param xyz:
    :param params:
        length ( 2 * n_unique * n_periodicities )
    :param quad_inds:
    :param torsion_inds:
    :return:
    """
    theta = compute_torsions(xyz, quad_inds)

    n_unique = int(len(params) / (2 * n_periodicities))
    params = np.reshape(params, (n_unique, (2 * n_periodicities)))

    ks, phases = params[torsion_inds][:, :n_periodicities], params[torsion_inds][:, n_periodicities:]

    # TODO; clean this up a bit
    periodicities_ = np.array([periodicities for _ in ks])

    return np.sum(periodic_torsion_potential(theta, ks, phases, periodicities_), axis=1)


if __name__ == '__main__':
    name = 'AlkEthOH_r1155'
    offmol = offmols[name]
    traj, _, ani1ccx_energies = get_snapshots_and_energies(name)
    xyz = traj.xyz

    # bonds
    pair_inds, bond_inds = get_unique_bonds(offmol)
    n_unique_bonds = len(set(bond_inds))
    n_bond_params = 2 * n_unique_bonds
    bond_params = np.random.randn(n_bond_params)

    bond_energies = compute_harmonic_bond_potential(xyz, bond_params, pair_inds, bond_inds)
    print('bond energies mean', bond_energies.mean())

    # angles
    triple_inds, angle_inds = get_unique_angles(offmol)
    n_unique_angles = len(set(angle_inds))
    n_angle_params = 2 * n_unique_angles
    angle_params = np.random.randn(n_angle_params)
    angle_energies = compute_harmonic_angle_potential(xyz, angle_params, triple_inds, angle_inds)
    print('angle energies mean', angle_energies.mean())

    # torsions
    quad_inds, torsion_inds = get_unique_torsions(offmol)
    n_unique_torsions = len(set(torsion_inds))
    n_torsion_params = 2 * n_unique_torsions * n_periodicities
    torsion_params = np.random.randn(n_torsion_params)
    torsion_energies = compute_periodic_torsion_potential(xyz, torsion_params, quad_inds, torsion_inds)
    print('torsion energies mean', torsion_energies.mean())

    params = np.hstack([bond_params, angle_params, torsion_params])

    from simtk import unit
    from espaloma.data.alkethoh.mm_utils import get_sim, set_positions, get_energy, get_nb_energy
    valence_energies = []
    sim = get_sim(name)
    for conf in xyz:
        set_positions(sim, conf * unit.nanometer)
        U_tot = get_energy(sim)
        U_nb = get_nb_energy(sim)
        valence_energies.append(U_tot - U_nb)
    valence_target = np.array(valence_energies)

    def loss(all_params):
        bond_params = all_params[:n_bond_params]
        angle_params = all_params[n_bond_params:(n_bond_params + n_angle_params)]
        torsion_params = all_params[-n_torsion_params:]

        bond_energies = compute_harmonic_bond_potential(xyz, bond_params, pair_inds, bond_inds)
        angle_energies = compute_harmonic_angle_potential(xyz, angle_params, triple_inds, angle_inds)
        torsion_energies = compute_periodic_torsion_potential(xyz, torsion_params, quad_inds, torsion_inds)
        
        U_valence = bond_energies + angle_energies + torsion_energies

        return np.sum((valence_target - U_valence) ** 2)



    # Atom types
    n_unique = 0
    n_total = 0

    symmetry_classes = {}
    for name in tqdm(offmols):
        offmol = offmols[name]
        symmetry_classes[name] = atom_symmetry_classes(offmol)
        if offmol.n_atoms != len(symmetry_classes[name]):
            print(f'{offmol.n_atoms} != {len(symmetry_classes[name])}')

        n_unique += len(set(symmetry_classes[name]))
        n_total += offmol.n_atoms

    print(f'atoms: {n_unique} / {n_total} = {n_unique / n_total:.3f}')

    # Bond types
    n_unique = 0
    n_total = 0
    for name in tqdm(offmols):
        pair_inds, bond_inds = get_unique_bonds(offmols[name])

        n_unique += len(set(bond_inds))
        n_total += len(bond_inds)
    print(f'bonds: {n_unique} / {n_total} = {n_unique / n_total:.3f}')

    # Angle types
    n_unique = 0
    n_total = 0
    for name in tqdm(offmols):
        triple_inds, angle_inds = get_unique_angles(offmols[name])

        n_unique += len(set(angle_inds))
        n_total += len(angle_inds)
    print(f'angles: {n_unique} / {n_total} = {n_unique / n_total:.3f}')

    # Torsion types
    n_unique = 0
    n_total = 0
    for name in tqdm(offmols):
        quad_inds, torsion_inds = get_unique_torsions(offmols[name])

        n_unique += len(set(torsion_inds))
        n_total += len(torsion_inds)
    print(f'torsions: {n_unique} / {n_total} = {n_unique / n_total:.3f}')
