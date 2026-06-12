# group_stage_scatter.R
# ----------------------
# For every group stage match, plots:
#   X axis  = away goals predicted
#   Y axis  = home goals predicted
#   Size    = number of participants who predicted that exact scoreline
#   Colour  = group stage points that scoreline would yield IF it were correct
#             (25 pts for correct outcome − Δh² − Δa² goal penalties)
#
# Colour reference: fasit.json (written by score.py) when available,
# otherwise falls back to the modal (most-predicted) scoreline per match.
#
# Usage:
#   source("R/group_stage_scatter.R")
#   plot_match(14)           # single match
#   plot_match(14, save = TRUE)  # also writes gData/match_014.png

library(tidyverse)
library(jsonlite)
library(here)

# ---------------------------------------------------------------------------
# Scoring constant
# ---------------------------------------------------------------------------
CORRECT_OUTCOME_PTS <- 25L

# ---------------------------------------------------------------------------
# Load predictions (once at source time)
# ---------------------------------------------------------------------------
preds <- fromJSON(here("gData", "predictions.json"),
                  simplifyVector = FALSE)

gs_raw <- map_dfr(preds$players, function(player) {
  gs <- player$group_stage
  if (is.null(gs) || length(gs) == 0) return(tibble())
  map_dfr(gs, function(m) {
    h <- suppressWarnings(as.integer(m$home_goals))
    a <- suppressWarnings(as.integer(m$away_goals))
    if (is.na(h) || is.na(a)) return(NULL)
    tibble(
      match  = as.integer(m$match_id),
      home   = as.character(m$home),
      away   = as.character(m$away),
      home_g = h,
      away_g = a
    )
  })
})

# ---------------------------------------------------------------------------
# Load fasit (once at source time)
# ---------------------------------------------------------------------------
fasit_path <- here("gData", "fasit.json")

if (file.exists(fasit_path)) {
  fasit      <- fromJSON(fasit_path, simplifyVector = FALSE)
  ref_scores <- map_dfr(fasit$group_stage, ~ tibble(
    match = as.integer(.x$match %||% .x$match_id),
    ref_h = as.integer(.x$home_goals),
    ref_a = as.integer(.x$away_goals)
  ))
  message("Using fasit.json as reference.")
} else {
  message("fasit.json not found — falling back to modal prediction as reference.")
  ref_scores <- gs_raw %>%
    count(match, home_g, away_g) %>%
    group_by(match) %>%
    slice_max(n, n = 1, with_ties = FALSE) %>%
    ungroup() %>%
    rename(ref_h = home_g, ref_a = away_g) %>%
    select(match, ref_h, ref_a)
}

# ---------------------------------------------------------------------------
# Build full plot_df (once at source time)
# ---------------------------------------------------------------------------
plot_df <- gs_raw %>%
  count(match, home, away, home_g, away_g, name = "n_predictors") %>%
  left_join(ref_scores, by = "match") %>%
  mutate(
    outcome_ok  = sign(home_g - away_g) == sign(ref_h - ref_a),
    points      = if_else(outcome_ok, CORRECT_OUTCOME_PTS, 0L) -
                  (home_g - ref_h)^2L -
                  (away_g - ref_a)^2L,
    match_label = paste0("M", match, ": ", home, " vs ", away)
  )

pts_label <- if (file.exists(fasit_path)) "Points" else "Points\n(vs modal)"
ref_label <- if (file.exists(fasit_path)) "actual result" else "modal prediction"

# ---------------------------------------------------------------------------
# plot_match() — main function
# ---------------------------------------------------------------------------
plot_match <- function(match_no, save = FALSE) {

  df <- filter(plot_df, match == match_no)

  if (nrow(df) == 0) {
    stop("Match ", match_no, " not found. ",
         "Valid group stage matches: ",
         paste(sort(unique(plot_df$match)), collapse = ", "))
  }

  match_title <- unique(df$match_label)
  ref_row     <- filter(ref_scores, match == match_no)

  max_g   <- max(c(df$home_g, df$away_g), na.rm = TRUE)
  g_breaks <- 0:max(max_g, 3L)

  p <- ggplot(df, aes(x = away_g, y = home_g)) +
    # Draw diagonal
    geom_abline(slope = 1, intercept = 0,
                colour = "grey75", linewidth = 0.4, linetype = "dashed") +
    # Actual result marker (if fasit available)
    {
      if (nrow(ref_row) > 0 && file.exists(fasit_path))
        geom_point(data = ref_row,
                   aes(x = ref_a, y = ref_h),
                   shape = 13, size = 7, colour = "black", stroke = 1.2)
    } +
    # Prediction dots
    geom_point(
      aes(size = n_predictors, colour = points),
      alpha = 0.88
    ) +
    # Count labels inside dots
    geom_text(
      data = filter(df, n_predictors > 1),
      aes(label = n_predictors),
      colour = "white", size = 3.2, fontface = "bold"
    ) +
    scale_x_continuous(breaks = g_breaks, expand = expansion(add = 0.7)) +
    scale_y_continuous(breaks = g_breaks, expand = expansion(add = 0.7)) +
    scale_size_area(
      max_size = 16,
      guide    = "none"
    ) +
    scale_colour_gradient2(
      low      = "red",
      high     = "blue",
      mid      = "grey85",
      midpoint = 0,
      name     = pts_label
    ) +
    labs(
      title    = match_title,
      subtitle = paste0(
        "Dot size = no. of participants predicting that scoreline.  ",
        "Colour = points vs ", ref_label, ".",
        if (nrow(ref_row) > 0 && file.exists(fasit_path))
          paste0("  [X] = actual result (", ref_row$ref_h, "-", ref_row$ref_a, ")")
        else ""
      ),
      x       = "Away goals",
      y       = "Home goals",
      caption = paste("Generated", Sys.Date())
    ) +
    theme_minimal(base_size = 12) +
    theme(
      plot.title        = element_text(size = 15, face = "bold"),
      plot.subtitle     = element_text(size = 8.5, colour = "grey45",
                                       margin = margin(b = 8)),
      plot.caption      = element_text(size = 7.5, colour = "grey55"),
      panel.grid.minor  = element_blank(),
      panel.grid.major  = element_line(colour = "grey90"),
      legend.position   = "right",
      legend.key.height = unit(0.9, "cm")
    )

  if (save) {
    out_png <- here("gData", sprintf("match_%03d.png", match_no))
    ggsave(out_png, p, width = 7, height = 6, dpi = 150)
    #message("Wrote -> ", out_png)
  }

  p
}
