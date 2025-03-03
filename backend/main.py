# backend/main.py
# Trading Assistant using Google's Gemini API with Chain of Thought

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

import motor.motor_asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field  # Import Field
import uvicorn

# 确保代理目录可在系统路径中找到
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trading_assistant import (
    TradingAssistantDeps,
    run_trading_analysis,
    ThinkingStep,
    TokenInfo,
    TradingAnalysis,
    trading_agent,
    approve_transaction,
    sign_transaction,
    fetch_token_information,
    analyze_contract_security,
    check_liquidity,
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 环境变量配置
# 使用默認值 (for debugging only!)
PROJECT_ID = os.environ.get("GOOGLE_PROJECT_ID", "your-project-id")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/your/credentials.json")
MODEL = "gemini-2.0-flash"
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", "your-search-api-key")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "your-cse-id")
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "trading_assistant")
print(PROJECT_ID, SERVICE_ACCOUNT_FILE, MODEL, GOOGLE_SEARCH_API_KEY, GOOGLE_CSE_ID, MONGODB_URL, DATABASE_NAME)

# 创建FastAPI应用
app = FastAPI(title="Trading Assistant API")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源（生产环境中应该限制）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建MongoDB客户端
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]


# 数据模型
class User(BaseModel):
    wallet_address: str
    created_at: datetime = datetime.now()
    has_agent: bool = False
    multisig_address: Optional[str] = None  # 新增：多签钱包地址


class Message(BaseModel):
    id: str
    sender: str
    text: str | dict
    message_type: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())  # Store as ISO string
    action: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),  # Serialize datetime to ISO string
        }


class Conversation(BaseModel):
    wallet_address: str
    messages: List[Message] = []


# --- Helper Functions ---

def _serialize_for_mongo(data: Any) -> Any:
    """
    Recursively serializes data to be compatible with MongoDB.
    """
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
    """
    Recursively deserializes data retrieved from MongoDB.
    """
    if isinstance(data, list):
        return [_deserialize_from_mongo(item) for item in data]
    elif isinstance(data, dict):
        # Attempt to reconstruct Pydantic models
        if "symbol" in data and "blockchain" in data and "contract_address" in data and "project_url" in data:
            try:
                return TokenInfo(**data)
            except:
                pass
        if "question" in data and "answer" in data:
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


# 活跃WebSocket连接管理
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

    def disconnect(self, wallet_address: str):
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]
        if wallet_address in self.user_sessions:
            del self.user_sessions[wallet_address]

    async def send_message(self, wallet_address: str, message: Dict[str, Any]):
        """向特定用户发送消息"""
        if wallet_address in self.active_connections:
            websocket = self.active_connections[wallet_address]
            await websocket.send_json(message)

    async def broadcast(self, message: Dict[str, Any]):
        """向所有连接的用户广播消息"""
        for wallet_address in self.active_connections:
            await self.send_message(wallet_address, message)

    async def update_status(self, wallet_address: str, status: str):
        """更新并发送状态消息"""
        status_message = {
            "id": f"status-{uuid4()}",
            "sender": "agent",
            "text": status,
            "message_type": "status",
            "timestamp": datetime.now().isoformat()
        }

        await self.send_message(wallet_address, status_message)
        await save_message(wallet_address, status_message)

    def set_agent_busy(self, wallet_address: str, busy: bool):
        """设置用户的Agent是否正在处理请求"""
        if wallet_address in self.user_sessions:
            self.user_sessions[wallet_address]["agent_busy"] = busy

    def is_agent_busy(self, wallet_address: str) -> bool:
        """检查用户的Agent是否正在处理请求"""
        if wallet_address in self.user_sessions:
            return self.user_sessions[wallet_address]["agent_busy"]
        return False


# 创建连接管理器实例
manager = ConnectionManager()


# 数据库操作函数
async def get_user(wallet_address: str) -> Optional[Dict[str, Any]]:
    """根据钱包地址获取用户"""
    user = await db.users.find_one({"wallet_address": wallet_address})
    return _deserialize_from_mongo(user) if user else None


async def create_user(wallet_address: str) -> Dict[str, Any]:
    """创建新用户"""
    user = User(wallet_address=wallet_address)
    user_dict = _serialize_for_mongo(user)
    await db.users.insert_one(user_dict)
    return user_dict


async def set_has_agent(wallet_address: str, has_agent: bool) -> bool:
    """设置用户是否有Agent"""
    result = await db.users.update_one(
        {"wallet_address": wallet_address},
        {"$set": {"has_agent": has_agent}}
    )
    return result.modified_count > 0


async def save_message(wallet_address: str, message_in: Dict[str, Any]) -> bool:
    """保存消息到数据库, 接受字典"""
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
    获取用户的历史消息。

    Args:
        wallet_address: 用户的钱包地址。
        show_history: 是否显示完整的历史记录。默认为 False，只显示最近的最终结果。

    Returns:
        消息列表。
    """
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        messages = _deserialize_from_mongo(conversation["messages"])
        if show_history:
             # 返回所有非 "thinking" 类型的消息
            return [msg for msg in messages if msg.get("message_type") != "thinking"]

        else:
            # 只返回最近一次的最终结果 (normal 类型，且不是 tool_call)
            for msg in reversed(messages):
                if msg.get("message_type") == "normal" :
                    return [msg]
            return []  # 如果没有找到，返回空列表
    return []


async def get_previous_messages(wallet_address: str) -> List[Dict[str, Any]]:
    """從資料庫中獲取先前的對話訊息"""
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        # 排除 'status' 類型的訊息，因為它們只是狀態更新，不影響對話上下文
        return [
            _deserialize_from_mongo(msg)
            for msg in conversation["messages"]
            if msg.get("message_type") != "status"
        ]
    return []


async def deploy_multisig_wallet(wallet_address: str) -> str:
    """
    模拟部署 2/2 多签钱包合约。

    Args:
        wallet_address: 用户的钱包地址。

    Returns:
        模拟的多签钱包合约地址。
    """
    # 在真实应用中，这里应该调用区块链相关的代码来部署合约
    # 这里只是模拟，生成一个唯一的合约地址
    multisig_address = f"0xms{uuid4().hex}"

    # 更新用户信息，保存多签钱包地址
    await db.users.update_one(
        {"wallet_address": wallet_address},
        {"$set": {"multisig_address": multisig_address}}
    )
    return multisig_address


async def add_token_to_whitelist(multisig_address: str, token_address: str) -> bool:
    """
    模拟将代币添加到多签钱包的白名单。

    Args:
        multisig_address: 多签钱包地址。
        token_address: 要添加的代币合约地址。

    Returns:
        True 表示添加成功, False 表示失败
    """
    # 在实际应用中，这里应该调用多签合约的相应方法
    # 这里只是模拟
    logger.info(f"Adding {token_address} to whitelist of {multisig_address}")
    # 假设有一个名为 multisig_whitelists 的集合, 实际应用中根据你的合约设计来
    await db.multisig_whitelists.update_one(
        {"multisig_address": multisig_address},
        {"$addToSet": {"whitelisted_tokens": token_address}},
        upsert=True,
    )
    return True

async def clarify_with_user(wallet_address: str, question: str) -> None:
    """向用户发送澄清问题，并保存消息"""
    clarification_message = Message(
        id=str(uuid4()),
        sender="agent",
        text=question,
        message_type="clarification",
    ).dict()
    await save_message(wallet_address, clarification_message)
    await manager.send_message(wallet_address, clarification_message)

# 消息处理函数
async def process_message(wallet_address: str, query: str) -> Dict[str, Any]:
    """處理使用者訊息並返回AI Agent的響應"""

    # 建立依賴項
    deps = TradingAssistantDeps(
        request={"wallet_address": wallet_address},  # 將 wallet_address 放入 request
        update_status_func=lambda _, status: manager.update_status(wallet_address, status),
        send_message_func=lambda _, message: manager.send_message(wallet_address, message),
    )

    # 設置Agent狀態為忙碌
    manager.set_agent_busy(wallet_address, True)
    try:
        # 1. 載入歷史訊息
        previous_messages = await get_previous_messages(wallet_address)
        previous_messages_text = "\n".join(
            [f"{msg['sender']}: {msg['text']}" for msg in previous_messages]
        )

        # 2. 組合歷史訊息和當前查詢
        full_query = f"{previous_messages_text}\nUser: {query}"

        # 3. 運行交易分析
        result = await run_trading_analysis(full_query, deps)

        if isinstance(result, Exception):
            return {"error": str(result)}
        return {"result": result.dict()}  # 返回 Pydantic 模型的字典形式

    finally:
        # 設置Agent狀態為空閒
        manager.set_agent_busy(wallet_address, False)



# WebSocket路由
@app.websocket("/ws/{address}")  # Use path parameter
async def websocket_endpoint(websocket: WebSocket, address: str):
    """WebSocket處理函數"""
    wallet_address = address
    wallet_address = address.lower()
    logger.info(f"New WebSocket connection from: {wallet_address}")
    await manager.connect(wallet_address, websocket)

    user = await get_user(wallet_address)
    if not user:
        user = await create_user(wallet_address)

    try:
        welcome_message = Message(
            id=str(uuid4()),
            sender="agent",
            text="Hello! I'm your AI Trading Assistant. How can I help you today?",
            message_type="normal"
        ).dict()
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
                await manager.send_message(wallet_address, {"error": str(e)})
                continue

            user_message = Message(
                id=str(uuid4()),
                sender="user",
                text=query,
                message_type="normal"
            ).dict()

            await save_message(wallet_address, user_message)

            if manager.is_agent_busy(wallet_address):
                await manager.send_message(wallet_address, {
                    "error": "Agent is busy. Please wait.",
                    "id": str(uuid4()),
                    "timestamp": datetime.now().isoformat()
                })
                continue

            asyncio.create_task(process_and_reply(wallet_address, query))

    except WebSocketDisconnect:
        manager.disconnect(wallet_address)
    except Exception as e:
        logger.exception(f"Error in WebSocket connection: {e}")
        await manager.send_message(
            wallet_address,
            {
                "error": f"An unexpected error occurred: {str(e)}",
                "id": str(uuid4()),
                "timestamp": datetime.now().isoformat(),
            },
        )
        manager.disconnect(wallet_address)


async def process_and_reply(wallet_address: str, query: str):
    """非同步處理訊息並逐步回覆"""
    try:
        result = await process_message(wallet_address, query)
        logger.info(f"Result from process_message: {result}")

        if "error" in result:
            error_message = Message(
                id=str(uuid4()), sender="agent", text=result["error"], message_type="error"
            ).dict()
            await save_message(wallet_address, error_message)
            await manager.send_message(wallet_address, error_message)
            return

        analysis_result = result["result"]
        logger.info(f"Analysis result: {analysis_result}")

        # 根據 safe_to_execute 和 thinking_steps 決定 action 類型
        agent_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=analysis_result["recommendation"],
            message_type="normal"
        )

        if "safe_to_execute" in analysis_result:
            if analysis_result["safe_to_execute"]:
                # 检查 thinking_steps 中是否有 "clarification" 类型的消息
                needs_clarification = any(
                    step.get("message_type") == "clarification" for step in analysis_result.get("thinking_steps", [])
                )
                if needs_clarification:
                    # 如果需要澄清，则不执行后续操作，直接发送澄清问题
                    return

                agent_message.action = {
                    "type": "confirm",
                    "text": "Confirm Transaction",
                    "data": analysis_result,
                }

                #  執行交易
                await handle_ai_transaction(wallet_address, analysis_result)
            else:
                agent_message.action = {
                    "type": "info",
                    "text": "View Details",
                    "data": analysis_result,
                }

        agent_message_dict = agent_message.dict()
        logger.info(f"Agent message: {agent_message_dict}")
        await save_message(wallet_address, agent_message_dict)
        await manager.send_message(wallet_address, agent_message_dict)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        error_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=f"An error occurred: {str(e)}",
            message_type="error",
        ).dict()
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)


async def handle_ai_transaction(wallet_address: str, analysis_result: dict):
    """AI 處理交易流程"""
    logger.info(f"handle ai transaction with: {analysis_result}")
    user = await get_user(wallet_address)
    if not user or not user.get("multisig_address"):
        error_message = Message(
            id=str(uuid4()),
            sender="agent",
            text="Multisig wallet not deployed. Please deploy a multisig wallet first.",
            message_type="error",
        ).dict()
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)

        return

    try:
        # 從分析結果中獲取代幣資訊
        source_token = analysis_result["source_token"]
        target_token = analysis_result["target_token"]

        # 發送狀態更新
        await manager.update_status(wallet_address, "AI is preparing to execute the transaction...")

        # 模擬交易準備階段
        await asyncio.sleep(1)  # 模擬延遲

        # 1. AI 批准交易 (消息)
        approval_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=f"我正在批准將 {source_token['symbol']} 兌換成 {target_token['symbol']} 的交易...",
            message_type="transaction",
        ).dict()
        await save_message(wallet_address, approval_message)
        await manager.send_message(wallet_address, approval_message)
        await asyncio.sleep(1.5)

        # 2. AI 簽名交易 (消息)
        signing_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=f"現在正在使用我的多重簽名金鑰簽署交易...",
            message_type="transaction",
        ).dict()
        await save_message(wallet_address, signing_message)
        await manager.send_message(wallet_address, signing_message)
        await asyncio.sleep(1.5)

        # 3.  從 thinking_steps 中提取 tx_hash
        # (更正：直接从工具函数的返回值中获取，而不是 thinking_steps)
        tx_hash = None
        for step in analysis_result['thinking_steps']:
            if step['question'] == 'Approve transaction details':
                tx_hash = step['answer'].get('tx_hash')
                break  # 找到就退出循环
        if not tx_hash:
            # 如果没有找到，可能是因为流程改变，或者工具函数没有返回
            logger.warning("Transaction hash (tx_hash) not found in thinking steps.")
            tx_hash = "0x" + uuid4().hex  # 生成模擬

        # 4. 模擬發送交易到區塊鏈
        submitting_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=f"交易已提交到區塊鏈。交易哈希：{tx_hash}",
            message_type="transaction",
            action={
                "type": "submitted",
                "tx_hash": tx_hash
            }
        ).dict()
        await save_message(wallet_address, submitting_message)
        await manager.send_message(wallet_address, submitting_message)

    except Exception as e:
        logger.exception(f"AI 交易處理過程中發生錯誤：{e}")
        error_message = Message(
            id=str(uuid4()),
            sender="agent",
            text=f"處理交易失敗：{str(e)}",
            message_type="error",
        ).dict()
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)


# API 路由
@app.post("/api/agent")
async def create_agent(wallet_address: str):
    """
    创建 Agent 记录（不部署多签钱包）。
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
    检查用户的 Agent 状态。
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
    部署多签钱包（模拟）。
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
    """取得使用者訊息的 API，可選擇是否包含思考過程"""
    wallet_address = wallet_address.lower()
    messages = await get_messages(wallet_address, show_history)
    return {"messages": messages}


@app.post("/api/user-signature")
async def user_signature(
        wallet_address: str,
        tx_hash: str,
        user_signature: str
):
    """接收使用者對交易的簽名"""
    wallet_address = wallet_address.lower()
    logger.info(f"收到使用者 {wallet_address} 對交易 {tx_hash} 的簽名")

    # 建立交易完成訊息
    completion_message = Message(
        id=str(uuid4()),
        sender="system",
        text="交易成功完成！多重簽名交易已提交到區塊鏈。",
        message_type="transaction",
        action={
            "type": "completed",
            "text": "交易已完成",
            "data": {
                "tx_hash": tx_hash,
                "user_signature": user_signature,
                "status": "confirmed",
            },
        },
    ).dict()

    await save_message(wallet_address, completion_message)

    if wallet_address in manager.active_connections:
        await manager.send_message(wallet_address, completion_message)

    return {
        "success": True,
        "message": "交易已完成",
        "tx_hash": tx_hash,
        "block_number": 12345678,  # 模擬區塊號
    }


@app.post("/api/user-reject-transaction")
async def user_reject_transaction(
        wallet_address: str,
        tx_hash: str,
        reason: Optional[str] = "使用者拒絕交易"
):
    """使用者拒絕交易"""
    wallet_address = wallet_address.lower()
    logger.info(f"使用者 {wallet_address} 拒絕了交易 {tx_hash}：{reason}")

    rejection_message = Message(
        id=str(uuid4()),
        sender="system",
        text=f"交易被拒絕: {reason}",
        message_type="transaction",
        action={
            "type": "rejected",
            "text": "交易被拒絕",
            "data": {
                "tx_hash": tx_hash,
                "reason": reason
            }
        }
    ).dict()

    await save_message(wallet_address, rejection_message)

    if wallet_address in manager.active_connections:
        await manager.send_message(wallet_address, rejection_message)

    return {"success": True, "message": "交易被拒絕"}


# 初始化資料庫索引
@app.on_event("startup")
async def create_indexes():
    """建立資料庫索引"""
    try:
        await db.users.create_index("wallet_address", unique=True)
        await db.conversations.create_index("wallet_address")
        #  multisig_whitelists 索引 (如果使用)
        await db.multisig_whitelists.create_index("multisig_address")
        logger.info("資料庫索引建立成功")
    except Exception as e:
        logger.error(f"建立資料庫索引失敗：{e}")


# 健康檢查端點
@app.get("/health")
async def health_check():
    """簡單的健康檢查 API"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# 執行應用程式
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")