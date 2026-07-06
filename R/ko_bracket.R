# ko_bracket.R
# ------------
# Reads gData/ko_bracket.json and produces a heatmap showing each
# participant's points per knockout stage as a fraction of the maximum
# possible, with correct_team and correct_spot counts as cell labels.
#
# Source this file and call:
#   plot_ko_bracket()                  # display
#   plot_ko_bracket(save = TRUE)       # save to img/ko_bracket.png

library(here)
library(ggplot2)
library(dplyr)
library(tidyr)
library(jsonlite)
library(stringr)

plot_ko_bracket <- function(
    json_path      = here("gData", "ko_bracket.json"),
    deltagere_path = here("gData", "deltagere.json"),
    save           = FALSE,
    out_path       = here("img", "ko_bracket.png"),
    width          = 10,
    height         = 9
) {

  # ---------------------------------------------------------------------------
  # Load
  # ---------------------------------------------------------------------------
  raw <- fromJSON(json_path, simplifyVector = FALSE)

  # Full-name lookup: abbr -> full_name
  # ko_bracket.json keys are abbreviations, so match on abbr field
  name_df <- if (file.exists(deltagere_path)) {
    d <- fromJSON(deltagere_path, simplifyDataFrame = TRUE)
    data.frame(
      abbr      = d$abbr,
      full_name = d$full_name,
      stringsAsFactors = FALSE
    )
  } else {
    data.frame(abbr = character(0), full_name = character(0))
  }

  lookup_name <- function(abbrs) {
    idx <- match(abbrs, name_df$abbr)
    ifelse(is.na(idx), abbrs, name_df$full_name[idx])
  }

  stage_order  <- unlist(raw$meta$stages)
  stage_labels <- unlist(raw$meta$stage_labels)   # named vector: key -> label

  # Medal stage handled separately — exclude from main heatmap
  ko_stages <- stage_order[stage_order != "medals"]

  # ---------------------------------------------------------------------------
  # Build long data frame
  # ---------------------------------------------------------------------------
  rows <- list()
  for (player in names(raw$players)) {
    player_data <- raw$players[[player]]
    for (stage_key in ko_stages) {
      s <- player_data[[stage_key]]
      if (is.null(s)) next
      rows <- c(rows, list(data.frame(
        player       = player,
        stage_key    = stage_key,
        correct_team = as.integer(s$correct_team),
        correct_spot = as.integer(s$correct_spot),
        pts          = as.integer(s$pts),
        max_pts      = as.integer(s$max_pts),
        n_slots      = as.integer(s$n_slots),
        stringsAsFactors = FALSE
      )))
    }
  }

  df <- bind_rows(rows) |>
    mutate(
      full_name   = lookup_name(player),
      pct         = ifelse(max_pts > 0, pts / max_pts, NA_real_),
      stage_label = factor(
        stage_labels[stage_key],
        levels = stage_labels[ko_stages]
      ),
      cell_label  = paste0(correct_team, " / ", n_slots)
    )

  # Order players by total KO points (desc) so best performers are at the top
  player_order <- df |>
    group_by(full_name) |>
    summarise(total = sum(pts, na.rm = TRUE), .groups = "drop") |>
    arrange(desc(total)) |>
    pull(full_name)

  df <- df |>
    mutate(full_name = factor(full_name, levels = rev(player_order)))

  # ---------------------------------------------------------------------------
  # Colour scale: red -> orange -> green, midpoint at 50%
  # ---------------------------------------------------------------------------
  p <- ggplot(df, aes(x = stage_label, y = full_name, fill = pct)) +
    geom_tile(colour = "white", linewidth = 1.2) +
    geom_text(
      aes(label = cell_label),
      size     = 3.2,
      colour   = ifelse(df$pct > 0.6, "white", "grey25"),
      fontface = "bold"
    ) +
    scale_fill_gradient2(
      low      = "#d9534f",
      mid      = "#f0ad4e",
      high     = "#5cb85c",
      midpoint = 0.5,
      limits   = c(0, 1),
      na.value = "grey88",
      name     = "% of max pts",
      labels   = scales::percent_format(accuracy = 1)
    ) +
    scale_x_discrete(position = "top") +
    labs(
      title    = "Knockout stage \u2014 teams predicted per stage",
      subtitle = paste0(
        "Cell label: correct teams / total slots  ",
        "\u2022  colour: points earned as % of stage maximum"
      ),
      x = NULL,
      y = NULL
    ) +
    theme_minimal(base_size = 12) +
    theme(
      plot.title        = element_text(face = "bold", size = 14, hjust = 0),
      plot.subtitle     = element_text(size = 9, colour = "grey40", hjust = 0,
                                       margin = margin(b = 10)),
      axis.text.x       = element_text(face = "bold", size = 10),
      axis.text.y       = element_text(size = 10),
      panel.grid        = element_blank(),
      legend.position   = "right",
      legend.key.height = unit(1.8, "cm"),
      plot.margin       = margin(12, 12, 12, 12)
    )

  if (save) {
    dir.create(dirname(out_path), showWarnings = FALSE, recursive = TRUE)
    ggsave(out_path, plot = p, width = width, height = height, dpi = 150)
    message("Saved \u2192 ", out_path)
  }

  p
}
