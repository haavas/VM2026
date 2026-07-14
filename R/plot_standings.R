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

plot_standings_stacked <- function(this_match,
                                   outfile = "standings_stacked.png",
                                   width   = 10,
                                   height  = 10,
                                   dpi     = 150) {
  # Base data: cumulative totals at this_match, player order by total
  hbar <- plot_standings_return(this_match, lag = 1)

  # Category totals from scores.json (static per player, not per match)
  scores_raw <- jsonlite::fromJSON(
    here::here("gData", "scores.json"),
    simplifyVector = TRUE
  )

  category_pts <- purrr::imap_dfr(scores_raw$players, function(s, player) {
    tibble(
      player    = player,
      qs_pts    = s$questions$points   %||% 0L,
      group_pts = s$group_stage$points %||% 0L,
      ko_pts    = (s$knockout$points   %||% 0L) +
                  (s$medals$points     %||% 0L)
    )
  })

  # Join and reshape to long format for stacking
  df_long <- hbar |>
    select(full_name, player, cumulative) |>
    left_join(category_pts, by = "player") |>
    pivot_longer(
      cols      = c(qs_pts, group_pts, ko_pts),
      names_to  = "category",
      values_to = "pts"
    ) |>
    mutate(
      category = factor(category,
                        levels = c("qs_pts", "group_pts", "ko_pts"),
                        labels = c("Qualitative", "Group stage", "Knockout"))
    )

  last_stage <- hbar |> pull(stage) |> first()

  p <- ggplot(df_long,
              aes(x = full_name, y = pts, fill = category)) +
    geom_col() +
    geom_text(
      data = hbar,
      aes(x = full_name, y = cumulative, label = cumulative, fill = NULL),
      hjust  = -0.25,
      size   = 5
    ) +
    scale_y_continuous(
      limits = c(0, max(hbar$cumulative) * 1.12)
    ) +
    scale_fill_manual(
      values = c(
        "Qualitative"  = "#5b9bd5",
        "Group stage"  = "#70ad47",
        "Knockout"     = "#ed7d31"
      ),
      name = "Category"
    ) +
    coord_flip() +
    ylab("Points") +
    xlab(" ") +
    labs(
      title    = "2026 World Cup \u2014 Current Standings",
      subtitle = paste0("After M", this_match, " \u2014 ", last_stage,
                        "  |  breakdown by scoring category")
    ) +
    theme_minimal() +
    theme(
      axis.text  = element_text(size = 14),
      axis.title = element_text(size = 14, face = "bold"),
      plot.title = element_text(face = "bold", size = 16),
      legend.position = "bottom"
    )

  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)

  invisible(p)
}

# %||% operator (base R has it in 4.4+, define for safety)
`%||%` <- function(x, y) if (!is.null(x)) x else y

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

# Team colours for the predicted-winner fill. France/Portugal use hex codes
# since "French blue" / "Burgundy" aren't base R colour names.
winner_colours <- c(
  England   = "white",
  Brazil    = "yellow",
  Argentina = "skyblue",
  France    = "#0055A4",
  Germany   = "black",
  Mexico    = "darkgreen",
  Portugal  = "#800020",
  Spain     = "red",
  Unknown   = "grey80"
)

plot_standings_by_winner <- function(this_match,
                                     lag     = 1,
                                     outfile = "standings_by_winner.png",
                                     width   = 10,
                                     height  = 10,
                                     dpi     = 150) {

  hbar <- plot_standings_return(this_match, lag)

  podium <- read_csv(here::here("gData", "podium_table.csv"), show_col_types = FALSE) |>
    select(full_name = Name, winner = Gold)

  hbar <- hbar |>
    left_join(podium, by = "full_name") |>
    mutate(
      winner    = replace_na(winner, "Unknown"),
      full_name = fct_reorder(full_name, cumulative)
    )

  last_stage <- hbar |> pull(stage) |> first()

  p <- ggplot(hbar, aes(x = full_name, y = cumulative, fill = winner)) +
    geom_col(colour = "grey30", linewidth = 0.3) +
    scale_y_continuous(
      limits = c(0, max(hbar$cumulative) * 1.12)
    ) +
    coord_flip() +
    scale_fill_manual(values = winner_colours, name = "Predicted winner") +
    geom_text(aes(label = cumulative), hjust = -0.25, size = 5) +
    ylab("Points") +
    xlab(" ") +
    labs(
      title    = "2026 World Cup — Current Standings",
      subtitle = paste0("After M", this_match, " — ", last_stage,
                        "  |  colour = predicted tournament winner")
    ) +
    theme_minimal() +
    theme(
      axis.text  = element_text(size = 14),
      axis.title = element_text(size = 14, face = "bold"),
      plot.title = element_text(face = "bold", size = 16),
      legend.position = "right"
    )

  ggsave(outfile, plot = p, width = width, height = height, dpi = dpi)

  invisible(p)
}