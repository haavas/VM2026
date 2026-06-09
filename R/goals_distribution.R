library(tidyverse)
library(jsonlite)

project_root <- function(...) {
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
raw <- fromJSON(project_root("gData", "simulations.json"), simplifyVector = FALSE)

STAGE_BREAKS <- c(72, 88, 96, 100, 102, 104)
STAGE_LABELS <- c(
  "Group Stage", "Round of 32", "Round of 16",
  "Quarterfinals", "Semi-Finals", "3rd/Final"
)
STAGE_COLORS <- c(
  "Group Stage"   = "#a8c8e8",
  "Round of 32"   = "#7baecf",
  "Round of 16"   = "#5592bc",
  "Quarterfinals" = "#3376a8",
  "Semi-Finals"   = "#1a5c8f",
  "3rd/Final"     = "#0a3d6b"
)

stage_of <- function(mn) {
  cut(mn,
    breaks = c(0, STAGE_BREAKS),
    labels = STAGE_LABELS
  )
}

# Build long data frame: one row per (match, goals_value) weighted by frequency
df <- imap_dfr(raw$match_goals, function(info, mn_chr) {
  mn <- as.integer(mn_chr)
  imap_dfr(info$freq, function(freq, goals_chr) {
    tibble(
      match    = mn,
      goals    = as.integer(goals_chr),
      freq     = as.numeric(freq),
      avg      = as.numeric(info$avg),
      stage    = as.character(stage_of(mn))
    )
  })
}) |>
  mutate(stage = factor(stage, levels = STAGE_LABELS))

# ── Plot 1: Density ridge per stage ─────────────────────────────────────────
# Aggregate: average frequency across all matches in each stage
stage_df <- df |>
  group_by(stage, goals) |>
  summarise(freq = mean(freq), .groups = "drop")

p1 <- ggplot(stage_df, aes(x = goals, y = freq, fill = stage, colour = stage)) +
  geom_col(alpha = 0.85, width = 0.7) +
  facet_wrap(~stage, ncol = 3) +
  scale_fill_manual(values = STAGE_COLORS, guide = "none") +
  scale_colour_manual(values = STAGE_COLORS, guide = "none") +
  scale_x_continuous(breaks = 0:10) +
  scale_y_continuous(labels = scales::percent_format()) +
  labs(
    title    = "Goal Distribution by Stage — 10,000 Simulations",
    subtitle = "Average probability of each goals total across all matches in each stage",
    x        = "Total goals in match",
    y        = "Probability"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(colour = "grey40"),
    panel.grid.minor = element_blank(),
    strip.text       = element_text(face = "bold")
  )

# ── Plot 2: Heatmap — goals distribution across all 104 matches ──────────────
p2 <- ggplot(df, aes(x = match, y = goals, fill = freq)) +
  geom_tile() +

  # Stage boundary lines
  geom_vline(xintercept = STAGE_BREAKS + 0.5,
             colour = "white", linewidth = 0.8, linetype = "dashed") +

  # Stage labels at top
  annotate("text",
    x = c(36, 80.5, 92.5, 98.5, 101.5, 103.5),
    y = max(df$goals) + 0.7,
    label = c("Group Stage", "R32", "R16", "QF", "SF", "F"),
    size = 3, colour = "grey30", hjust = 0.5
  ) +

  # Average goals line
  geom_line(
    data = df |> group_by(match) |> summarise(avg = first(avg), .groups = "drop"),
    aes(x = match, y = avg),
    inherit.aes = FALSE,
    colour = "white", linewidth = 1, linetype = "solid", alpha = 0.9
  ) +

  scale_fill_gradient(low = "#f0f4f8", high = "#0a3d6b",
                      labels = scales::percent_format(),
                      name = "Probability") +
  scale_x_continuous(breaks = c(1, seq(10, 70, 10), STAGE_BREAKS),
                     expand = c(0.005, 0)) +
  scale_y_continuous(breaks = 0:10, expand = c(0.05, 0)) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "Goals Distribution — All 104 Matches",
    subtitle = "Colour = probability of that goals total; white line = average",
    x        = "Match number",
    y        = "Total goals in match"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(colour = "grey40"),
    panel.grid       = element_blank(),
    legend.position  = "right",
    plot.margin      = margin(t = 20, r = 10, b = 5, l = 5)
  )

# ── Save ─────────────────────────────────────────────────────────────────────
out_dir <- project_root("figures")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

ggsave(file.path(out_dir, "goals_by_stage.png"),   p1, width = 10, height = 7,  dpi = 150)
ggsave(file.path(out_dir, "goals_heatmap.png"),    p2, width = 14, height = 6,  dpi = 150)

message("Saved → figures/goals_by_stage.png")
message("Saved → figures/goals_heatmap.png")
