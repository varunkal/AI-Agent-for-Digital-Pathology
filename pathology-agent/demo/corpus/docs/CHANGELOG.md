# Pipeline changelog

## Cohort B added
Cohort B follows the Cohort A pipeline with two deliberate differences:
Leiden resolution is 1.0 rather than the house default of 0.7, and the Cox
model additionally adjusts for sex. QC thresholds are unchanged.

## QC thresholds centralised
Cell and gene filtering moved out of the individual QC notebooks and into
src/qc_utils.py so every cohort filters identically. The pipeline YAML files
still record the values for provenance and must be kept in step with the code.
