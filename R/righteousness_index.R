# righteousness_index.R ────────────────────────────────────────────────────────
# An "Index of Righteousness" for the 2026 World Cup competition.
#
# Idea:  Each country is scored on three V-Dem dimensions (latest year, 2025) ──
#          democracy    = v2x_polyarchy   (electoral democracy index)
#          human_rights = v2x_clphy       (physical violence index: freedom
#                                           from political killing & torture)
#          corruption   = 1 - v2x_corr    ("cleanness"; v2x_corr is higher =
#                                           MORE corrupt, so we invert it)
#        All three are on 0..1 and oriented so that higher = more righteous.
#        A country's righteousness is their equal-weight mean.
#
#        Each *contestant* is then scored by how far they pushed righteous
#        countries in their knockout bracket. Every team a contestant advances
#        earns that country's righteousness, weighted by the deepest round the
#        contestant sent them to:
#          r32 = 1, r16 = 2, qf = 3, sf = 4, final = 5, world champion = 6.
#        A contestant's score is the weight-weighted mean righteousness of their
#        bracket (0..1) — i.e. the average righteousness of the teams they
#        believed in, counting deep runs more.
#
# Notes / data inclusion:
#   * Curaçao (CUW) is not a sovereign state and is absent from V-Dem; it keeps
#     an NA righteousness and is simply dropped from any contestant's weighted
#     mean (denominator excludes it). It is retained in the country table.
#   * England and Scotland are both mapped to the United Kingdom (GBR) in V-Dem;
#     they therefore share the UK's righteousness score.
#
# Usage:
#   source(here::here("R", "righteousness_index.R"))
#   righteous_countries          # country-level table (raw + derived)
#   righteous_standings          # contestant ranking
#   plot_righteousness()         # horizontal bar chart -> righteousness.png
#   plot_country_righteousness() # country chart       -> righteousness_countries.png
# ──────────────────────────────────────────────────────────────────────────────

library(tidyverse)
library(jsonlite)
library(here)

# ── 1. Country righteousness from V-Dem (latest year) ───────────────────────────
.vdem_latest <- vdemdata::vdem |>
  filter(year == max(year)) |>
  transmute(
    vdem_country = country_name,
    iso3         = country_text_id,
    year,
    v2x_polyarchy,            # democracy           (raw, kept)
    v2x_clphy,                # human rights        (raw, kept)
    v2x_corr,                 # corruption          (raw, kept; higher = worse)
    democracy    = v2x_polyarchy,
    human_rights = v2x_clphy,
    corr_clean   = 1 - v2x_corr,
    righteousness_vdem = (v2x_polyarchy + v2x_clphy + (1 - v2x_corr)) / 3
  )

# ── Editorial adjustment: the "17. mai correction" (declared partiality) ─────────
# This is a Norwegian tournament, and the honest V-Dem index has the audacity to
# rank Sweden first. In the interest of full disclosure — and in open, deliberate
# violation of measurement validity — we dock Sweden by a fixed, clearly visible
# penalty. The true V-Dem score is preserved as `righteousness_vdem`; the adjusted
# `righteousness` is what the index reports. Set RIVALRY_PENALTY to numeric(0) to
# recover the honest, unpatriotic ranking.
RIVALRY_PENALTY <- c(SWE = 0.68)   # keyed by ISO-3; Sweden falls from 1st to near-last
NORWAY_BONUS    <- c(NOR = 0.05)   # keyed by ISO-3; a gratuitous patriotic uplift (Norway is already 1st)

# ── 2. Map the 48 World Cup teams to V-Dem ISO-3 codes ──────────────────────────
# Explicit, documented crosswalk (countrycode is not a dependency here).
team_iso <- tribble(
  ~team,                     ~iso3,
  "Algeria",                 "DZA",
  "Argentina",               "ARG",
  "Australia",               "AUS",
  "Austria",                 "AUT",
  "Belgium",                 "BEL",
  "Bosnia and Herzegovina",  "BIH",
  "Brazil",                  "BRA",
  "Canada",                  "CAN",
  "Cape Verde",              "CPV",
  "Colombia",                "COL",
  "Croatia",                 "HRV",
  "Curaçao",                 "CUW",   # not in V-Dem -> NA righteousness
  "Czech Republic",          "CZE",
  "DR Congo",                "COD",
  "Ecuador",                 "ECU",
  "Egypt",                   "EGY",
  "England",                 "GBR",   # UK constituent -> shares GBR score
  "France",                  "FRA",
  "Germany",                 "DEU",
  "Ghana",                   "GHA",
  "Haiti",                   "HTI",
  "Iran",                    "IRN",
  "Iraq",                    "IRQ",
  "Ivory Coast",             "CIV",
  "Japan",                   "JPN",
  "Jordan",                  "JOR",
  "Korea Republic",          "KOR",
  "Mexico",                  "MEX",
  "Morocco",                 "MAR",
  "Netherlands",             "NLD",
  "New Zealand",             "NZL",
  "Norway",                  "NOR",
  "Panama",                  "PAN",
  "Paraguay",                "PRY",
  "Portugal",                "PRT",
  "Qatar",                   "QAT",
  "Saudi Arabia",            "SAU",
  "Scotland",                "GBR",   # UK constituent -> shares GBR score
  "Senegal",                 "SEN",
  "South Africa",            "ZAF",
  "Spain",                   "ESP",
  "Sweden",                  "SWE",
  "Switzerland",             "CHE",
  "Tunisia",                 "TUN",
  "Turkey",                  "TUR",
  "United States",           "USA",
  "Uruguay",                 "URY",
  "Uzbekistan",              "UZB"
)

righteous_countries <- team_iso |>
  left_join(.vdem_latest, by = "iso3") |>
  mutate(
    # signed: positive = bonus, negative = penalty
    editorial_adjustment = coalesce(unname(NORWAY_BONUS[iso3]), 0) -
                           coalesce(unname(RIVALRY_PENALTY[iso3]), 0),
    righteousness        = righteousness_vdem + editorial_adjustment
  ) |>
  arrange(desc(righteousness))

# team -> righteousness lookup (named vector) for the contestant scoring
.team_score <- righteous_countries |>
  select(team, righteousness) |>
  deframe()

# ── 3. Contestant brackets -> depth weights ─────────────────────────────────────
LEVEL_WEIGHTS <- c(r32 = 1, r16 = 2, qf = 3, sf = 4, final = 5)
CHAMPION_WEIGHT <- 6

preds <- fromJSON(here("gData", "predictions.json"), simplifyVector = FALSE)

# Teams that appear in a given knockout level (both home and away sides).
.teams_at_level <- function(ko, lvl) {
  node <- ko[[lvl]]
  if (is.null(node) || length(node) == 0) return(character(0))
  if (lvl == "final") return(c(node$home, node$away))   # single match (dict)
  unlist(lapply(node, function(m) c(m$home, m$away)))   # list of matches
}

# For one player: tibble(team, weight) with the *deepest* round reached,
# then the world champion bumped to weight 6.
.player_team_levels <- function(pl) {
  ko <- pl$knockout
  rows <- map_dfr(names(LEVEL_WEIGHTS), function(lvl) {
    tibble(team = .teams_at_level(ko, lvl), weight = LEVEL_WEIGHTS[[lvl]])
  })
  champ <- pl$world_champion
  rows |>
    group_by(team) |>
    summarise(weight = max(weight), .groups = "drop") |>
    bind_rows(tibble(team = champ, weight = CHAMPION_WEIGHT)) |>
    group_by(team) |>
    summarise(weight = max(weight), .groups = "drop")    # champion override
}

# Weight-weighted mean righteousness for one player (NA teams excluded).
.player_score <- function(pl) {
  tl <- .player_team_levels(pl)
  tl <- tl |> mutate(righteousness = .team_score[team])
  ok <- tl |> filter(!is.na(righteousness))
  tibble(
    righteousness   = sum(ok$weight * ok$righteousness) / sum(ok$weight),
    champion        = pl$world_champion,
    champion_score  = unname(.team_score[pl$world_champion]),
    n_teams_scored  = nrow(ok),
    n_teams_missing = nrow(tl) - nrow(ok)
  )
}

# ── 4. Build the contestant standings ───────────────────────────────────────────
# Contestant-level editorial adjustment, keyed by player id (positive = penalty).
# "overskudd_paa_timeregnskapet" — a personal deduction levied on Øyvind Stiansen
# in recognition of his surplus on the hour-accounting. Declared, not hidden.
overskudd_paa_timeregnskapet <- c("World_cup_2026_stiansen" = 0.10)

# "theorist_tax" — a levy on the political theorists, set at half the Stiansen rate.
theorist_tax_rate <- overskudd_paa_timeregnskapet[["World_cup_2026_stiansen"]] / 2
theorist_tax <- c(
  "Sandven_World_cup_2026"  = theorist_tax_rate,   # Hallvard Hodne Sandven
  "World_cup_2026_ØB"       = theorist_tax_rate,   # Øivind Bratberg
  "World_cup_2026 (Kuyper)" = theorist_tax_rate    # Jonathan Kuyper
)

# "swede_surtax" — the Sweden penalty, amplified at the contestant level for the
# Swedish nationals among us. Keyed by player id.
SWEDE_SURTAX_RATE <- 0.15
swede_surtax <- c(
  "World_cup_2026_Daniel_Naurin" = SWEDE_SURTAX_RATE,   # Daniel Naurin
  "World_cup_2026_gabriel"       = SWEDE_SURTAX_RATE    # Gabriel Lönn
)

# "taking_it_too_seriously_tax" — scales with time spent on the qualitative survey:
# the longer you deliberated, the more righteousness you forfeit. The rate is per
# minute and the dock is capped, so the 8.5-hour idle-tab outlier cannot run the
# index into the ground. Set the rate to 0 to switch it off.
# NB: this rate is not innocent. It was tuned by uniroot() to the exact value at
# which the points-vs-righteousness correlation reaches p = 0.050 — i.e. the index
# is openly p-hacked to significance. The number's false precision is the giveaway.
TAKING_IT_TOO_SERIOUSLY_RATE <- 0.004814   # righteousness docked per minute (tuned to p = 0.05)
TAKING_IT_TOO_SERIOUSLY_CAP  <- 0.15       # maximum dock

# "abstention_tax" — the symmetric counterpart: contestants with no qualitative
# submission escaped the seriousness tax on a technicality. Non-participation is
# itself suspect, so it is taxed at the seriousness cap. (This is what finally
# reaches Øyvind Colbjørnsen, the lone abstainer.)
ABSTENTION_TAX <- TAKING_IT_TOO_SERIOUSLY_CAP

.answer_times <- fromJSON(here("gData", "qualitative.json"))$responses |>
  as_tibble() |>
  transmute(player     = sub("\\.xlsx$", "", excel_file),
            answer_min = answer_time_ms / 60000)

# Readable names from the competition standings file.
.full_names <- read_delim(here("gData", "standings.csv"), delim = ";",
                          locale = locale(encoding = "UTF-8"),
                          show_col_types = FALSE) |>
  distinct(player, full_name) |>
  mutate(full_name = if_else(is.na(full_name) | full_name == "", player, full_name))

righteous_standings <- imap_dfr(preds$players, function(pl, key) {
  .player_score(pl) |> mutate(player = key, .before = 1)
}) |>
  left_join(.full_names, by = "player") |>
  mutate(full_name = coalesce(full_name, player)) |>
  left_join(.answer_times, by = "player") |>
  rename(righteousness_bracket = righteousness) |>
  mutate(
    timeregnskap_penalty = coalesce(unname(overskudd_paa_timeregnskapet[player]), 0),
    theorist_tax_penalty = coalesce(unname(theorist_tax[player]), 0),
    seriousness_penalty  = pmin(coalesce(answer_min, 0) * TAKING_IT_TOO_SERIOUSLY_RATE,
                                TAKING_IT_TOO_SERIOUSLY_CAP),
    abstention_penalty   = if_else(is.na(answer_min), ABSTENTION_TAX, 0),
    swede_surtax_penalty = coalesce(unname(swede_surtax[player]), 0),
    righteousness        = righteousness_bracket - timeregnskap_penalty -
                           theorist_tax_penalty - seriousness_penalty -
                           abstention_penalty - swede_surtax_penalty
  ) |>
  arrange(desc(righteousness)) |>
  mutate(righteous_rank = row_number(), .before = 1)

# ── 5. Plots ────────────────────────────────────────────────────────────────────
plot_righteousness <- function(outfile = "righteousness.png",
                               width = 10, height = 11, dpi = 150) {
  d <- righteous_standings |>
    mutate(full_name = fct_reorder(full_name, righteousness))

  p <- ggplot(d, aes(x = full_name, y = righteousness, fill = righteousness)) +
    geom_col() +
    coord_flip() +
    scale_fill_gradient(low = "grey80", high = "darkgreen", guide = "none") +
    scale_y_continuous(limits = c(0, max(d$righteousness) * 1.10)) +
    geom_text(aes(label = sprintf("%.3f", righteousness)),
              hjust = -0.2, size = 4) +
    labs(
      title    = "2026 World Cup — Index of Righteousness",
      subtitle = "Weight-weighted mean V-Dem righteousness of each bracket (deeper runs count more)",
      x = " ", y = "Righteousness (0–1)"
    ) +
    theme_minimal() +
    theme(
      axis.text  = element_text(size = 13),
      axis.title = element_text(size = 13, face = "bold"),
      plot.title = element_text(face = "bold", size = 16)
    )

  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)
  invisible(p)
}

plot_country_righteousness <- function(outfile = "righteousness_countries.png",
                                       width = 10, height = 12, dpi = 150) {
  d <- righteous_countries |>
    filter(!is.na(righteousness)) |>
    distinct(iso3, .keep_all = TRUE) |>          # collapse England/Scotland -> UK
    mutate(label = fct_reorder(vdem_country, righteousness))

  p <- ggplot(d, aes(x = label, y = righteousness, fill = righteousness)) +
    geom_col() +
    coord_flip() +
    scale_fill_gradient(low = "grey80", high = "darkgreen", guide = "none") +
    geom_text(aes(label = sprintf("%.2f", righteousness)),
              hjust = -0.2, size = 3.5) +
    scale_y_continuous(limits = c(0, 1.15)) +
    labs(
      title    = "World Cup 2026 nations, ranked by righteousness",
      subtitle = "Mean of V-Dem democracy, human rights and cleanness (2025), after declared 17. mai adjustments (Sweden down, Norway up)",
      x = " ", y = "Righteousness (0–1)"
    ) +
    theme_minimal() +
    theme(plot.title = element_text(face = "bold", size = 15))

  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)
  invisible(p)
}

plot_points_vs_righteousness <- function(outfile = "points_vs_righteousness.png",
                                         width = 9, height = 7, dpi = 150) {
  pts <- read_delim(here("gData", "standings.csv"), delim = ";",
                    locale = locale(encoding = "UTF-8"),
                    show_col_types = FALSE) |>
    filter(match == max(match)) |>
    select(player, points = cumulative)

  d <- righteous_standings |> left_join(pts, by = "player")
  r <- cor(d$points, d$righteousness)
  p_val <- cor.test(d$points, d$righteousness)$p.value

  p <- ggplot(d, aes(x = righteousness, y = points)) +
    geom_smooth(method = "lm", formula = y ~ x, se = TRUE,
                colour = "grey40", fill = "grey85", linewidth = 0.6) +
    geom_point(aes(colour = points), size = 3) +
    ggrepel::geom_text_repel(aes(label = full_name), size = 3,
                             max.overlaps = 20, seed = 1) +
    scale_colour_gradient(low = "red", high = "blue", guide = "none") +
    labs(
      title    = "Competition points vs. righteousness",
      subtitle = sprintf("Pearson r = %.2f (p = %.3f) — the more points you score, the less righteous you are",
                         r, p_val),
      x = "Righteousness of bracket (0–1)",
      y = "Competition points (after M12)"
    ) +
    theme_minimal(base_size = 12) +
    theme(plot.title = element_text(face = "bold", size = 15))

  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)
  invisible(p)
}

# ── 6. Persist tables (raw + derived; identifiers kept for merging) ─────────────
# Not run on source() — call explicitly to (re)write the CSVs, so that rendering
# the post never triggers disk writes:
#   Rscript -e 'source(here::here("R","righteousness_index.R")); save_righteousness_outputs()'
save_righteousness_outputs <- function() {
  write_csv(righteous_countries, here("gData", "righteousness_countries.csv"))
  write_csv(righteous_standings, here("gData", "righteousness_standings.csv"))
  invisible(NULL)
}
