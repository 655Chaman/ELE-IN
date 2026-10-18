"""
Three-Layer Paranoia Framework: Campaign Sequence DAG Validator & Loop Guard
- Layer 0 (Foundational): Iterative Kahn's algorithm cycle detection and BFS reachability.
- Layer 1 (Environmental): Stack-safe iterative traversal (zero RecursionError risk on 1,500+ node graphs),
  dual edge-key normalization (source/target and source_node_id/target_node_id), and malformed payload resilience.
- Layer 2 (Human Paranoia): Detects isolated/orphaned nodes on the canvas, dangling edges to deleted nodes,
  unreachable outreach touchpoints, and dead-end conditional branch nodes.
"""
import json
from collections import deque
from typing import List, Dict, Any, Set, Optional, Tuple

TOUCHPOINT_KEYWORDS = ("message", "connection", "inmail", "followup", "invite", "voice_note")
BRANCH_NODE_TYPES = {"if_connected", "if_replied", "if_icp_score", "ab_split", "icp_score_gate"}


def _extract_edge_endpoints(edge: Any) -> tuple:
    if not isinstance(edge, dict):
        return None, None
    src = edge.get("source") if edge.get("source") is not None else edge.get("source_node_id")
    tgt = edge.get("target") if edge.get("target") is not None else edge.get("target_node_id")
    if src is None or tgt is None:
        return None, None
    src_str = str(src).strip()
    tgt_str = str(tgt).strip()
    if not src_str or not tgt_str:
        return None, None
    return src_str, tgt_str


def _is_touchpoint_node(node: dict) -> bool:
    ntype = str(node.get("type") or node.get("node_type") or "").lower()
    return any(k in ntype for k in TOUCHPOINT_KEYWORDS)


def _is_branch_node(node: dict) -> bool:
    ntype = str(node.get("type") or node.get("node_type") or "").lower()
    return ntype in BRANCH_NODE_TYPES or ntype.startswith("if_")


def has_cycle(nodes: list, edges: list) -> bool:
    """
    Iterative Kahn's topological sort + self-loop guard.
    Returns True if the directed graph contains any cycle.
    Supports both (source, target) and (source_node_id, target_node_id).
    Never raises RecursionError regardless of graph depth.
    """
    if not nodes or not isinstance(nodes, list):
        return False

    node_ids: List[str] = []
    seen_ids: Set[str] = set()
    for n in nodes:
        if isinstance(n, dict) and n.get("id") is not None:
            nid = str(n["id"]).strip()
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                node_ids.append(nid)

    if not node_ids:
        return False

    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}

    seen_edges: Set[Tuple[str, str]] = set()
    for e in (edges or []):
        src, tgt = _extract_edge_endpoints(e)
        if not src or not tgt:
            continue
        # Direct self-loop on a valid node
        if src == tgt and src in seen_ids:
            return True
        edge_pair = (src, tgt)
        if edge_pair in seen_edges:
            continue
        seen_edges.add(edge_pair)
        if src in seen_ids and tgt in seen_ids:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    visited_count = 0

    while queue:
        curr = queue.popleft()
        visited_count += 1
        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    return visited_count < len(node_ids)


def validate_sequence_dag(nodes: list, edges: list) -> Dict[str, Any]:
    """
    Performs full DAG structural and reachability analysis.
    """
    safe_nodes = [n for n in (nodes or []) if isinstance(n, dict) and n.get("id") is not None]
    safe_edges = [e for e in (edges or []) if isinstance(e, dict)]

    node_map: Dict[str, dict] = {}
    node_order: List[str] = []
    for n in safe_nodes:
        nid = str(n["id"]).strip()
        if nid and nid not in node_map:
            node_map[nid] = n
            node_order.append(nid)

    if not node_order:
        return {
            "has_cycle": False,
            "dangling_edges": [],
            "root_node_ids": [],
            "reachable_node_ids": [],
            "orphaned_node_ids": [],
            "dead_end_branch_nodes": [],
            "total_touchpoints": 0,
            "reachable_touchpoints": 0,
        }

    adj: Dict[str, List[str]] = {nid: [] for nid in node_order}
    in_degree: Dict[str, int] = {nid: 0 for nid in node_order}
    out_degree: Dict[str, int] = {nid: 0 for nid in node_order}
    dangling_edges: List[Dict[str, str]] = []

    seen_edges: Set[Tuple[str, str]] = set()
    for e in safe_edges:
        src, tgt = _extract_edge_endpoints(e)
        if not src or not tgt:
            continue
        if src not in node_map or tgt not in node_map:
            dangling_edges.append({"source": src, "target": tgt})
            continue
        edge_pair = (src, tgt)
        if edge_pair in seen_edges:
            continue
        seen_edges.add(edge_pair)
        adj[src].append(tgt)
        out_degree[src] += 1
        in_degree[tgt] += 1

    cycle_detected = has_cycle(safe_nodes, safe_edges)

    root_node_ids = [nid for nid in node_order if in_degree[nid] == 0]
    # Primary entry roots: if edges exist, prefer roots that have outgoing edges
    connected_roots = [nid for nid in root_node_ids if out_degree[nid] > 0]
    entry_roots = [connected_roots[0]] if connected_roots else (root_node_ids[:1] if root_node_ids else [])

    # BFS reachability from primary entry root (matches EleInOrchestrator start node behavior)
    reachable_set: Set[str] = set()
    if not safe_edges:
        # When no edges are provided (e.g. single-node or unlinked list), treat all nodes as reachable
        reachable_set = set(node_order)
    else:
        bfs_queue = deque(entry_roots)
        while bfs_queue:
            curr = bfs_queue.popleft()
            if curr in reachable_set:
                continue
            reachable_set.add(curr)
            for nxt in adj.get(curr, []):
                if nxt not in reachable_set:
                    bfs_queue.append(nxt)

    reachable_node_ids = [nid for nid in node_order if nid in reachable_set]
    orphaned_node_ids = []
    if len(node_order) > 1 and len(safe_edges) > 0:
        orphaned_node_ids = [nid for nid in node_order if nid not in reachable_set]

    dead_end_branch_nodes = [
        nid for nid in node_order
        if _is_branch_node(node_map[nid]) and out_degree[nid] == 0
    ]

    total_touchpoints = sum(1 for nid in node_order if _is_touchpoint_node(node_map[nid]))
    reachable_touchpoints = sum(1 for nid in reachable_node_ids if _is_touchpoint_node(node_map[nid]))

    return {
        "has_cycle": cycle_detected,
        "dangling_edges": dangling_edges,
        "root_node_ids": root_node_ids,
        "reachable_node_ids": reachable_node_ids,
        "orphaned_node_ids": orphaned_node_ids,
        "dead_end_branch_nodes": dead_end_branch_nodes,
        "total_touchpoints": total_touchpoints,
        "reachable_touchpoints": reachable_touchpoints,
    }


def check_optimistic_concurrency(
    existing_campaign: dict,
    current_version: Optional[int] = None,
    expected_version: Optional[int] = None,
    expected_updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 1 & 2: Optimistic Concurrency Control (OCC) for Campaign Sequence Saves.
    Detects multi-tab stale overwrites by comparing caller's expected_version or expected_updated_at
    against the persisted campaign record.
    """
    if not isinstance(existing_campaign, dict):
        return {"conflict": False, "reason": None, "current_version": current_version, "current_updated_at": None}

    meta = existing_campaign.get("metadata") if isinstance(existing_campaign.get("metadata"), dict) else {}
    resolved_version = current_version if isinstance(current_version, int) else meta.get("version")
    db_updated_at = existing_campaign.get("updated_at")

    if expected_version is not None and resolved_version is not None:
        try:
            if int(expected_version) != int(resolved_version):
                return {
                    "conflict": True,
                    "reason": (
                        f"Optimistic concurrency conflict: Campaign was modified by another session "
                        f"(expected version {expected_version}, current version is {resolved_version}). "
                        f"Please refresh before saving."
                    ),
                    "current_version": resolved_version,
                    "current_updated_at": db_updated_at,
                }
        except (ValueError, TypeError):
            pass

    if expected_updated_at is not None and isinstance(db_updated_at, str) and db_updated_at.strip():
        exp_ts = str(expected_updated_at).strip()
        cur_ts = db_updated_at.strip()
        if exp_ts and exp_ts != cur_ts:
            return {
                "conflict": True,
                "reason": (
                    f"Optimistic concurrency conflict: Campaign was modified since it was loaded "
                    f"(expected updated_at '{exp_ts}', current is '{cur_ts}'). "
                    f"Please refresh before saving."
                ),
                "current_version": resolved_version,
                "current_updated_at": cur_ts,
            }

    return {
        "conflict": False,
        "reason": None,
        "current_version": resolved_version,
        "current_updated_at": db_updated_at,
    }


def _normalize_nodes_list(raw_nodes: Any) -> List[dict]:
    if isinstance(raw_nodes, str):
        try:
            raw_nodes = json.loads(raw_nodes)
        except Exception:
            return []
    if not isinstance(raw_nodes, list):
        return []
    return [n for n in raw_nodes if isinstance(n, dict) and n.get("id") is not None]


def validate_active_campaign_graph_mutation(
    existing_nodes: Any,
    new_nodes: Any,
    in_flight_node_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 1 & 2: Active-Enrollment Structural Mutation Lock.
    When a campaign is ACTIVE, deleting existing nodes or changing their action type
    orphans in-flight leads executing on those nodes.
    """
    old_list = _normalize_nodes_list(existing_nodes)
    new_list = _normalize_nodes_list(new_nodes)

    old_map: Dict[str, str] = {}
    for n in old_list:
        nid = str(n["id"]).strip()
        ntype = str(n.get("type") or n.get("node_type") or "unknown").strip().lower()
        if nid:
            old_map[nid] = ntype

    new_map: Dict[str, str] = {}
    for n in new_list:
        nid = str(n["id"]).strip()
        ntype = str(n.get("type") or n.get("node_type") or "unknown").strip().lower()
        if nid:
            new_map[nid] = ntype

    deleted_node_ids = [nid for nid in old_map if nid not in new_map]
    type_mutated_nodes = [
        {"node_id": nid, "old_type": old_map[nid], "new_type": new_map[nid]}
        for nid in old_map
        if nid in new_map and old_map[nid] != new_map[nid]
    ]

    in_flight_set = {str(x).strip() for x in (in_flight_node_ids or set()) if x}
    mutated_ids = set(deleted_node_ids) | {m["node_id"] for m in type_mutated_nodes}
    orphaned_in_flight = sorted(list(in_flight_set & mutated_ids))

    is_safe = len(deleted_node_ids) == 0 and len(type_mutated_nodes) == 0
    return {
        "is_safe": is_safe,
        "deleted_node_ids": deleted_node_ids,
        "type_mutated_nodes": type_mutated_nodes,
        "orphaned_in_flight_nodes": orphaned_in_flight,
    }

