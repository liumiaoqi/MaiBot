"""Flow runner for executing flow-type skills.

This module provides FlowRunner for executing flowchart-based skills
node by node, similar to kimi-cli's implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentlite.agent import Agent
    from agentlite.skills.models import Flow, FlowEdge, FlowNode


class FlowExecutionError(Exception):
    """Raised when flow execution fails."""

    pass


class FlowRunner:
    """Executes flowchart-based skills.

    FlowRunner executes a flowchart node by node, handling task nodes
    and decision nodes appropriately.

    For task nodes: Executes the node's label as a prompt
    For decision nodes: Presents options and waits for user/agent choice

    Example:
        >>> from agentlite.skills.models import Flow, FlowNode, FlowEdge
        >>> # Define a simple flow
        >>> flow = Flow(
        ...     nodes={
        ...         "start": FlowNode(id="start", label="Start", kind="begin"),
        ...         "task": FlowNode(id="task", label="Analyze code", kind="task"),
        ...         "end": FlowNode(id="end", label="End", kind="end"),
        ...     },
        ...     outgoing={
        ...         "start": [FlowEdge(src="start", dst="task")],
        ...         "task": [FlowEdge(src="task", dst="end")],
        ...     },
        ...     begin_id="start",
        ...     end_id="end",
        ... )
        >>> runner = FlowRunner(flow, "my-flow")
        >>> output = await runner.run(agent, "Additional context")
    """

    def __init__(self, flow: "Flow", name: str = "flow"):
        """Initialize the flow runner.

        Args:
            flow: The flowchart to execute
            name: Name of the flow (for logging/debugging)
        """
        self._flow = flow
        self._name = name

    async def run(self, agent: "Agent", args: str = "") -> str:
        """Execute the flow.

        Args:
            agent: The agent to use for executing task nodes
            args: Additional arguments/context for the flow

        Returns:
            The combined output from all executed nodes

        Raises:
            FlowExecutionError: If execution fails
        """
        current_id = self._flow.begin_id
        outputs: list[str] = []
        steps = 0
        max_steps = 100  # Prevent infinite loops

        while steps < max_steps:
            steps += 1

            node = self._flow.nodes.get(current_id)
            if node is None:
                raise FlowExecutionError(f"Node '{current_id}' not found in flow")

            # Get outgoing edges
            edges = self._flow.outgoing.get(current_id, [])

            # Handle different node types
            if node.kind == "end":
                # Flow complete
                break

            elif node.kind == "begin":
                # Just move to next node
                if not edges:
                    raise FlowExecutionError("BEGIN node has no outgoing edges")
                current_id = edges[0].dst
                continue

            elif node.kind == "task":
                # Execute task
                output = await self._execute_task_node(agent, node, args)
                if output:
                    outputs.append(output)

                # Move to next node
                if not edges:
                    raise FlowExecutionError(f"Task node '{current_id}' has no outgoing edges")
                current_id = edges[0].dst

            elif node.kind == "decision":
                # Handle decision
                choice = await self._execute_decision_node(agent, node, edges, args)

                # Find the edge matching the choice
                next_id = None
                for edge in edges:
                    if edge.label and edge.label.lower() == choice.lower():
                        next_id = edge.dst
                        break

                if next_id is None:
                    raise FlowExecutionError(
                        f"Invalid choice '{choice}' for decision node '{current_id}'"
                    )

                current_id = next_id

            else:
                raise FlowExecutionError(f"Unknown node kind: {node.kind}")

        if steps >= max_steps:
            raise FlowExecutionError("Flow exceeded maximum steps (possible infinite loop)")

        return "\n\n".join(outputs)

    async def _execute_task_node(self, agent: "Agent", node: "FlowNode", args: str) -> str:
        """Execute a task node.

        Args:
            agent: The agent to use
            node: The task node
            args: Additional arguments

        Returns:
            The task output
        """
        # Build prompt from node label and args
        prompt = node.label
        if args.strip():
            prompt = f"{prompt}\n\nContext: {args.strip()}"

        # Execute using agent
        response = await agent.run(prompt)
        return response

    async def _execute_decision_node(
        self, agent: "Agent", node: "FlowNode", edges: list["FlowEdge"], args: str
    ) -> str:
        """Execute a decision node.

        Args:
            agent: The agent to use
            node: The decision node
            edges: Available outgoing edges (choices)
            args: Additional arguments

        Returns:
            The chosen option
        """
        # Build prompt with choices
        choices = [edge.label for edge in edges if edge.label]

        prompt_lines = [
            node.label,
            "",
            "Available options:",
            *[f"- {choice}" for choice in choices],
            "",
            "Reply with one of the options above.",
        ]

        if args.strip():
            prompt_lines.extend(["", f"Context: {args.strip()}"])

        prompt = "\n".join(prompt_lines)

        # Get choice from agent
        response = await agent.run(prompt)

        # Extract choice from response (find matching option)
        response_clean = response.strip().lower()
        for choice in choices:
            if choice.lower() in response_clean or response_clean in choice.lower():
                return choice

        # If no exact match, return the first choice as default
        # (or could raise an error)
        return choices[0] if choices else ""
