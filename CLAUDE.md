# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A [Quarto](https://quarto.org/) website for a Political Science World Cup 2026 prediction competition, published to GitHub Pages at `https://haavas.github.io/VM2026/`. The site lists competition rules/posts and is backed by an R analysis pipeline.

## Build and render

```bash
# Render the full site (output goes to docs/)
quarto render

# Preview locally with live reload
quarto preview

# Render a single file
quarto render posts/Regelendring/index.qmd
```

The site output directory is `docs/` (configured in `_quarto.yml`), which is what GitHub Pages serves.

## R analysis

The main analysis is in `R/worldcup_analysis.R`. It requires:

- CRAN packages: `dplyr`, `tidyr`, `readr`, `WDI`, `countrycode`, `glmmTMB`, `DHARMa`
- GitHub packages: `vdeminstitute/vdemdata`, `JaseZiv/worldfootballR`
- A local file `fifa_pretournament.csv` (not tracked) with columns `year`, `iso3`, `fifa`
- External data: `Data/fifa_ranking-2024-06-20.csv` (FIFA rankings snapshot)

The script models World Cup goals (1994–2022) using Poisson/negative-binomial mixed models with FIFA rating, population, and V-Dem democracy index as covariates. It uses a match-level random intercept as a poor man's bivariate Poisson to handle within-match correlation.

## Content structure

- `index.qmd` — homepage listing (auto-lists everything in `posts/`)
- `posts/` — one subdirectory per post, each with its own `index.qmd`
- `posts/_metadata.yml` — applies `freeze: true` to all posts (computational output is frozen; re-rendered only explicitly)
- `about.qmd` — about page

Posts are in Norwegian. New posts go in `posts/<slug>/index.qmd`.

## Freeze behaviour

Because `freeze: true` is set in `posts/_metadata.yml`, Quarto will **not** re-execute R code in posts unless you explicitly run `quarto render --execute-daemon-restart` or delete `.quarto/_freeze/`. This means R code in posts is frozen after first render — edit the `.qmd` source and re-render the specific file to refresh output.
