# podium_table.R
# --------------
# Lists every participant with their name, abbreviation, and predicted
# Gold / Silver / Bronze from predictions.json + deltagere.json.
#
# Gold   = winner of the Final   (home if ft[1] > ft[2], else away, etc.)
# Silver = loser  of the Final
# Bronze = winner of the 3rd-Place match
#
# Usage: source this file from RStudio or run via Rscript.

library(tidyverse)
library(jsonlite)

# ---------------------------------------------------------------------------
# Project root (avoids collision with the `here` package loaded by tidyverse)
# ---------------------------------------------------------------------------
project_root <- function() {
  path <- normalizePath(
    rprojroot::find_root(rprojroot::has_dir(".git"),
                         path = dirname(sys.frame(1)$ofile %||% getwd())),
    mustWork = FALSE
  )
  path
}

# Simpler fallback that works when sourced interactively too
root <- tryCatch(
  rprojroot::find_root(rprojroot::has_dir(".git")),
  error = function(e) {
    # fall back to the directory two levels up from R/
    normalizePath(file.path(dirname(rstudioapi::getActiveDocumentContext()$path), ".."))
  }
)

gdata_dir <- file.path(root, "gData")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
preds_path     <- file.path(gdata_dir, "predictions.json")
deltagere_path <- file.path(gdata_dir, "deltagere.json")

preds     <- fromJSON(preds_path,     simplifyVector = FALSE)
deltagere <- fromJSON(deltagere_path, simplifyVector = FALSE)

# ---------------------------------------------------------------------------
# Build abbreviation lookup: file stem -> abbr
# ---------------------------------------------------------------------------
deltagere_df <- map_dfr(deltagere, ~ tibble(
  player_key = tools::file_path_sans_ext(.x$file),
  full_name  = .x$full_name,
  abbr       = .x$abbr
))

# ---------------------------------------------------------------------------
# Helper: derive winner of a match from ft / pen / et
# ---------------------------------------------------------------------------
match_winner <- function(m) {
  home <- m$home
  away <- m$away
  if (is.null(home) || is.null(away)) return(NA_character_)
  
  ft <- m$ft
  h  <- ft[[1]]; a <- ft[[2]]
  
  if (!is.null(h) && !is.null(a) && !is.na(h) && !is.na(a)) {
    if (h > a) return(home)
    if (a > h) return(away)
  }
  
  # Extra time
  et <- m$et
  if (!is.null(et)) {
    eh <- et[[1]]; ea <- et[[2]]
    if (!is.null(eh) && !is.null(ea) && !is.na(eh) && !is.na(ea)) {
      if (eh > ea) return(home)
      if (ea > eh) return(away)
    }
  }
  
  # Penalties
  pen <- m$pen
  if (!is.null(pen)) {
    ph <- pen[[1]]; pa <- pen[[2]]
    if (!is.null(ph) && !is.null(pa) && !is.na(ph) && !is.na(pa)) {
      if (ph > pa) return(home)
      if (pa > ph) return(away)
    }
  }
  
  NA_character_
}

match_loser <- function(m) {
  home <- m$home
  away <- m$away
  w    <- match_winner(m)
  if (is.na(w)) return(NA_character_)
  if (w == home) away else home
}

# ---------------------------------------------------------------------------
# Extract podium per player
# ---------------------------------------------------------------------------
podium_df <- imap_dfr(preds$players, function(player, key) {
  ko     <- player$knockout
  final  <- ko$final
  bronze <- ko$bronze
  
  tibble(
    player_key = as.character(key),
    gold       = match_winner(final),
    silver     = match_loser(final),
    bronze_team = match_winner(bronze)
  )
})

# ---------------------------------------------------------------------------
# Join with names / abbreviations
# ---------------------------------------------------------------------------
result <- podium_df %>%
  left_join(deltagere_df, by = "player_key") %>%
  select(full_name, abbr, gold, silver, bronze_team) %>%
  rename(
    Name       = full_name,
    Abbr       = abbr,
    Gold       = gold,
    Silver     = silver,
    Bronze     = bronze_team
  ) %>%
  arrange(Name)

# ---------------------------------------------------------------------------
# Print to console
# ---------------------------------------------------------------------------
cat("\n=== Predicted Podium per Participant ===\n\n")
print(result, n = Inf)

# ---------------------------------------------------------------------------
# Save as CSV
# ---------------------------------------------------------------------------
out_path <- file.path(gdata_dir, "podium_table.csv")
write_csv(result, out_path)
message("\nWrote → ", out_path)

result

# ---------------------------------------------------------------------------
# ggplot2 table — styled to match similarity_network_top3.R
# ---------------------------------------------------------------------------
library(ggplot2)

# Country colours for the medal columns (reuse the same palette idea)
medal_colours <- c(
  Gold   = "#F5C518",
  Silver = "#B0B8C4",
  Bronze = "#CD7F32"
)

# Reshape to long for colour mapping
long <- result %>%
  mutate(row = row_number()) %>%
  pivot_longer(c(Gold, Silver, Bronze),
               names_to  = "Medal",
               values_to = "Team") %>%
  mutate(
    Medal  = factor(Medal, levels = c("Gold", "Silver", "Bronze")),
    x_pos  = as.numeric(Medal),           # 1 = Gold, 2 = Silver, 3 = Bronze
    y_pos  = -row                         # top to bottom
  )

# Column header positions  (-2.2 = Name start, 0.1 = Abbr centre)
headers <- tibble(
  label = c("Name", "Abbr", "Gold", "Silver", "Bronze"),
  x_pos = c(-2.2, 0.1, 1.3, 2.3, 3.3),
  y_pos = 0.6
)

# Name and abbr columns
text_cols <- result %>%
  mutate(
    row    = row_number(),
    y_pos  = -row,
    x_name = -2.2,
    x_abbr = 0.1
  )

n_rows <- nrow(result)

p_table <- ggplot() +
  # Alternating row backgrounds
  geom_rect(
    data = tibble(row = seq(1, n_rows, 2)),
    aes(xmin = -2.7, xmax = 3.9,
        ymin = -row - 0.45, ymax = -row + 0.45),
    fill = "grey94", colour = NA
  ) +
  # Team name tiles (coloured by medal)
  geom_tile(
    data = long %>% mutate(x_pos = x_pos + 0.3),
    aes(x = x_pos, y = y_pos, fill = Medal),
    width = 0.95, height = 0.82, alpha = 0.85
  ) +
  scale_fill_manual(values = medal_colours, name = NULL) +
  # Team name text inside tiles
  geom_text(
    data = long %>% mutate(x_pos = x_pos + 0.3),
    aes(x = x_pos, y = y_pos, label = Team),
    size = 3.4, colour = "grey15", fontface = "plain"
  ) +
  # Full name column
  geom_text(
    data = text_cols,
    aes(x = x_name, y = y_pos, label = Name),
    hjust = 0, size = 3.6, colour = "grey20"
  ) +
  # Abbreviation column
  geom_text(
    data = text_cols,
    aes(x = x_abbr, y = y_pos, label = Abbr),
    hjust = 0.5, size = 3.6, colour = "grey20", fontface = "bold"
  ) +
  # Column headers
  geom_text(
    data = headers,
    aes(x = x_pos, y = y_pos, label = label),
    hjust = ifelse(headers$label == "Name", 0, 0.5),
    size = 3.8, colour = "grey10", fontface = "bold"
  ) +
  # Header separator line
  geom_hline(yintercept = 0.1, colour = "grey60", linewidth = 0.4) +
  coord_cartesian(xlim = c(-2.7, 3.9),
                  ylim = c(-n_rows - 0.6, 1.1),
                  clip = "off") +
  theme_void(base_size = 12) +
  theme(
    legend.position  = "none",
    plot.title       = element_text(size = 14, face = "bold",
                                    margin = margin(b = 4)),
    plot.subtitle    = element_text(size = 9,  colour = "grey45",
                                    margin = margin(b = 8)),
    plot.caption     = element_text(size = 7.5, colour = "grey55"),
    plot.margin      = margin(12, 12, 12, 12)
  ) +
  labs(
    title    = "World Cup 2026 — Predicted Podium",
    subtitle = "Each participant's predicted Gold / Silver / Bronze",
    caption  = paste("Generated", Sys.Date())
  )

out_png <- file.path(gdata_dir, "podium_table.png")
ggsave(out_png, p_table,
       width  = 10,
       height = max(3, 0.40 * n_rows + 1.6),
       dpi    = 150)
message("Wrote → ", out_png)

p_table