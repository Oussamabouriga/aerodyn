from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Iterable, Optional
import math


@dataclass(frozen=True)
class Edge:
    claim_id: str
    src: str
    dst: str
    polarity: str  # '+' or '-'
    delay_months: int = 0
    confidence: float = 0.6


@dataclass
class Loop:
    loop_id: str
    loop_type: str  # 'R' reinforcing, 'B' balancing
    sign: int       # +1 or -1
    nodes: List[str]
    edge_claim_ids: List[str]


def _sign_from_polarity(p: str) -> int:
    return -1 if str(p).strip() == "-" else +1


def build_graph(edges: Iterable[Edge]) -> Tuple[Set[str], Dict[str, List[Edge]]]:
    nodes: Set[str] = set()
    adj: Dict[str, List[Edge]] = {}
    for e in edges:
        nodes.add(e.src)
        nodes.add(e.dst)
        adj.setdefault(e.src, []).append(e)
    return nodes, adj


def _canonical_cycle(nodes: List[str], edges: List[str]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """
    Canonicalize a directed cycle by rotating to a lexicographically smallest representation.
    nodes is like [A,B,C,A] or [A,B,C] (we will normalize).
    edges is aligned to transitions (A->B, B->C, C->A).
    """
    # normalize nodes to not repeat start at end
    if len(nodes) >= 2 and nodes[0] == nodes[-1]:
        nodes = nodes[:-1]

    n = len(nodes)
    if n == 0:
        return tuple(), tuple()

    # rotate both nodes and edges together
    rotations = []
    for k in range(n):
        rn = tuple(nodes[k:] + nodes[:k])
        re = tuple(edges[k:] + edges[:k])
        rotations.append((rn, re))

    return min(rotations, key=lambda x: x[0])


def find_cycles(
    adj: Dict[str, List[Edge]],
    max_len: int = 8,
) -> List[Tuple[List[str], List[str]]]:
    """
    Returns cycles as (nodes_in_order, edge_claim_ids_in_order).
    Cycle nodes returned WITHOUT repeating start at end.
    """
    all_nodes = sorted(set(adj.keys()) | {e.dst for edges in adj.values() for e in edges})
    seen: Set[Tuple[Tuple[str, ...], Tuple[str, ...]]] = set()
    out: List[Tuple[List[str], List[str]]] = []

    def dfs(start: str, current: str, path_nodes: List[str], path_edges: List[str], in_path: Set[str]):
        if len(path_nodes) > max_len:
            return

        for e in adj.get(current, []):
            nxt = e.dst

            if nxt == start and len(path_nodes) >= 2:
                cycle_nodes = path_nodes + [start]
                cycle_edges = path_edges + [e.claim_id]

                canon = _canonical_cycle(cycle_nodes, cycle_edges)
                if canon not in seen:
                    seen.add(canon)
                    # store cycle without repeating start
                    out.append((list(canon[0]), list(canon[1])))
                continue

            if nxt in in_path:
                continue

            in_path.add(nxt)
            dfs(start, nxt, path_nodes + [nxt], path_edges + [e.claim_id], in_path)
            in_path.remove(nxt)

    for start in all_nodes:
        dfs(start, start, [start], [], {start})

    return out


def loops_from_cycles(cycles: List[Tuple[List[str], List[str]]], edge_by_id: Dict[str, Edge]) -> List[Loop]:
    loops: List[Loop] = []
    for i, (nodes, edge_ids) in enumerate(cycles, start=1):
        sign = +1
        for cid in edge_ids:
            sign *= _sign_from_polarity(edge_by_id[cid].polarity)

        loop_type = "R" if sign == +1 else "B"
        loops.append(
            Loop(
                loop_id=f"LOOP_{i:03d}",
                loop_type=loop_type,
                sign=sign,
                nodes=nodes,
                edge_claim_ids=edge_ids,
            )
        )
    return loops


def circular_layout(nodes: List[str], radius: float = 1.0) -> Dict[str, Tuple[float, float]]:
    """
    Simple dependency-free layout.
    """
    n = max(len(nodes), 1)
    pos: Dict[str, Tuple[float, float]] = {}
    for i, node in enumerate(nodes):
        theta = 2 * math.pi * (i / n)
        pos[node] = (radius * math.cos(theta), radius * math.sin(theta))
    return pos