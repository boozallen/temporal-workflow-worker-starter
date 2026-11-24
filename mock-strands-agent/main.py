# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Mock Strands Agent for Local Development - A2A JSON-RPC Protocol

This is a JSON-RPC 2.0 server that simulates a Strands agent for local testing
of foundry-temporal-agents integration patterns. It implements the A2A protocol
used by foundry-temporal-agents.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str) -> str:
    """Escape CR/LF so untrusted request data cannot forge or split log lines."""
    return value.replace("\r", "\\r").replace("\n", "\\n")

app = FastAPI(title="Mock Strands Agent - A2A Protocol", version="1.0.0")


# A2A JSON-RPC Protocol Models
class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: dict[str, Any]
    id: int


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Any | None = None
    error: dict[str, Any] | None = None
    id: int


# Mock response templates
MOCK_RESPONSES = {
    "greeting": {
        "en": "Hello {name}! Welcome to our advanced workflow system powered by AI.",
        "es": "¡Hola {name}! Bienvenido a nuestro sistema de flujos de trabajo avanzado impulsado por IA.",
        "fr": "Bonjour {name}! Bienvenue dans notre système de workflows avancé alimenté par l'IA.",
    },
    "research": "Based on my analysis of the provided context, here are the key findings: {analysis}",
    "default": "I have processed your request: '{prompt}'. This is a mock response for local development.",
}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent": "mock-strands-agent",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/agent/capabilities")
async def get_capabilities():
    """Mock agent capabilities endpoint"""
    return {
        "agent_name": "mock-strands-agent",
        "version": "1.0.0",
        "capabilities": [
            "greeting_generation",
            "research_analysis",
            "general_assistance",
        ],
        "supported_languages": ["en", "es", "fr"],
        "max_context_length": 4000,
        "streaming_supported": False,
    }


@app.post("/")
async def handle_jsonrpc_request(request: Request) -> JSONResponse:
    """
    A2A JSON-RPC 2.0 endpoint that handles foundry-temporal-agents requests.

    This endpoint implements the A2A protocol used by foundry-temporal-agents:
    - Receives JSON-RPC 2.0 requests
    - Parses message content from params.message.parts[0].text
    - Returns JSON-RPC 2.0 responses
    """
    try:
        # Parse JSON-RPC request
        body = await request.json()
        logger.info(
            f"Received JSON-RPC request: {_sanitize_for_log(json.dumps(body))}"
        )

        # Validate JSON-RPC structure
        if body.get("jsonrpc") != "2.0":
            return _create_error_response(
                -32600, "Invalid Request - not JSON-RPC 2.0", body.get("id")
            )

        if body.get("method") != "message/send":
            return _create_error_response(
                -32601, f"Method not found: {body.get('method')}", body.get("id")
            )

        # Extract message content from A2A protocol structure
        params = body.get("params", {})
        message = params.get("message", {})
        parts = message.get("parts", [])

        if not parts or not parts[0].get("text"):
            return _create_error_response(
                -32602, "Invalid params - missing message text", body.get("id")
            )

        # Get the actual task message
        task_message = parts[0]["text"]
        session_id = params.get("sessionId")

        logger.info(f"Processing task: {_sanitize_for_log(task_message[:100])}...")

        # Simulate processing time (30s to exercise periodic heartbeats in the activity)
        await asyncio.sleep(30)

        # Generate response based on task content
        result = await _generate_mock_response(task_message, session_id)

        # Return JSON-RPC 2.0 success response
        response = JsonRpcResponse(result=result, id=body.get("id"))

        logger.info(f"Generated response: {_sanitize_for_log(result[:100])}...")
        return JSONResponse(content=response.dict())

    except json.JSONDecodeError:
        return _create_error_response(-32700, "Parse error", None)
    except Exception as e:
        logger.error(f"Error processing JSON-RPC request: {e}")
        return _create_error_response(
            -32603,
            f"Internal error: {str(e)}",
            body.get("id") if "body" in locals() else None,
        )


async def _generate_mock_response(
    task_message: str, session_id: str | None = None
) -> str:
    """Generate mock response based on task content."""
    task_lower = task_message.lower()

    # Try to extract context from task message JSON if present
    context = {}
    try:
        # Look for JSON in the message (foundry often includes extra data)
        if "extra data:" in task_lower:
            json_start = task_message.find("{")
            if json_start != -1:
                json_part = task_message[json_start:]
                json_end = json_part.find("}")
                if json_end != -1:
                    context = json.loads(json_part[: json_end + 1])
    except:
        pass  # Ignore JSON parsing errors

    if "greeting" in task_lower or "hello" in task_lower:
        # Handle greeting requests
        name = context.get("user_name", "User")
        language = context.get("language", "en")

        template = MOCK_RESPONSES["greeting"].get(
            language, MOCK_RESPONSES["greeting"]["en"]
        )
        return template.format(name=name)

    elif "research" in task_lower or "analyze" in task_lower:
        # Handle research requests
        analysis = "The provided data shows positive trends with 95% confidence. Key metrics indicate successful implementation."
        return MOCK_RESPONSES["research"].format(analysis=analysis)

    else:
        # Default response
        return MOCK_RESPONSES["default"].format(prompt=task_message[:100])


def _create_error_response(
    code: int, message: str, request_id: int | None
) -> JSONResponse:
    """Create JSON-RPC 2.0 error response."""
    response = JsonRpcResponse(error={"code": code, "message": message}, id=request_id)
    return JSONResponse(content=response.dict())


@app.post("/agent/stream")
async def stream_agent_request(request: Request):
    """Mock streaming endpoint (not implemented for simplicity)"""
    return _create_error_response(
        -32601, "Streaming not implemented in mock agent", None
    )


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Mock Strands Agent server with A2A JSON-RPC 2.0 protocol...")
    logger.info("Ready to handle foundry-temporal-agents requests")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
