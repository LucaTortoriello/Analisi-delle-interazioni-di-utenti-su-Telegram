"""Analisi di comunità e nodi ponte sul grafo globale dei reply."""

import math
import threading
import time
from collections import Counter, defaultdict

import networkx as nx


_CACHE_TTL_SECONDS = 300
_cache_lock = threading.Lock()
_cache = {"created_at": 0.0, "analysis": None}


def _load_graph(run_query):
    rows = run_query("""
        MATCH (a:Utente)-[r:REPLIED_TO_GLOBAL]-(b:Utente)
        WHERE a.id < b.id AND r.count > 0
        RETURN a.id AS source, b.id AS target, sum(r.count) AS weight
    """) or []

    graph = nx.Graph()
    for row in rows:
        graph.add_edge(
            int(row["source"]),
            int(row["target"]),
            weight=float(row["weight"] or 1),
        )
    return graph


def _load_chat_activity(run_query):
    """Carica le chat che hanno generato i reply usati dal grafo."""
    return run_query("""
        MATCH (a:Utente)-[r:REPLIED_TO]->(b:Utente)
        WHERE r.count > 0 AND r.chatId IS NOT NULL
        RETURN a.id AS source, b.id AS target,
               r.chatId AS chat_id, r.count AS weight
    """) or []


def _weighted_pagerank(graph, alpha=0.85, max_iterations=60, tolerance=1e-9):
    """PageRank pesato senza dipendenze numeriche esterne."""
    node_count = graph.number_of_nodes()
    if not node_count:
        return {}

    ranks = {node: 1.0 / node_count for node in graph}
    strengths = dict(graph.degree(weight="weight"))
    base = (1.0 - alpha) / node_count

    for _ in range(max_iterations):
        next_ranks = {node: base for node in graph}
        dangling = sum(ranks[node] for node, strength in strengths.items() if not strength)
        dangling_share = alpha * dangling / node_count
        if dangling_share:
            for node in next_ranks:
                next_ranks[node] += dangling_share

        for source in graph:
            strength = strengths.get(source, 0.0)
            if not strength:
                continue
            contribution = alpha * ranks[source] / strength
            for target, edge_data in graph[source].items():
                next_ranks[target] += contribution * float(edge_data.get("weight", 1))

        delta = sum(abs(next_ranks[node] - ranks[node]) for node in graph)
        ranks = next_ranks
        if delta < tolerance:
            break

    return ranks


def _compute_analysis(graph, chat_activity=None):
    if graph.number_of_nodes() == 0:
        return {
            "node_metrics": {},
            "communities": [],
            "bridges": [],
            "summary": {"nodes": 0, "edges": 0, "community_count": 0},
        }

    raw_communities = nx.community.louvain_communities(
        graph,
        weight="weight",
        resolution=1.0,
        seed=42,
    )
    raw_communities = sorted(raw_communities, key=len, reverse=True)
    community_by_node = {
        node_id: community_id
        for community_id, members in enumerate(raw_communities, start=1)
        for node_id in members
    }

    pagerank = _weighted_pagerank(graph)
    weighted_degree = dict(graph.degree(weight="weight"))
    external_weight = defaultdict(float)
    external_communities = defaultdict(set)
    internal_weight = defaultdict(float)
    community_external_weight = defaultdict(float)
    community_chat_weights = defaultdict(Counter)

    for source, target, data in graph.edges(data=True):
        weight = float(data.get("weight", 1))
        source_community = community_by_node[source]
        target_community = community_by_node[target]
        if source_community == target_community:
            internal_weight[source_community] += weight
            continue
        external_weight[source] += weight
        external_weight[target] += weight
        external_communities[source].add(target_community)
        external_communities[target].add(source_community)
        community_external_weight[source_community] += weight
        community_external_weight[target_community] += weight

    for row in chat_activity or []:
        try:
            source_community = community_by_node[int(row["source"])]
            target_community = community_by_node[int(row["target"])]
            chat_id = int(row["chat_id"])
            weight = float(row.get("weight") or 1)
        except (KeyError, TypeError, ValueError):
            continue

        community_chat_weights[source_community][chat_id] += weight
        if target_community != source_community:
            community_chat_weights[target_community][chat_id] += weight

    node_metrics = {}
    for node_id in graph.nodes:
        total_weight = float(weighted_degree.get(node_id, 0))
        outside_weight = float(external_weight.get(node_id, 0))
        bridge_score = (
            math.log1p(outside_weight)
            * math.log1p(total_weight)
            * (1 + math.log1p(len(external_communities.get(node_id, set()))))
        )
        node_metrics[node_id] = {
            "community": community_by_node[node_id],
            "pagerank": pagerank.get(node_id, 0.0),
            "weighted_degree": total_weight,
            "external_weight": outside_weight,
            "external_communities": len(external_communities.get(node_id, set())),
            "bridge_score": bridge_score,
        }

    communities = []
    for community_id, members in enumerate(raw_communities, start=1):
        communities.append({
            "id": community_id,
            "size": len(members),
            "internal_weight": int(internal_weight.get(community_id, 0)),
            "external_weight": int(community_external_weight.get(community_id, 0)),
            "top_chat_ids": [
                chat_id
                for chat_id, _ in community_chat_weights[community_id].most_common(3)
            ],
        })

    top_bridges = sorted(
        (
            {"id": node_id, **metrics}
            for node_id, metrics in node_metrics.items()
            if metrics["external_communities"] > 0
        ),
        key=lambda row: row["bridge_score"],
        reverse=True,
    )[:50]

    return {
        "node_metrics": node_metrics,
        "communities": communities,
        "bridges": top_bridges,
        "summary": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "community_count": len(communities),
            "largest_community": communities[0]["size"] if communities else 0,
        },
    }


def get_community_analysis(run_query, force=False):
    """Restituisce l'analisi, riusando per cinque minuti il risultato in RAM."""
    now = time.monotonic()
    with _cache_lock:
        cached = _cache["analysis"]
        if not force and cached and now - _cache["created_at"] < _CACHE_TTL_SECONDS:
            return cached

        graph = _load_graph(run_query)
        analysis = _compute_analysis(graph, _load_chat_activity(run_query))
        _cache["analysis"] = analysis
        _cache["created_at"] = time.monotonic()
        return analysis
