library(tidyverse)
library(jsonlite)

project_root <- function(...) {
  # Walk up from this script's location to find the .git root
  start <- dirname(rstudioapi::getSourceEditorContext()$path)
  path  <- start
  while (!file.exists(file.path(path, ".git"))) {
    parent <- dirname(path)
    if (parent == path) stop("Could not find project root (.git)")
    path <- parent
  }
  file.path(path, ...)
}

# ── Load data ────────────────────────────────────────────────────────────────
raw <- fromJSON(project_root("gData", "cumulative_goals.json"), simplifyVector = FALSE)

# Pivot to long format: one row per (player, match)
df <- imap_dfr(raw$players, function(pred, player) {
  tibble(
    player     = player,
    match      = as.integer(raw$match_index),
    label      = as.character(raw$match_labels),
    cumulative = as.integer(pred$cumulative)
  )
})

# Stage boundaries for background shading + x-axis breaks
stage_starts <- df |>
  mutate(stage = str_extract(label, "[A-Za-z0-9]+$")) |>
  group_by(stage) |>
  summarise(start = min(match), end = max(match), .groups = "drop") |>
  mutate(stage = factor(stage, levels = c("GS", "R32", "R16", "QF", "SF", "3rd", "F")))

stage_colors <- c(
  GS  = "#f0f4f8",
  R32 = "#dde8f0",
  R16 = "#c8dce9",
  QF  = "#a8c8de",
  SF  = "#7baecf",
  `3rd` = "#5592bc",
  F   = "#2e76a8"
)

# X-axis: one tick per stage transition + final match
x_breaks <- c(stage_starts$start, 104)
x_labels <- c(
  paste0(stage_starts$stage, "\n(M", stage_starts$start, ")"),
  "M104\nFinal"
)

# ── Plot ─────────────────────────────────────────────────────────────────────
p <- ggplot(df, aes(x = match, y = cumulative, colour = player)) +
  
  # Stage shading
  geom_rect(
    data = stage_starts,
    aes(xmin = start - 0.5, xmax = end + 0.5, ymin = -Inf, ymax = Inf,
        fill = stage),
    inherit.aes = FALSE, alpha = 0.35
  ) +
  scale_fill_manual(values = stage_colors, name = "Stage") +
  
  # Lines + points at stage boundaries
  geom_line(linewidth = 0.9) +
  geom_point(
    data = df |> filter(match %in% stage_starts$end),
    size = 2
  ) +
  
  scale_colour_brewer(palette = "Set1", name = "Player") +
  scale_x_continuous(breaks = x_breaks, labels = x_labels, expand = c(0.01, 0)) +
  scale_y_continuous(labels = scales::comma_format()) +
  
  labs(
    title    = "2026 World Cup — Cumulative Predicted Goals",
    subtitle = "Running total of home + away goals across all 104 matches",
    x        = NULL,
    y        = "Cumulative goals"
  ) +
  
  theme_minimal(base_size = 13) +
  theme(
    plot.title       = element_text(face = "bold", size = 15),
    plot.subtitle    = element_text(colour = "grey40", margin = margin(b = 10)),
    panel.grid.minor = element_blank(),
    panel.grid.major.x = element_blank(),
    axis.text.x      = element_text(size = 9, colour = "grey30"),
    legend.position  = "off"
  )

print(p)

# ── Save ─────────────────────────────────────────────────────────────────────
out_dir <- project_root("figures")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
ggsave(file.path(out_dir, "cumulative_goals.png"), p,
       width = 12, height = 6, dpi = 150)

message("Saved → figures/cumulative_goals.png")