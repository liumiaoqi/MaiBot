"""Debug script with detailed logging to find CLI test hang cause."""

from __future__ import annotations

import os
import sys
import asyncio
import logging
import time

sys.path.insert(0, "/home/tcmofashi/proj/l2d_backend/agentlite/src")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("debug")

# SiliconFlow DeepSeek-V3 (known good function calling support)
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = "Pro/deepseek-ai/DeepSeek-V3.2"
SILICONFLOW_API_KEY = "sk-eaxfgkkcuatochftxpevkyvltghigsrclzjzalybmaqycual"


async def main():
    from agentlite import Agent, OpenAIProvider
    from agentlite.tools.shell.shell import Shell
    from agentlite.message import Message

    logger.info("=" * 60)
    logger.info("CLI Debug Test with DeepSeek-V3 (SiliconFlow)")
    logger.info("=" * 60)

    api_key = os.environ.get("SILICONFLOW_API_KEY") or SILICONFLOW_API_KEY
    if not api_key:
        logger.error("SILICONFLOW_API_KEY not set")
        return

    logger.info(f"Using model: {SILICONFLOW_MODEL}")

    provider = OpenAIProvider(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
        timeout=30.0,
    )

    agent = Agent(
        provider=provider,
        system_prompt="You are a shell assistant. Execute commands when asked. Reply briefly.",
        tools=[Shell(timeout=10)],
        max_iterations=5,
    )

    start_time = time.time()
    message = "Run 'echo test' and tell me the result."

    logger.info("\n=== Starting Agent Run ===")
    logger.info(f"Message: {message}")
    logger.info(f"Max iterations: {agent.max_iterations}")
    logger.info(f"Tools: {[t.name for t in agent.tools.tools]}")

    agent._history.append(Message(role="user", content=message))

    iterations = 0
    final_response = None

    while iterations < agent.max_iterations:
        iterations += 1
        elapsed = time.time() - start_time

        logger.info(f"\n{'=' * 50}")
        logger.info(f"ITERATION {iterations}/{agent.max_iterations} (elapsed: {elapsed:.1f}s)")
        logger.info(f"{'=' * 50}")

        # Step 1: Call Provider
        logger.info(">>> Step 1: Calling provider.generate()...")
        step_start = time.time()

        try:
            stream = await asyncio.wait_for(
                provider.generate(
                    system_prompt=agent.system_prompt,
                    tools=agent.tools.tools,
                    history=agent._history,
                ),
                timeout=60.0,
            )
            logger.info(f"<<< Provider returned stream in {time.time() - step_start:.2f}s")
        except asyncio.TimeoutError:
            logger.error("!!! Provider call TIMEOUT after 60s")
            final_response = "ERROR: Provider timeout"
            break

        # Step 2: Collect stream parts
        logger.info(">>> Step 2: Collecting stream parts...")
        step_start = time.time()

        from agentlite.message import TextPart, ToolCall, ContentPart

        response_parts = []
        tool_calls = []
        chunk_count = 0

        try:
            async for part in stream:
                chunk_count += 1
                if chunk_count % 10 == 0:
                    logger.debug(f"    Received chunk #{chunk_count}")

                if isinstance(part, ToolCall):
                    tool_calls.append(part)
                    logger.info(
                        f"    ToolCall received: {part.function.name if hasattr(part, 'function') else part}"
                    )
                elif isinstance(part, ContentPart):
                    response_parts.append(part)
                    if isinstance(part, TextPart):
                        logger.debug(f"    Text: {part.text[:50]}...")

            logger.info(
                f"<<< Stream finished in {time.time() - step_start:.2f}s, {chunk_count} chunks"
            )
        except asyncio.TimeoutError:
            logger.error("!!! Stream reading TIMEOUT")
            final_response = "ERROR: Stream timeout"
            break
        except Exception as e:
            logger.error(f"!!! Stream error: {type(e).__name__}: {e}")
            final_response = f"ERROR: Stream error - {e}"
            break

        # Extract text
        response_text = ""
        for part in response_parts:
            if isinstance(part, TextPart):
                response_text += part.text
        logger.info(f"Response text ({len(response_text)} chars): {response_text[:100]}...")
        logger.info(f"Tool calls: {len(tool_calls)}")

        # Add to history
        agent._history.append(
            Message(
                role="assistant",
                content=response_parts,
                tool_calls=tool_calls if tool_calls else None,
            )
        )

        # Step 3: Check if done
        if not tool_calls:
            elapsed = time.time() - start_time
            logger.info(f"\n=== Agent completed in {elapsed:.2f}s, {iterations} iterations ===")
            final_response = response_text
            break

        # Step 4: Execute tool calls
        logger.info(f"\n>>> Step 3: Executing {len(tool_calls)} tool calls...")
        step_start = time.time()

        for i, tc in enumerate(tool_calls):
            func_name = tc.function.name if hasattr(tc, "function") else str(tc)
            func_args = tc.function.arguments if hasattr(tc, "function") else ""
            logger.info(f"    Tool #{i + 1}: {func_name}")
            logger.info(f"    Args: {func_args[:200]}...")

            try:
                result = await asyncio.wait_for(
                    agent.tools.handle(tc),
                    timeout=30.0,
                )
                output = result.output if hasattr(result, "output") else str(result)
                is_error = result.is_error if hasattr(result, "is_error") else False
                logger.info(
                    f"    Result: is_error={is_error}, output_len={len(output) if output else 0}"
                )
                output_preview = output[:100] if output else "None"
                logger.info(f"    Output preview: {output_preview}...")
            except asyncio.TimeoutError:
                logger.error("    !!! Tool execution TIMEOUT")
                output = "Tool execution timed out"
                is_error = True
            except Exception as e:
                logger.error(f"    !!! Tool error: {type(e).__name__}: {e}")
                output = str(e)
                is_error = True

            # Add tool result to history
            agent._history.append(
                Message(
                    role="tool",
                    content=output,
                    tool_call_id=tc.id if hasattr(tc, "id") else f"tc_{i}",
                )
            )

        logger.info(f"<<< Tool execution finished in {time.time() - step_start:.2f}s")

        # Check overall timeout
        elapsed = time.time() - start_time
        if elapsed > 90:
            logger.warning(f"!!! Overall timeout approaching ({elapsed:.1f}s)")
            final_response = f"Timeout after {iterations} iterations"
            break

    if iterations >= agent.max_iterations:
        logger.warning(f"!!! Max iterations reached ({agent.max_iterations})")
        final_response = f"Max iterations ({agent.max_iterations}) reached"

    logger.info(f"\n{'=' * 60}")
    logger.info("FINAL RESULT:")
    logger.info(f"{'=' * 60}")
    logger.info(f"{final_response}")
    logger.info(f"Total iterations: {iterations}")
    logger.info(f"Total time: {time.time() - start_time:.2f}s")
    logger.info(f"History length: {len(agent._history)}")


if __name__ == "__main__":
    asyncio.run(main())
