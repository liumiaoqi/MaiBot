"""Example: Custom Tools

This example demonstrates how to define and use custom tools with agents.
"""

import asyncio
import os
from datetime import datetime

from pydantic import BaseModel

from agentlite import Agent, OpenAIProvider, tool
from agentlite.tool import CallableTool2, ToolOk


# Define a tool using the decorator
@tool()
async def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


@tool()
async def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: The mathematical expression to evaluate (e.g., "2 + 2").
    """
    try:
        # Safe evaluation - only allow basic math operations
        allowed_names = {
            "abs": abs,
            "max": max,
            "min": min,
            "pow": pow,
            "round": round,
        }
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


# Define a tool using CallableTool2 (type-safe)
class WeatherParams(BaseModel):
    """Parameters for weather tool."""

    city: str
    units: str = "celsius"


class GetWeather(CallableTool2[WeatherParams]):
    """Get weather information for a city."""

    name = "get_weather"
    description = "Get the current weather for a city."
    params = WeatherParams

    async def __call__(self, params: WeatherParams) -> ToolOk:
        # This is a mock implementation
        # In a real scenario, you would call a weather API
        weather_data = {
            "Beijing": {"temp": 22, "condition": "Sunny"},
            "Shanghai": {"temp": 25, "condition": "Cloudy"},
            "New York": {"temp": 18, "condition": "Rainy"},
            "London": {"temp": 15, "condition": "Overcast"},
        }

        city = params.city
        if city in weather_data:
            data = weather_data[city]
            temp = data["temp"]
            if params.units == "fahrenheit":
                temp = temp * 9 // 5 + 32
            return ToolOk(
                output=f"Weather in {city}: {data['condition']}, {temp}°{params.units[0].upper()}"
            )
        return ToolOk(output=f"Weather data not available for {city}")


async def main():
    """Run the custom tools example."""
    # Create provider
    provider = OpenAIProvider(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        model="gpt-4o-mini",
    )

    # Create agent with tools
    agent = Agent(
        provider=provider,
        system_prompt="You are a helpful assistant with access to tools.",
        tools=[
            get_current_time,
            calculate,
            GetWeather(),
        ],
    )

    # Test tools
    print("=== Testing Tools ===\n")

    print("User: What time is it?")
    response = await agent.run("What time is it?")
    print(f"Agent: {response}\n")

    print("User: What is 123 * 456?")
    response = await agent.run("What is 123 * 456?")
    print(f"Agent: {response}\n")

    print("User: What's the weather in Beijing?")
    response = await agent.run("What's the weather in Beijing?")
    print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
