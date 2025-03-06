# main.py - Integrated backend with new trading agent
import subprocess
import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Union
from uuid import uuid4

from fastapi.openapi.utils import get_openapi

# --- FIX: Add project root to PYTHONPATH ---
# Get the absolute path to the project root directory
# project_root = os.path.dirname(os.path.abspath(__file__))
# Add the project root to sys.path
# sys.path.insert(0, project_root)
# --- CORRECT Path Fix ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
# --- END Path Fix ---
# os.chdir(os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from agents.dex_api_client.public_data import get_binance_tickers
from backend.message_structure import MessageStructure
import motor.motor_asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure agent module is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Google Cloud Configuration ---
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
SERVICE_ACCOUNT_FILE = os.path.abspath("./gemini_defi_agent.json")
LOCATION = os.getenv("LOCATION", "us-central1")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")

# --- API Keys ---
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# OKX Web3 credentials
OKX_WEB3_PROJECT_ID = os.getenv("OKX_WEB3_PROJECT_ID")
OKX_WEB3_PROJECT_KEY = os.getenv("OKX_WEB3_PROJECT_KEY")
OKX_WEB3_PROJECT_SECRET = os.getenv("OKX_WEB3_PROJECT_SECRET")
OKX_WEB3_PROJECT_PASSWRD = os.getenv("OKX_WEB3_PROJECT_PASSWRD")

# MongoDB configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
print(f"MongoDB URL: {str(MONGODB_URL)[:10]}...{str(MONGODB_URL)[5:]}")
DATABASE_NAME = os.getenv("DATABASE_NAME", "trading_assistant")

print(f"Using model: {MODEL} in {LOCATION}")
print(f"MongoDB URL: {MONGODB_URL}, Database: {DATABASE_NAME}")

# Import your trading agent classes and tools
from agents.trade_bot_agent import (
    TradingAssistantDeps, trading_agent, TokenInfo, TradingAnalysis, ThinkingStep, okx_client, third_party_client
)
from agents.dex_api_client.okx_web3_client import OkxWeb3Client
from agents.dex_api_client.third_client import ThirdPartyClient


# Define this since we're importing from the new file
async def initialize_clients():
    from agents.trade_bot_agent import initialize_clients as init
    await init()


# Define run_trading_analysis if not present in the new agent
async def run_trading_analysis(query, deps):
    return await trading_agent.run(query, deps=deps)


okx_client_server: OkxWeb3Client = None
third_party_client_server: ThirdPartyClient = None


# --- Initialize database indexes ---
# @app.on_event("startup")
# async def create_indexes():
#     """Create database indexes"""
#     try:
#         await db.users.create_index("wallet_address", unique=True)
#         await db.conversations.create_index("wallet_address")
#         # Multisig_whitelists index (if used)
#         await db.multisig_whitelists.create_index("multisig_address")
#         logger.info("Database indexes created successfully")
#
#         # Initialize API clients
#         await initialize_clients()
#         logger.info("API clients initialized successfully")
#     except Exception as e:
#         logger.error(f"Error creating database indexes: {e}")

# use lifespan instead

# --- FastAPI App Configuration ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database indexes
    global okx_client_server, third_party_client_server, db
    try:
        await db.users.create_index("wallet_address", unique=True)
        await db.conversations.create_index("wallet_address")
        # Multisig_whitelists index (if used)
        await db.multisig_whitelists.create_index("multisig_address")
        logger.info("Database indexes created successfully")

        # Initialize API clients
        await initialize_clients()
        logger.info("API clients initialized successfully")
    except Exception as e:
        logger.error(f"Error creating database indexes: {e}")

    # Initialize the OKX client
    okx_client_server = OkxWeb3Client(
        project_id=OKX_WEB3_PROJECT_ID,
        api_key=OKX_WEB3_PROJECT_KEY,
        api_secret=OKX_WEB3_PROJECT_SECRET,
        api_passphrase=OKX_WEB3_PROJECT_PASSWRD,
    )
    await okx_client_server.initialize()
    logger.info("OKX client initialized successfully")

    # Initialize the third-party client
    third_party_client_server = ThirdPartyClient()
    await third_party_client_server.initialize()
    logger.info("Third-party client initialized successfully")

    print(f"App started at {datetime.now()}")

    yield

    print(f"App stopped at {datetime.now()}")

def get_git_version():
    try:
        # 執行 git describe 命令，並捕獲輸出
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            stderr=subprocess.STDOUT, # 將錯誤輸出合併到標準輸出
            text=True  # 以文字模式處理輸出
        ).strip()
        return version
    except subprocess.CalledProcessError:
        return "0.0.0"  # 如果 git 命令失敗，返回預設版本

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Trading Assistant API",
        version=get_git_version(),
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


# Create FastAPI app
app = FastAPI(title="Trading Assistant API", version="0.1", lifespan=lifespan)

origins = [
    "https://gun-ai-wallet.onrender.com",  # 你的前端網址
    "http://localhost:8000",             # 如果你在本地開發前端，也可能需要這個
    "http://localhost:3000",             # 如果你的前端在 3000 埠運行
    "http://127.0.0.1:8026",  # 如果你在本地開發前端，也可能需要這個
    "http://127.0.0.1:3000",  # 如果你的前端在 3000 埠運行
    "http://localhost:7788",             # 如果你在本地開發前端，也可能需要這個
    "http://127.0.0.1:7788",  # 如果你在本地開發前端，也可能需要這個
]

app.openapi = custom_openapi


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Create MongoDB client
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]


# --- Data Models ---
class User(BaseModel):
    wallet_address: str
    created_at: datetime = Field(default_factory=datetime.now)
    has_agent: bool = False
    multisig_address: Optional[str] = None


class Message(BaseModel):
    id: str
    sender: str
    text: Union[str, dict]
    message_type: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Conversation(BaseModel):
    wallet_address: str
    messages: List[Message] = []


# --- Helper Functions ---
def _serialize_for_mongo(data: Any) -> Any:
    """Recursively serializes data to be compatible with MongoDB."""
    if isinstance(data, BaseModel):
        return data.dict()
    elif isinstance(data, list):
        return [_serialize_for_mongo(item) for item in data]
    elif isinstance(data, dict):
        return {key: _serialize_for_mongo(value) for key, value in data.items()}
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data


def _deserialize_from_mongo(data: Any) -> Any:
    """Recursively deserializes data retrieved from MongoDB."""
    if isinstance(data, list):
        return [_deserialize_from_mongo(item) for item in data]
    elif isinstance(data, dict):
        # Attempt to reconstruct Pydantic models
        if "symbol" in data and "blockchain" in data and all(
                key in data for key in ["contract_address", "project_url"]):
            try:
                return TokenInfo(**data)
            except:
                pass
        if "phase" in data and "question" in data and "answer" in data:
            try:
                return ThinkingStep(**data)
            except:
                pass
        if "source_token" in data and "target_token" in data and "security_analysis" in data:
            try:
                return TradingAnalysis(**data)
            except:
                pass

        return {key: _deserialize_from_mongo(value) for key, value in data.items()}
    elif isinstance(data, str):
        try:
            return datetime.fromisoformat(data)
        except ValueError:
            return data
    else:
        return data


# --- Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_sessions: Dict[str, Dict[str, Any]] = {}

    async def connect(self, wallet_address: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[wallet_address] = websocket
        self.user_sessions[wallet_address] = {
            "last_message_time": datetime.now(),
            "agent_busy": False
        }
        logger.info(f"WebSocket connection established for {wallet_address}")

    def disconnect(self, wallet_address: str):
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]
        if wallet_address in self.user_sessions:
            del self.user_sessions[wallet_address]
        logger.info(f"WebSocket connection closed for {wallet_address}")

    async def send_message(self, wallet_address: str, message: Dict[str, Any]):
        """Send a message to a specific user"""
        if wallet_address in self.active_connections:
            websocket = self.active_connections[wallet_address]
            try:
                await websocket.send_json(message)
                logger.debug(f"Message sent to {wallet_address}: {message.get('id', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending message to {wallet_address}: {e}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected users"""
        for wallet_address in self.active_connections:
            await self.send_message(wallet_address, message)

    async def update_status(self, wallet_address: str, status: str):
        """Update and send a status message"""
        status_message = MessageStructure.format_status(status)

        await self.send_message(wallet_address, status_message)
        await save_message(wallet_address, status_message)

    def set_agent_busy(self, wallet_address: str, busy: bool):
        """Set whether the user's agent is busy processing a request"""
        if wallet_address in self.user_sessions:
            self.user_sessions[wallet_address]["agent_busy"] = busy
            logger.info(f"Agent for {wallet_address} set to {'busy' if busy else 'available'}")

    def is_agent_busy(self, wallet_address: str) -> bool:
        """Check if the user's agent is busy processing a request"""
        if wallet_address in self.user_sessions:
            return self.user_sessions[wallet_address]["agent_busy"]
        return False


# Create connection manager instance
manager = ConnectionManager()


# --- Database Functions ---
async def get_user(wallet_address: str) -> Optional[Dict[str, Any]]:
    """Get a user by wallet address"""
    user = await db.users.find_one({"wallet_address": wallet_address})
    return _deserialize_from_mongo(user) if user else None


async def create_user(wallet_address: str) -> Dict[str, Any]:
    """Create a new user"""
    user = User(wallet_address=wallet_address)
    user_dict = _serialize_for_mongo(user)
    await db.users.insert_one(user_dict)
    return user_dict


async def set_has_agent(wallet_address: str, has_agent: bool) -> bool:
    """Set whether the user has an agent"""
    result = await db.users.update_one(
        {"wallet_address": wallet_address},
        {"$set": {"has_agent": has_agent}}
    )
    return result.modified_count > 0


async def save_message(wallet_address: str, message_in: Dict[str, Any]) -> bool:
    """Save a message to the database"""
    message = _serialize_for_mongo(message_in)
    message["id"] = message.get("id", str(uuid4()))
    message["message_type"] = message.get("message_type", "normal")
    message["timestamp"] = message.get("timestamp", datetime.now().isoformat())

    if isinstance(message["timestamp"], datetime):
        message["timestamp"] = message["timestamp"].isoformat()

    result = await db.conversations.update_one(
        {"wallet_address": wallet_address},
        {"$push": {"messages": message}},
        upsert=True
    )
    return result.modified_count > 0 or result.upserted_id is not None


async def get_messages(wallet_address: str, show_history: bool = False) -> List[Dict[str, Any]]:
    """
    Get a user's message history.

    Args:
        wallet_address: The user's wallet address.
        show_history: Whether to show the complete history. Default is False, showing only the most recent final result.

    Returns:
        A list of messages.
    """
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        messages = _deserialize_from_mongo(conversation["messages"])
        if show_history:
            # Return all non-"thinking" type messages
            return [msg for msg in messages if msg.get("message_type") != "thinking"]
        else:
            # Only return the most recent final result (normal type, and not a tool_call)
            for msg in reversed(messages):
                if msg.get("message_type") == "normal":
                    return [msg]
            return []  # If none found, return empty list
    return []


async def get_previous_messages(wallet_address: str) -> List[Dict[str, Any]]:
    """Get previous conversation messages from the database"""
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        # Exclude 'status' type messages, as they're just status updates and don't affect conversation context
        return [
            _deserialize_from_mongo(msg)
            for msg in conversation["messages"]
            if msg.get("message_type") != "status"
        ]
    return []


async def deploy_multisig_wallet(wallet_address: str) -> str:
    """
    Simulate deploying a 2/2 multisig wallet contract.

    Args:
        wallet_address: The user's wallet address.

    Returns:
        A simulated multisig wallet contract address.
    """
    # In a real app, this would call blockchain code to deploy a contract
    # This is just a simulation, generating a unique contract address
    multisig_address = f"0xms{uuid4().hex}"

    # Update user information, save the multisig wallet address
    await db.users.update_one(
        {"wallet_address": wallet_address},
        {"$set": {"multisig_address": multisig_address}}
    )
    return multisig_address


async def add_token_to_whitelist(multisig_address: str, token_address: str) -> bool:
    """
    Simulate adding a token to the multisig wallet's whitelist.

    Args:
        multisig_address: The multisig wallet address.
        token_address: The token contract address to add.

    Returns:
        True if added successfully, False if failed
    """
    # In a real app, this would call the multisig contract's method
    # This is just a simulation
    logger.info(f"Adding {token_address} to whitelist of {multisig_address}")
    # Assume a collection named multisig_whitelists, adjust based on your contract design
    await db.multisig_whitelists.update_one(
        {"multisig_address": multisig_address},
        {"$addToSet": {"whitelisted_tokens": token_address}},
        upsert=True,
    )
    return True


async def clarify_with_user(wallet_address: str, question: str) -> None:
    """Send a clarification question to the user and save the message"""
    clarification_message = MessageStructure.format_ai_response({
        "recommendation": question,
        "message_type": "clarification"
    })
    await save_message(wallet_address, clarification_message)
    await manager.send_message(wallet_address, clarification_message)


# --- Message Processing Helper Function ---
async def process_message(wallet_address: str, query: str) -> Dict[str, Any]:
    """Process a user message and return the AI Agent's response"""

    # Create dependencies
    deps = TradingAssistantDeps(
        request={"wallet_address": wallet_address},  # Pass wallet_address in request
        update_status_func=lambda req, status: manager.update_status(wallet_address, status),
        send_message_func=lambda req, message: manager.send_message(wallet_address, message),
        agent_name="trading_agent"
    )

    # Set Agent status to busy
    manager.set_agent_busy(wallet_address, True)
    try:
        # 1. Load history messages
        previous_messages = await get_previous_messages(wallet_address)
        previous_messages_text = "\n".join(
            [f"{msg['sender']}: {msg['text']}" for msg in previous_messages]
        )

        # 2. Combine history messages and current query
        full_query = f"{previous_messages_text}\nUser: {query}"

        # 3. Run trading analysis
        result = await run_trading_analysis(full_query, deps)

        if isinstance(result, Exception):
            return {"error": str(result)}

        # Return Pydantic model as dict
        return {"result": result.dict() if hasattr(result, "dict") else result}

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        return {"error": str(e)}
    finally:
        # Set Agent status to idle
        manager.set_agent_busy(wallet_address, False)


# --- WebSocket Route ---
@app.websocket("/ws/{address}")
async def websocket_endpoint(websocket: WebSocket, address: str):
    """WebSocket handler function"""
    wallet_address = address.lower()
    logger.info(f"New WebSocket connection from: {wallet_address}")
    await manager.connect(wallet_address, websocket)

    user = await get_user(wallet_address)
    if not user:
        user = await create_user(wallet_address)

    try:
        # Use MessageStructure for welcome message
        welcome_message = MessageStructure.format_ai_response({
            "recommendation": "Hello! I'm your AI Trading Assistant. How can I help you today?"
        })
        await save_message(wallet_address, welcome_message)
        await manager.send_message(wallet_address, welcome_message)

        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from {wallet_address}: {data}")
            try:
                data_json = json.loads(data)
                query = data_json.get("query")
                if not query:
                    raise ValueError("Missing 'query' field")

            except (json.JSONDecodeError, ValueError) as e:
                await manager.send_message(wallet_address, MessageStructure.format_error(str(e)))
                continue

            # Format user message
            user_message = {
                "id": str(uuid4()),
                "sender": "user",
                "text": query,
                "message_type": "normal",
                "timestamp": datetime.now().isoformat()
            }

            await save_message(wallet_address, user_message)

            if manager.is_agent_busy(wallet_address):
                await manager.send_message(wallet_address, MessageStructure.format_error(
                    "Agent is busy. Please wait."
                ))
                continue

            asyncio.create_task(process_and_reply(wallet_address, query))

    except WebSocketDisconnect:
        manager.disconnect(wallet_address)
    except Exception as e:
        logger.exception(f"Error in WebSocket connection: {e}")
        await manager.send_message(
            wallet_address,
            MessageStructure.format_error(f"An unexpected error occurred: {str(e)}")
        )
        manager.disconnect(wallet_address)


async def process_and_reply(wallet_address: str, query: str):
    """Asynchronously process the message and send step-by-step replies"""
    try:
        result = await process_message(wallet_address, query)
        logger.info(f"Result from process_message: {result}")

        if "error" in result:
            error_message = MessageStructure.format_error(result["error"])
            await save_message(wallet_address, error_message)
            await manager.send_message(wallet_address, error_message)
            return

        analysis_result = result["result"]
        logger.info(f"Analysis result: {analysis_result}")

        # Handle AgentRunResult object correctly - extract the data attribute which contains TradingAnalysis
        if hasattr(analysis_result, 'data'):
            trading_analysis = analysis_result.data
        else:
            # If it's already a TradingAnalysis object (or dict)
            trading_analysis = analysis_result

        # Now access attributes on the TradingAnalysis object (not dict subscripting)
        agent_message = MessageStructure.format_ai_response(trading_analysis)

        # Set action based on the safe_to_execute attribute
        if hasattr(trading_analysis, 'safe_to_execute'):
            safe_to_execute = trading_analysis.safe_to_execute
            if safe_to_execute:
                # Check if there are any "clarification" type messages in thinking_steps
                needs_clarification = False
                if hasattr(trading_analysis, 'thinking_steps'):
                    needs_clarification = any(
                        getattr(step, 'message_type', '') == "clarification"
                        for step in trading_analysis.thinking_steps
                    )

                if not needs_clarification:
                    # Execute transaction if safe
                    await handle_ai_transaction(wallet_address, {
                        "safe_to_execute": safe_to_execute,
                        "source_token": getattr(trading_analysis.source_token, 'symbol', 'UNKNOWN'),
                        "target_token": getattr(trading_analysis.target_token, 'symbol', 'UNKNOWN'),
                        "thinking_steps": [step.__dict__ if hasattr(step, '__dict__') else step
                                           for step in getattr(trading_analysis, 'thinking_steps', [])]
                    })

        await save_message(wallet_address, agent_message)
        await manager.send_message(wallet_address, agent_message)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        error_message = MessageStructure.format_error(f"An error occurred: {str(e)}")
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)


async def handle_ai_transaction(wallet_address: str, analysis_result: dict):
    """AI transaction handling process"""
    logger.info(f"Handling AI transaction with: {analysis_result}")
    user = await get_user(wallet_address)
    if not user or not user.get("multisig_address"):
        error_message = MessageStructure.format_error(
            "Multisig wallet not deployed. Please deploy a multisig wallet first."
        )
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)
        return

    try:
        # Get token information from analysis result
        source_token = analysis_result.get("source_token", "Unknown")
        target_token = analysis_result.get("target_token", "Unknown")

        # Send status update
        await manager.update_status(wallet_address, "AI is preparing to execute the transaction...")

        # Simulate transaction preparation stage
        await asyncio.sleep(1)  # Simulate delay

        # 1. AI approves transaction (message)
        approval_message = MessageStructure.format_transaction(
            text=f"I'm approving the exchange of {source_token} for {target_token}...",
            status="pending"
        )
        await save_message(wallet_address, approval_message)
        await manager.send_message(wallet_address, approval_message)
        await asyncio.sleep(1.5)

        # 2. AI signs transaction (message)
        signing_message = MessageStructure.format_transaction(
            text=f"Now signing the transaction with my multisig key...",
            status="pending"
        )
        await save_message(wallet_address, signing_message)
        await manager.send_message(wallet_address, signing_message)
        await asyncio.sleep(1.5)

        # 3. Extract tx_hash from thinking_steps
        tx_hash = None
        for step in analysis_result.get('thinking_steps', []):
            if isinstance(step, dict) and step.get('question') == 'Approve transaction details':
                answer = step.get('answer', {})
                if isinstance(answer, dict):
                    tx_hash = answer.get('tx_hash')
                break

        if not tx_hash:
            # If not found, generate a simulated one
            logger.warning("Transaction hash (tx_hash) not found in thinking steps.")
            tx_hash = "0x" + uuid4().hex

        # 4. Simulate sending transaction to blockchain
        submitting_message = MessageStructure.format_transaction(
            text=f"Transaction submitted to blockchain. Transaction hash: {tx_hash}",
            status="completed",
            action={
                "type": "submitted",
                "tx_hash": tx_hash
            }
        )
        await save_message(wallet_address, submitting_message)
        await manager.send_message(wallet_address, submitting_message)

    except Exception as e:
        logger.exception(f"Error during AI transaction processing: {e}")
        error_message = MessageStructure.format_error(f"Transaction processing failed: {str(e)}")
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)


# --- API Routes ---
@app.post("/api/agent")
async def create_agent(wallet_address: str):
    """
    Create an Agent record (without deploying a multisig wallet).
    """
    wallet_address = wallet_address.lower()
    user = await get_user(wallet_address)
    if not user:
        user = await create_user(wallet_address)

    await set_has_agent(wallet_address, True)
    return {"success": True, "message": "Agent created successfully."}


@app.get("/api/agent-status/{wallet_address}")
async def get_agent_status(wallet_address: str):
    """
    Check a user's Agent status.
    """
    wallet_address = wallet_address.lower()
    user = await get_user(wallet_address)
    if user:
        return {
            "has_agent": user.get("has_agent", False),
            "multisig_address": user.get("multisig_address"),
        }
    else:
        return {"has_agent": False, "multisig_address": None}


@app.post("/api/deploy-multisig")
async def deploy_multisig(wallet_address: str):
    """
    Deploy a multisig wallet (simulation).
    """
    wallet_address = wallet_address.lower()
    user = await get_user(wallet_address)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("multisig_address"):
        raise HTTPException(
            status_code=400, detail="Multisig wallet already deployed for this user"
        )

    multisig_address = await deploy_multisig_wallet(wallet_address)
    return {
        "success": True,
        "message": "Multisig wallet deployed successfully",
        "multisig_address": multisig_address,
    }


@app.get("/api/messages")
async def get_user_messages(wallet_address: str, show_history: bool = Query(False)):
    """Get user messages API, with option to include thinking process"""
    wallet_address = wallet_address.lower()
    messages = await get_messages(wallet_address, show_history)
    return {"messages": messages}


@app.post("/api/user-signature")
async def user_signature(
        wallet_address: str,
        tx_hash: str,
        user_signature: str
):
    """Receive user signature for a transaction"""
    wallet_address = wallet_address.lower()
    logger.info(f"Received user {wallet_address} signature for transaction {tx_hash}")

    # Create transaction completion message
    completion_message = MessageStructure.format_transaction(
        text="Transaction successfully completed! Multisig transaction submitted to blockchain.",
        status="completed",
        action={
            "type": "completed",
            "text": "Transaction completed",
            "data": {
                "tx_hash": tx_hash,
                "user_signature": user_signature,
                "status": "confirmed",
            },
        }
    )

    await save_message(wallet_address, completion_message)

    if wallet_address in manager.active_connections:
        await manager.send_message(wallet_address, completion_message)

    return {
        "success": True,
        "message": "Transaction completed",
        "tx_hash": tx_hash,
        "block_number": 12345678,  # Simulated block number
    }


@app.post("/api/user-reject-transaction")
async def user_reject_transaction(
        wallet_address: str,
        tx_hash: str,
        reason: Optional[str] = "User rejected transaction"
):
    """User transaction rejection"""
    wallet_address = wallet_address.lower()
    logger.info(f"User {wallet_address} rejected transaction {tx_hash}: {reason}")

    rejection_message = MessageStructure.format_transaction(
        text=f"Transaction rejected: {reason}",
        status="error",
        action={
            "type": "rejected",
            "text": "Transaction rejected",
            "data": {
                "tx_hash": tx_hash,
                "reason": reason
            }
        }
    )

    await save_message(wallet_address, rejection_message)

    if wallet_address in manager.active_connections:
        await manager.send_message(wallet_address, rejection_message)

    return {"success": True, "message": "Transaction rejected"}


@app.get("/api/public-data/tickers")
async def get_tickers():
    """Fetch ticker data for multiple symbols from the Binance API."""
    # Fetch data from Binance API
    tickers = await get_binance_tickers([
        "BTCUSDT", "ETHUSDT", "SOLUSDT"
    ])
    return {"tickers": tickers}


class GetWalletDataByChain(BaseModel):
    wallet_address: str
    chain_id_list: Optional[List[str]] = None  # ["1", "56", "137", "8453"]


@app.post("/api/total-balance")
async def get_total_balance(data: GetWalletDataByChain):
    """Get total balance for a wallet address"""
    res = await okx_client_server.get_total_value_by_address(
        data.wallet_address,
        data.chain_id_list
    )
    return res


@app.post("/api/total-balance-detail")
async def get_total_balance(data: GetWalletDataByChain):
    res = await okx_client_server.get_all_token_balances_by_address(
        data.wallet_address,
        data.chain_id_list,
        filter_risk_tokens=True
    )
    if not res['data']:
        return []
    return await okx_client_server.process_token_data(res)


@app.post("/api/wallet-transaction-history")
async def get_wallet_transaction_history(data: GetWalletDataByChain):
    res = await okx_client_server.get_transactions_by_address(
        data.wallet_address,
        data.chain_id_list
    )
    if not res['data']:
        return []
    return await okx_client_server.process_transaction_data(res, data.wallet_address)


# private data
@app.get("/wallet-balance")
async def get_wallet_balance(wallet_address: str, chain_id: str = None):
    """Get wallet balance"""
    return {"wallet_address": wallet_address, "balance": 1000.0}


# 添加檢查用戶 Agent 狀態的端點
@app.get("/api/user-status")
async def check_user_status(wallet_address: str):
    """
    檢查指定錢包地址的用戶是否已有 Agent

    參數:
    - wallet_address: 用戶的錢包地址

    返回:
    - has_agent: 用戶是否已有 Agent
    - multisig_address: 如果有 Agent，返回對應的多簽錢包地址
    """
    try:
        # 連接數據庫並查詢用戶狀態
        # 這裡用您的實際數據庫查詢邏輯替換
        user = await db.users.find_one({"wallet_address": wallet_address.lower()})

        return {
            "has_agent": user.get("has_agent", False),
            "multisig_address": user.get("multisig_address")
        }
    except Exception as e:
        logger.error(f"Error checking user status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check user status")


class CreateAgent(BaseModel):
    wallet_address: str


# 添加創建 Agent 的端點
@app.post("/api/create-agent")
async def create_agent(data: CreateAgent):
    """
    為指定錢包地址的用戶創建一個 AI Agent

    請求體:
    - wallet_address: 用戶的錢包地址

    返回:
    - success: 是否成功創建 Agent
    - message: 結果信息
    - agent_id: 創建的 Agent ID (如果成功)
    """
    try:
        # 解析請求體
        data = data.model_dump()
        wallet_address = data["wallet_address"]

        if not wallet_address:
            raise HTTPException(status_code=400, detail="Wallet address is required")

        # 檢查用戶是否已有 Agent
        user = await db.users.find_one({"wallet_address": wallet_address.lower()})

        if user and user.get("agent_id"):
            # 用戶已有 Agent，返回已存在信息
            return {
                "success": True,
                "message": "Agent already exists",
                "agent_id": user.get("agent_id")
            }

        # 創建新的 Agent
        # 這裡添加您的實際 Agent 創建邏輯
        agent_id = str(uuid.uuid4())  # 生成唯一 ID

        # 創建或更新用戶記錄
        # await db.users.update_one(
        #     {"wallet_address": wallet_address.lower()},
        #     {"$set": {
        #         "agent_id": agent_id,
        #         "has_agent": True,
        #         "created_at": datetime.utcnow(),
        #         "last_active": datetime.utcnow()
        #     }},
        #     upsert=True
        # )
        res = await db.users.find_one_and_update(
            {"wallet_address": wallet_address.lower()},
            {"$set": {
                "agent_id": agent_id,
                "has_agent": True,
                "created_at": datetime.utcnow(),
                "last_active": datetime.utcnow()
            }},
            upsert=True,
            return_document=True
        )

        # 如果需要創建多簽錢包，可以在這裡添加邏輯
        # multisig_address = await create_multisig_wallet(wallet_address)
        # 然後更新數據庫中的 multisig_address 字段

        return {
            "success": True,
            "message": "Agent created successfully",
            "agent_id": agent_id
        }
    except HTTPException as http_exc:
        # 重新拋出 HTTP 異常
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create agent")


# --- Health check endpoint ---
@app.get("/health")
async def health_check():
    """Simple health check API"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# --- Run application ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7788, log_level="info")
