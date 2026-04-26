# =============================================================================
# World Cup match analysis: goals as a function of FIFA rating, population,
# and V-Dem Liberal Democracy Index
#
# Sample: World Cup matches 1994-2022 (recommended starting point)
# Outcome: 120-minute score, shootouts excluded
# Models:  Poisson with covariates entered (a) separately for team/opponent
#          and (b) as differences (symmetry constraint).
#          Match-level random intercept handles within-match correlation
#          (poor man's bivariate Poisson).
# =============================================================================

# ---- 0. Packages ------------------------------------------------------------
# install.packages(c("dplyr", "tidyr", "readr", "WDI", "countrycode",
#                    "glmmTMB", "DHARMa", "remotes"))
# remotes::install_github("vdeminstitute/vdemdata")
# remotes::install_github("JaseZiv/worldfootballR")

library(dplyr)
library(tidyr)
library(readr)
library(WDI)
library(countrycode)
library(vdemdata)
library(worldfootballR)
library(glmmTMB)
library(DHARMa)


# ---- 1. World Cup match results --------------------------------------------
# load_match_comp_results() pulls pre-scraped FBref data for the FIFA World Cup
# (all years available, updated ~daily). HomeGoals / AwayGoals are full-time
# INCLUDING extra time but EXCLUDING shootouts -- exactly what we want.
# The Score column carries the raw "1-1 (4-3 pen.)" string if you want to
# verify shootouts; Notes flags ET/penalties.

wc_raw <- load_match_comp_results(comp_name = "FIFA World Cup")

# Spot-check a knockout match or two before trusting the goal columns:
# wc_raw %>% filter(grepl("pen", Score, ignore.case = TRUE)) %>%
#   select(Season_End_Year, Round, Home, Away, HomeGoals, AwayGoals, Score)

matches <- wc_raw %>%
  filter(Season_End_Year >= 1994, Season_End_Year <= 2022) %>%
  mutate(
    # FBref names are like "Germany de" / "China PR cn" -- strip trailing 2-letter code
    home_team = trimws(sub("\\s+[a-z]{2}$", "", Home)),
    # FBref away names are like "de Germany" -- code prefixed
    away_team = trimws(sub("^[a-z]{2}\\s+", "", Away)),
    knockout  = as.integer(!grepl("group", Round, ignore.case = TRUE)),
    host_country = case_when(
      Season_End_Year == 1994 ~ "United States",
      Season_End_Year == 1998 ~ "France",
      Season_End_Year == 2002 ~ "South Korea",   # Japan added below
      Season_End_Year == 2006 ~ "Germany",
      Season_End_Year == 2010 ~ "South Africa",
      Season_End_Year == 2014 ~ "Brazil",
      Season_End_Year == 2018 ~ "Russia",
      Season_End_Year == 2022 ~ "Qatar"
    ),
    host_home = as.integer(home_team == host_country),
    host_home = ifelse(Season_End_Year == 2002 & home_team == "Japan",
                       1L, host_home)
  ) %>%
  rename(year       = Season_End_Year,
         home_goals = HomeGoals,
         away_goals = AwayGoals) %>%
  filter(!is.na(home_goals), !is.na(away_goals)) %>%
  select(year, knockout, host_home,
         home_team, away_team, home_goals, away_goals)

# Sanity check: list unique team names so you can spot any the regex mangled
# sort(unique(c(matches$home_team, matches$away_team)))


# ---- 2. Country code harmonisation -----------------------------------------
# World Cup uses football-federation names (England, not UK; etc.).
# Build a manual lookup for the cases countrycode() misses or gets wrong.

football_to_iso3 <- c(
  # FBref format: code + name or name + code
  "eng England"          = "GBR",
  "sct Scotland"         = "GBR",
  "wls Wales"            = "GBR",
  "England eng"          = "GBR",
  "Scotland sct"         = "GBR",
  "Wales wls"            = "GBR",
  # FIFA ranking CSV format: plain name
  "England"              = "GBR",
  "Scotland"             = "GBR",
  "Wales"                = "GBR",
  "Northern Ireland"     = "GBR",
  "South Korea"          = "KOR",
  "Korea Republic"       = "KOR",
  "Ivory Coast"          = "CIV",
  "Cote d'Ivoire"        = "CIV",
  "Iran"                 = "IRN",
  "IR Iran"              = "IRN",
  "Russia"               = "RUS",
  "Serbia"               = "SRB",
  "Serbia & Montenegro"  = "SRB",
  "Serbia and Montenegro" = "SRB",
  "Yugoslavia"           = "SRB",
  "Czech Republic"       = "CZE",
  "United States"        = "USA",
  "USA"                  = "USA"
)

to_iso3 <- function(x) {
  countrycode(x, origin = "country.name", destination = "iso3c",
              custom_match = football_to_iso3, warn = FALSE)
}

matches <- matches %>%
  mutate(home_iso3 = to_iso3(home_team),
         away_iso3 = to_iso3(away_team))

stopifnot(!any(is.na(matches$home_iso3)), !any(is.na(matches$away_iso3)))


# ---- 3. Population (World Bank) --------------------------------------------
pop <- WDI(country = "all", indicator = "SP.POP.TOTL",
           start = 1990, end = 2022) %>%
  rename(pop = SP.POP.TOTL) %>%
  mutate(iso3 = countrycode(iso2c, "iso2c", "iso3c", warn = FALSE)) %>%
  select(iso3, year, pop) %>%
  filter(!is.na(iso3), !is.na(pop))


# ---- 4. V-Dem Liberal Democracy Index --------------------------------------
vdem_sub <- vdem %>%
  transmute(iso3 = country_text_id, year, vdem = v2x_libdem) %>%
  filter(!is.na(vdem))


# ---- 5. FIFA ratings -------------------------------------------------------
# Build pre-tournament snapshots from the raw monthly ranking file.
# We pick the last published ranking before each tournament's first match.
#
# Tournament start dates → last available ranking date used:
#   1994-06-17  →  1994-06-14
#   1998-06-10  →  1998-05-20
#   2002-05-31  →  2002-05-15
#   2006-06-09  →  2006-05-17
#   2010-06-11  →  2010-05-26
#   2014-06-12  →  2014-06-05
#   2018-06-14  →  2018-06-07
#   2022-11-20  →  2022-10-06

pretournament_dates <- tibble(
  year      = c(1994L, 1998L, 2002L, 2006L, 2010L, 2014L, 2018L, 2022L),
  rank_date = c("1994-06-14", "1998-05-20", "2002-05-15", "2006-05-17",
                "2010-05-26", "2014-06-05", "2018-06-07", "2022-10-06")
)

fifa <- read_csv("Data/fifa_ranking-2024-06-20.csv",
                 col_types = cols(rank_date = col_character())) %>%
  inner_join(pretournament_dates, by = "rank_date") %>%
  mutate(
    iso3 = to_iso3(country_full),
    fifa = total_points
  ) %>%
  filter(!is.na(iso3)) %>%
  select(year, iso3, fifa)


# ---- 6. Merge covariates onto matches --------------------------------------
attach_covars <- function(df, side) {
  # side is "home" or "away"
  iso_col <- paste0(side, "_iso3")
  df %>%
    left_join(pop,      by = c(setNames("iso3", iso_col), "year")) %>%
    rename(!!paste0("pop_",  side) := pop) %>%
    left_join(vdem_sub, by = c(setNames("iso3", iso_col), "year")) %>%
    rename(!!paste0("vdem_", side) := vdem) %>%
    left_join(fifa,     by = c(setNames("iso3", iso_col), "year")) %>%
    rename(!!paste0("fifa_", side) := fifa)
}

matches <- matches %>%
  attach_covars("home") %>%
  attach_covars("away")

# Inspect missingness before proceeding
matches %>% summarise(across(starts_with(c("pop_", "vdem_", "fifa_")),
                             ~ sum(is.na(.))))

matches <- matches %>%
  filter(if_all(starts_with(c("pop_", "vdem_", "fifa_")), ~ !is.na(.)))


# ---- 7. Reshape to long format for modelling -------------------------------
long <- matches %>%
  mutate(match_id = row_number()) %>%
  pivot_longer(
    cols      = c(home_goals, away_goals),
    names_to  = "side",
    values_to = "goals"
  ) %>%
  mutate(
    is_home     = as.integer(side == "home_goals"),
    fifa_team   = ifelse(is_home == 1, fifa_home,    fifa_away),
    fifa_opp    = ifelse(is_home == 1, fifa_away,    fifa_home),
    logpop_team = ifelse(is_home == 1, log(pop_home), log(pop_away)),
    logpop_opp  = ifelse(is_home == 1, log(pop_away), log(pop_home)),
    vdem_team   = ifelse(is_home == 1, vdem_home,    vdem_away),
    vdem_opp    = ifelse(is_home == 1, vdem_away,    vdem_home),
    is_host     = ifelse(is_home == 1, host_home, 0L),
    fifa_d      = fifa_team   - fifa_opp,
    logpop_d    = logpop_team - logpop_opp,
    vdem_d      = vdem_team   - vdem_opp
  )


# ---- 8. Models -------------------------------------------------------------

## 8a. Unrestricted: separate team and opponent effects
mod_full <- glmmTMB(
  goals ~ fifa_team + fifa_opp +
    logpop_team + logpop_opp +
    vdem_team + vdem_opp +
    is_host + knockout +
    (1 | match_id),
  family = poisson,
  data   = long
)

## 8b. Restricted: symmetry imposed (single coef per covariate, on the
##     team-minus-opponent difference)
mod_diff <- glmmTMB(
  goals ~ fifa_d + logpop_d + vdem_d +
    is_host + knockout +
    (1 | match_id),
  family = poisson,
  data   = long
)

## Likelihood-ratio test of the symmetry constraint
anova(mod_diff, mod_full)

summary(mod_full)
summary(mod_diff)


# ---- 9. Diagnostics --------------------------------------------------------

## Overdispersion check
sim_full <- simulateResiduals(mod_full)
plot(sim_full)
testDispersion(sim_full)

## Predicted vs. observed goal distribution
long$pred <- predict(mod_full, type = "response")
table_obs <- table(long$goals)
table_exp <- sapply(0:max(long$goals),
                    function(k) sum(dpois(k, long$pred)))
cbind(observed = as.numeric(table_obs),
      expected = round(table_exp[seq_along(table_obs)], 1))

## Sensitivity: refit with negative binomial in case of overdispersion
mod_nb <- glmmTMB(
  goals ~ fifa_team + fifa_opp + logpop_team + logpop_opp +
    vdem_team + vdem_opp + is_host + knockout +
    (1 | match_id),
  family = nbinom2,
  data   = long
)
AIC(mod_full, mod_nb)


# ---- 10. Optional: knockout interactions -----------------------------------
# Knockout matches may compress effects (weaker teams play more defensively).
mod_int <- glmmTMB(
  goals ~ (fifa_d + logpop_d + vdem_d) * knockout +
    is_host + (1 | match_id),
  family = poisson, data = long
)
summary(mod_int)