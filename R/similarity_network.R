# similarity_network.R
# --------------------
# Draws a network graph where nodes are players and edges represent
# pairwise prediction similarity.  Edge thickness and colour reflect
# the normalised similarity score; negative similarities are drawn as
# dashed red edges.  Node size reflects each player's self-score
# (their theoretical maximum), so more "decisive" predictors appear larger.

library(tidyverse)
library(jsonlite)
library(igraph)
library(ggraph)
library(here)

# ---------------------------------------------------------------------------
# Project-root helper (avoids collision with here::here)
# ---------------------------------------------------------------------------
project_root <- function() here::here()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
sim_path <- file.path(project_root(), "gData", "similarity.json")
sim      <- fromJSON(sim_path, simplifyVector = FALSE)

self_scores <- tibble(
  player     = names(sim$self_scores),
  self_score = unlist(sim$self_scores)
)

pairs_df <- imap_dfr(sim$pairs, function(pair, i) {
  tibble(
    player_a   = pair$player_a,
    player_b   = pair$player_b,
    score_ab   = pair$score_ab,
    score_ba   = pair$score_ba,
    avg_raw    = pair$avg_raw,
    normalised = pair$normalised
  )
})

# ---------------------------------------------------------------------------
# Build igraph object
# ---------------------------------------------------------------------------
nodes <- self_scores

edges <- pairs_df %>%
  filter(normalised >= 0.6) %>%
  mutate(
    positive = normalised >= 0,
    abs_sim  = abs(normalised)
  )

g <- graph_from_data_frame(
  d        = edges %>% select(player_a, player_b, normalised, abs_sim, positive),
  vertices = nodes %>% select(player, self_score),
  directed = FALSE
)

# Use similarity as layout weight so similar players cluster together
E(g)$weight <- pmax(E(g)$normalised, 0.01)

set.seed(42)
layout <- create_layout(g, layout = "fr")

# ---------------------------------------------------------------------------
# Edge midpoints for labels (geom_edge_label doesn't exist in ggraph)
# ---------------------------------------------------------------------------
edge_labels <- edges %>%
  left_join(layout %>% select(name, x, y), by = c("player_a" = "name")) %>%
  rename(x1 = x, y1 = y) %>%
  left_join(layout %>% select(name, x, y), by = c("player_b" = "name")) %>%
  rename(x2 = x, y2 = y) %>%
  mutate(
    mx    = (x1 + x2) / 2,
    my    = (y1 + y2) / 2,
    label = sprintf("%.2f", normalised)
  )

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
pal_edge_pos <- "#2166ac"   # blue  — similar
pal_edge_neg <- "#d73027"   # red   — dissimilar
pal_node     <- "#4dac26"   # green

p <- ggraph(layout) +
  
  # Negative edges (dashed red)
  geom_edge_link(
    aes(edge_width = abs_sim, filter = !positive),
    colour   = pal_edge_neg,
    linetype = "dashed",
    alpha    = 0.7
  ) +
  
  # Positive edges (solid blue)
  geom_edge_link(
    aes(edge_width = abs_sim, edge_alpha = abs_sim, filter = positive),
    colour = pal_edge_pos
  ) +
  
  # Edge labels at midpoints
  geom_text(
    data        = edge_labels,
    aes(x = mx, y = my, label = label),
    size        = 3,
    colour      = "grey25",
    inherit.aes = FALSE
  ) +
  
  # Nodes
  geom_node_point(
    aes(size = self_score),
    colour = pal_node,
    alpha  = 0.85
  ) +
  
  # Node labels
  geom_node_label(
    aes(label = name),
    repel         = TRUE,
    size          = 4,
    fontface      = "bold",
    label.padding = unit(0.2, "lines"),
    label.size    = 0.3,
    fill          = "white"
  ) +
  
  scale_edge_width(range = c(0.4, 4), guide = "none") +
  scale_edge_alpha(range = c(0.3, 1), guide = "none") +
  scale_size(
    name   = "Self-score",
    range  = c(4, 14),
    labels = scales::comma
  ) +
  
  labs(
    title    = "Player prediction similarity",
    subtitle = "Only edges with similarity ≥ 0.6 shown  ·  Edge thickness = similarity  ·  Node size = self-score",
    caption  = "Similarity: avg score each player earns using the other's predictions as ground truth,\nnormalised by geometric mean of self-scores."
  ) +
  
  theme_graph(base_family = "sans") +
  theme(
    plot.title      = element_text(size = 14, face = "bold"),
    plot.subtitle   = element_text(size = 9,  colour = "grey40"),
    plot.caption    = element_text(size = 7,  colour = "grey50"),
    legend.position = "right"
  )

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
out_path <- file.path(project_root(), "gData", "similarity_network.png")
ggsave(out_path, p, width = 8, height = 6, dpi = 150)
message("Wrote → ", out_path)

p