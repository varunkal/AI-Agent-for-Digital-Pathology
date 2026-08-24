# Levy Lab profile

<!--
WHAT THIS IS
This file is how the assistant learns to behave like someone who works in this
lab, rather than a generic assistant with a search box. Retrieval finds passages
that resemble the question; it cannot know that this lab always normalizes a
certain way, or what `cohortA/` refers to, or which statistical test is the house
default. That knowledge lives here.

HOW TO USE IT
  1. Copy this file to LAB_PROFILE.md
  2. Fill in what you know. Leave the rest as TODO — the code reports which
     sections are still empty rather than pretending the profile is complete.
  3. Anyone in the lab can edit it. It is plain Markdown on purpose.

WHAT NOT TO PUT HERE
  - No patient data, specimen IDs, or anything identifiable.
  - No secrets, paths to restricted data, or credentials.
  - This is conventions and norms, not results.

WHY IT IS SEPARATE FROM THE FILES
The assistant is told explicitly that this is background knowledge and NOT a
citable source. If a question asks for a specific fact, it must still come from a
real file. Otherwise the assistant would start citing "the lab context" as
evidence, which would quietly break the grounding measurement.

Sections below match the categories named in the project description. Keep the
`## ` headings exactly as written — the parser keys on them.
-->

## Overview
<!-- One paragraph: what the lab works on, main data types, main goals. -->
TODO

## Naming conventions
<!-- How are cohorts, samples, runs, and files named? What do prefixes and
     suffixes mean? Example: does `cohortA_v2_final.h5ad` follow a pattern? -->
TODO

## File structure
<!-- Where do raw data, processed data, notebooks, scripts, results and figures
     live? What is the standard project layout on Discovery? -->
TODO

## Standard pipelines
<!-- The normal order of operations for the lab's common workflows. Example:
     Xenium -> QC -> normalization -> cell typing -> niche discovery -> outcome
     association. Name the scripts or notebooks that usually do each step. -->
TODO

## Quality control standards
<!-- Default thresholds and what triggers exclusion. Minimum transcripts per
     cell, minimum cells per gene, acceptable failure rates, when a sample is
     dropped. -->
TODO

## Preferred statistical methods
<!-- Which tests the lab uses for which situations, standard covariates, and how
     multiple testing is handled. -->
TODO

## Data structures
<!-- Common object layouts. For AnnData: what lives in .obs, .var, .obsm, .uns?
     Which keys are standard across projects? -->
TODO

## Figure conventions
<!-- Colour schemes, panel layouts, required annotations, file formats and DPI,
     where figures get written. -->
TODO

## Interpretation norms
<!-- How the lab reads its own results. What counts as a meaningful effect, what
     is treated as exploratory, what caveats are standard. -->
TODO

## Known pitfalls
<!-- Mistakes new people reliably make. Stale intermediate files, deprecated
     scripts that still run, cohorts with special handling, things that look
     fine but are wrong. This section tends to be the most valuable one. -->
TODO
