"""Tumour interface analysis: distance from each cell to the tumour boundary.

Reads results/niche_assignments.csv produced by src/niche_discovery.py and the
tumour masks, computes a signed distance for every cell, then bins cells into
interface zones.

Writes results/interface_distances.csv
"""
import numpy as np

BOUNDARY_BIN_UM = 50
MAX_DISTANCE_UM = 500


def distance_to_interface(adata, tumour_mask):
    signed = signed_distance(adata.obsm["spatial"], tumour_mask)
    return np.clip(signed, -MAX_DISTANCE_UM, MAX_DISTANCE_UM)


def bin_by_zone(distances, bin_um=BOUNDARY_BIN_UM):
    return np.floor(distances / bin_um).astype(int)
