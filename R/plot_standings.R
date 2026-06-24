# plot_standings.R ─────────────────────────────────────────────────────────────
library(tidyverse)
library(ggplot2)

plot_standings_return <- function(this_match, lag = 1) {
  
  df <- read_delim(here::here("gData", "standings.csv"),
                   delim          = ";",
                   locale         = locale(encoding = "UTF-8"),
                   show_col_types = FALSE) |>
    mutate(full_name = if_else(is.na(full_name) | full_name == "",
                               player, full_name))
  
  played_matches <- sort(unique(df$play_order))
  
  this_play_order <- df |>
    filter(match == this_match) |>
    pull(play_order) |>
    first()
  
  lag_match_idx <- match(this_play_order, played_matches) - lag
  
  lag_match_play_order <- if (!is.na(lag_match_idx) && lag_match_idx >= 1) {
    played_matches[lag_match_idx]
  } else {
    NA_integer_
  }
  
  lag_scores <- if (!is.na(lag_match_play_order)) {
    df |>
      filter(play_order == lag_match_play_order) |>
      select(player, lag_score = cumulative)
  } else {
    tibble(player = unique(df$player), lag_score = 0L)
  }
  
  df |>
    filter(match == this_match) |>
    left_join(lag_scores, by = "player") |>
    mutate(
      lag_score = replace_na(lag_score, 0L),
      diff      = cumulative - lag_score,
      full_name = fct_reorder(full_name, cumulative)
    )
}

plot_standings <- function(this_match,
                           lag     = 1,
                           outfile = "standings.png",
                           width   = 10,
                           height  = 10,
                           dpi     = 150) {
  
  hbar <- plot_standings_return(this_match, lag)
  
  last_stage <- hbar |> pull(stage) |> first()
  lag_label  <- if (lag == 1) "last game" else paste0("last ", lag, " games")
  
  p <- ggplot(hbar, aes(x = full_name, y = cumulative, fill = diff)) +
    geom_col() +
    scale_y_continuous(
      limits = c(min(min(hbar$cumulative), 0), max(hbar$cumulative) * 1.12)
    ) +
    coord_flip() +
    scale_fill_gradient2(
      low      = "red",
      high     = "blue",
      mid      = "grey85",
      midpoint = 0,
      name     = paste0("Pts (", lag_label, ")")
    ) +
    geom_text(aes(label = cumulative), hjust = -0.25, size = 5) +
    ylab("Points") +
    xlab(" ") +
    labs(
      title    = "2026 World Cup \u2014 Current Standings",
      subtitle = paste0("After M", this_match, " \u2014 ", last_stage,
                        "  |  colour = points from ", lag_label)
    ) +
    theme_minimal() +
    theme(
      axis.text  = element_text(size = 14),
      axis.title = element_text(size = 14, face = "bold"),
      plot.title = element_text(face = "bold", size = 16)
    )
  
  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)
  
  invisible(p)
}