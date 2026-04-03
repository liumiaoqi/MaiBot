"""Flowchart parsers for flow-type skills.

This module provides parsers for Mermaid and D2 flowchart syntax
to convert them into Flow objects that can be executed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentlite.skills.models import Flow, FlowEdge, FlowNode


class FlowParseError(ValueError):
    """Raised when flowchart parsing fails."""

    pass


def parse_mermaid_flowchart(content: str) -> "Flow":
    """Parse a Mermaid flowchart into a Flow object.

    Supports basic Mermaid flowchart syntax:
    - Node definitions: `id[label]`, `id(label)`, `id{label}`
    - Edges: `-->`, `---`, `-.->`
    - Labeled edges: `-->|label|`, `-.->|label|`
    - Special nodes: BEGIN(( )), END(( ))

    Args:
        content: Mermaid flowchart definition

    Returns:
        Flow object representing the flowchart

    Raises:
        FlowParseError: If parsing fails

    Example:
        >>> mermaid = '''
        ... flowchart TD
        ...     BEGIN(( )) --> CHECK[Check input]
        ...     CHECK --> VALID{Is valid?}
        ...     VALID -->|Yes| PROCESS[Process]
        ...     VALID -->|No| ERROR[Show error]
        ...     PROCESS --> END(( ))
        ...     ERROR --> END
        ... '''
        >>> flow = parse_mermaid_flowchart(mermaid)
    """
    from agentlite.skills.models import Flow, FlowEdge, FlowNode

    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []

    # Node patterns
    # id[label] - rectangle
    # id(label) - rounded
    # id{label} - diamond
    # id(( )) - circle (used for begin/end)
    node_pattern = re.compile(
        r"^(\w+)\s*"  # node ID
        r"(?:\[(.*?)\]|"  # [label]
        r"\((.*?)\)|"  # (label)
        r"\{(.*?)\}|"  # {label}
        r"\(\((.*?)\)\))"  # ((label))
    )

    # Edge patterns
    # A --> B
    # A -->|label| B
    # A -.-> B
    edge_pattern = re.compile(
        r"^(\w+)\s*"  # source
        r"(?:-->|---|-.->)"  # arrow
        r"\|([^|]*)\|?\s*"  # optional label
        r"(\w+)\s*$"  # destination
    )

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("flowchart") or line.startswith("graph"):
            continue

        # Remove trailing punctuation
        line = line.rstrip(";")

        # Try to match edge first
        edge_match = edge_pattern.match(line)
        if edge_match:
            src, label, dst = edge_match.groups()
            edges.append(
                FlowEdge(src=src.strip(), dst=dst.strip(), label=label.strip() if label else None)
            )
            continue

        # Try to match node definition
        node_match = node_pattern.match(line)
        if node_match:
            node_id = node_match.group(1)
            # Get the first non-None label from groups
            label = next((g for g in node_match.groups()[1:] if g is not None), node_id)

            # Determine node kind
            kind = "task"
            if label.strip() == "" or node_id.upper() in ("BEGIN", "START"):
                kind = "begin"
            elif node_id.upper() in ("END", "STOP", "FINISH"):
                kind = "end"
            elif "{" in line or "}" in line:
                kind = "decision"

            nodes[node_id] = FlowNode(id=node_id, label=label, kind=kind)

    # Build outgoing edge map
    outgoing: dict[str, list[FlowEdge]] = {}
    for edge in edges:
        if edge.src not in outgoing:
            outgoing[edge.src] = []
        outgoing[edge.src].append(edge)

    # Find begin and end nodes
    begin_ids = [n.id for n in nodes.values() if n.kind == "begin"]
    end_ids = [n.id for n in nodes.values() if n.kind == "end"]

    if not begin_ids:
        # Use first node if no explicit begin
        begin_ids = [list(nodes.keys())[0]] if nodes else []
    if not end_ids:
        # Use last node if no explicit end
        end_ids = [list(nodes.keys())[-1]] if nodes else []

    if len(begin_ids) != 1:
        raise FlowParseError(f"Expected exactly one BEGIN node, found {len(begin_ids)}")
    if len(end_ids) != 1:
        raise FlowParseError(f"Expected exactly one END node, found {len(end_ids)}")

    return Flow(nodes=nodes, outgoing=outgoing, begin_id=begin_ids[0], end_id=end_ids[0])


def parse_d2_flowchart(content: str) -> "Flow":
    """Parse a D2 flowchart into a Flow object.

    Supports basic D2 syntax:
    - Node definitions: `id: label`
    - Edges: `id1 -> id2` or `id1 -> id2: label`
    - Special shapes: `id: {shape: circle}`

    Args:
        content: D2 flowchart definition

    Returns:
        Flow object representing the flowchart

    Raises:
        FlowParseError: If parsing fails

    Example:
        >>> d2 = '''
        ... BEGIN: {shape: circle}
        ... CHECK: Check input
        ... VALID: Is valid? {shape: diamond}
        ... PROCESS: Process
        ... ERROR: Show error
        ... END: {shape: circle}
        ...
        ... BEGIN -> CHECK
        ... CHECK -> VALID
        ... VALID -> PROCESS: Yes
        ... VALID -> ERROR: No
        ... PROCESS -> END
        ... ERROR -> END
        ... '''
        >>> flow = parse_d2_flowchart(d2)
    """
    from agentlite.skills.models import Flow, FlowEdge, FlowNode

    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []

    # Node pattern: id: label or id: {shape: ...}
    node_pattern = re.compile(r"^(\w+)\s*:\s*(.+)$")

    # Edge pattern: src -> dst or src -> dst: label
    edge_pattern = re.compile(r"^(\w+)\s*->\s*(\w+)(?:\s*:\s*(.+))?$")

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Try edge first
        edge_match = edge_pattern.match(line)
        if edge_match:
            src, dst, label = edge_match.groups()
            edges.append(
                FlowEdge(src=src.strip(), dst=dst.strip(), label=label.strip() if label else None)
            )
            continue

        # Try node definition
        node_match = node_pattern.match(line)
        if node_match:
            node_id, rest = node_match.groups()
            rest = rest.strip()

            # Check for shape definition
            shape_match = re.search(r"\{shape:\s*(\w+)\}", rest)
            shape = shape_match.group(1) if shape_match else None

            # Extract label (remove shape definition)
            label = re.sub(r"\{[^}]*\}", "", rest).strip()
            if not label:
                label = node_id

            # Determine kind
            kind = "task"
            if shape == "circle" or node_id.upper() in ("BEGIN", "START"):
                if not label or label == node_id:
                    kind = "begin"
                elif node_id.upper() in ("END", "STOP"):
                    kind = "end"
            elif shape == "diamond" or node_id.upper() in ("VALID", "CHECK", "DECISION"):
                kind = "decision"
            elif node_id.upper() in ("END", "STOP", "FINISH"):
                kind = "end"

            nodes[node_id] = FlowNode(id=node_id, label=label, kind=kind)

    # Build outgoing edge map
    outgoing: dict[str, list[FlowEdge]] = {}
    for edge in edges:
        if edge.src not in outgoing:
            outgoing[edge.src] = []
        outgoing[edge.src].append(edge)

    # Find begin and end nodes
    begin_ids = [n.id for n in nodes.values() if n.kind == "begin"]
    end_ids = [n.id for n in nodes.values() if n.kind == "end"]

    if not begin_ids:
        begin_ids = [list(nodes.keys())[0]] if nodes else []
    if not end_ids:
        end_ids = [list(nodes.keys())[-1]] if nodes else []

    if len(begin_ids) != 1:
        raise FlowParseError(f"Expected exactly one BEGIN node, found {len(begin_ids)}")
    if len(end_ids) != 1:
        raise FlowParseError(f"Expected exactly one END node, found {len(end_ids)}")

    return Flow(nodes=nodes, outgoing=outgoing, begin_id=begin_ids[0], end_id=end_ids[0])
