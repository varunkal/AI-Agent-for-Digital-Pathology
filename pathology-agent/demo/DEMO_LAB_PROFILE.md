## Overview
This lab studies colorectal cancer recurrence using Xenium spatial transcriptomics
with matched H&E. Cohort A is the ColoCare recurrence cohort.

## Naming conventions
Cohorts are named cohortA, cohortB. A file suffixed _v2 supersedes the earlier
version. Notebooks prefixed qc_ are quality control for the named cohort.

## Standard pipelines
The standard order is: QC -> normalization -> cell typing -> niche discovery ->
outcome association -> figures. Each step has one script or notebook.

## Quality control standards
House defaults: minimum 10 transcripts per cell, minimum 3 cells per gene.
Leiden resolution 0.7 is the lab default for cell typing; it is a convention,
not a tuned value, and the rationale was never formally recorded.

## Preferred statistical methods
Outcome association uses Cox proportional hazards adjusted for stage and age,
with Benjamini-Hochberg correction across niches.
