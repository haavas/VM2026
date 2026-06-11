# similarity_network_top3.R
# -------------------------
# Variant of similarity_network.R where each player keeps only their
# three most similar partners.  Nodes are coloured by predicted world
# champion; all nodes are the same size.

library(tidyverse)
library(jsonlite)
library(igraph)
library(ggraph)
library(here)

project_root <- function() here::here()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
sim_path   <- file.path(project_root(), "gData", "similarity.json")
preds_path <- file.path(project_root(), "gData", "predictions.json")

sim   <- fromJSON(sim_path,   simplifyVector = FALSE)
preds <- fromJSON(preds_path, simplifyVector = FALSE)

# Node table: one row per player, with their predicted world champion
nodes <- imap_dfr(preds$players, function(p, name) {
  tibble(
    player    = name,
    champion  = p$world_champion %||% "Unknown"
  )
})

pairs_df <- imap_dfr(sim$pairs, function(pair, i) {
  tibble(
    player_a   = pair$player_a,
    player_b   = pair$player_b,
    normalised = pair$normalised
  )
})

# ---------------------------------------------------------------------------
# Keep top-3 edges per player (union across both endpoints)
# ---------------------------------------------------------------------------
long <- bind_rows(
  pairs_df %>% rename(focal = player_a, other = player_b),
  pairs_df %>% rename(focal = player_b, other = player_a)
)

top3_pairs <- long %>%
  group_by(focal) %>%
  slice_max(normalised, n = 3, with_ties = FALSE) %>%
  ungroup() %>%
  mutate(
    pa = if_else(focal < other, focal, other),
    pb = if_else(focal < other, other, focal)
  ) %>%
  distinct(pa, pb)

edges <- pairs_df %>%
  mutate(
    pa = if_else(player_a < player_b, player_a, player_b),
    pb = if_else(player_a < player_b, player_b, player_a)
  ) %>%
  semi_join(top3_pairs, by = c("pa", "pb")) %>%
  select(-pa, -pb) %>%
  mutate(abs_sim = abs(normalised))

# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------
g <- graph_from_data_frame(
  d        = edges %>% select(player_a, player_b, normalised, abs_sim),
  vertices = nodes %>% select(player, champion),
  directed = FALSE
)

E(g)$weight <- pmax(E(g)$normalised, 0.01)

# Set champion as a vertex attribute so create_layout carries it through
V(g)$champion <- nodes$champion[match(V(g)$name, nodes$player)]

set.seed(42)
layout <- create_layout(g, layout = "fr")

# Edge midpoints for labels
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
# Colour palette — one colour per unique predicted champion
# ---------------------------------------------------------------------------
champions  <- sort(unique(nodes$champion))
n_champs   <- length(champions)
champ_cols <- setNames(
  scales::hue_pal()(n_champs),
  champions
)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
pal_edge <- "#555555"

p <- ggraph(layout) +

  geom_edge_link(
    aes(edge_width = abs_sim, edge_alpha = abs_sim),
    colour = pal_edge
  ) +

  geom_text(
    data        = edge_labels,
    aes(x = mx, y = my, label = label),
    size        = 3,
    colour      = "grey25",
    inherit.aes = FALSE
  ) +

  geom_node_point(
    aes(colour = champion),
    size  = 8,
    alpha = 0.9
  ) +

  geom_node_label(
    aes(label = name),
    repel         = TRUE,
    size          = 4,
    fontface      = "bold",
    label.padding = unit(0.2, "lines"),
    label.size    = 0.3,
    fill          = "white"
  ) +

  scale_colour_manual(
    name   = "Predicted winner",
    values = champ_cols
  ) +
  scale_edge_width(range = c(0.4, 4), guide = "none") +
  scale_edge_alpha(range = c(0.3, 1), guide = "none") +

  labs(
    title    = "Player prediction similarity — top 3 per player",
    subtitle = "Each player's three most similar partners shown  ·  Edge thickness = similarity  ·  Node colour = predicted champion",
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
out_path <- file.path(project_root(), "gData", "similarity_network_top3.png")
ggsave(out_path, p, width = 8, height = 6, dpi = 150)
message("Wrote → ", out_path)

p
