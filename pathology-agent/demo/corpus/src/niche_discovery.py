"""Spatial niche discovery.

Builds a k=15 spatial neighbour graph over cell centroids, computes
neighbourhood composition vectors, then k-means with k=8 niches.
Writes results/niche_assignments.csv
"""
import numpy as np
from sklearn.cluster import KMeans

K_NEIGHBORS = 15
N_NICHES = 8

def discover_niches(adata):
    composition = neighborhood_composition(adata, k=K_NEIGHBORS)
    return KMeans(n_clusters=N_NICHES, random_state=0).fit_predict(composition)
