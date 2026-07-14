# goals_progress_points.R ──────────────────────────────────────────────────────
library(tidyverse)
library(jsonlite)

# Score each player's predicted cumulative goals against the actual (fasit)
# cumulative goals as of `this_match` (defaults to the latest match with a
# known result).
#
# poeng = 30 * exp(-|gjett - fasit| / lambda), lambda = fasit / 10
# i.e. full 30 points for an exact match, decaying exponentially with the
# absolute error, scaled relative to how many goals have actually been scored.
goals_progress_points <- function(this_match = NULL) {

  raw <- fromJSON(here::here("gData", "cumulative_goals_vs_fasit.json"),
                   simplifyVector = FALSE)

  deltagere <- fromJSON(here::here("gData", "deltagere.json")) |>
    mutate(player = str_remove(file, "\\.xlsx$")) |>
    select(player, full_name)

  match_index <- as.integer(raw$match_index)
  played      <- unlist(raw$fasit$played)

  n_played <- if (is.null(this_match)) {
    max(which(played))
  } else {
    idx <- match(this_match, match_index)
    if (is.na(idx)) stop("this_match (", this_match, ") not found in match_index")
    idx
  }

  fasit_underveis <- as.numeric(raw$fasit$cumulative[[n_played]])

  imap_dfr(raw$players, function(pred, player) {
    gjett_underveis <- as.numeric(pred$cumulative[[n_played]])
    lambda <- fasit_underveis / 10
    poeng <- if (fasit_underveis == 0) {
      if (gjett_underveis == 0) 30 else 0
    } else {
      30 * exp(-abs(gjett_underveis - fasit_underveis) / lambda)
    }
    tibble(player = player, gjett_underveis, fasit_underveis, poeng)
  }) |>
    left_join(deltagere, by = "player") |>
    mutate(
      player = if_else(is.na(full_name) | full_name == "", player, full_name),
      poeng  = round(poeng)
    ) |>
    select(-full_name) |>
    arrange(desc(poeng))
}
