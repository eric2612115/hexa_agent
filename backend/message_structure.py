# --- 標準化的WebSocket消息結構 ---
from datetime import datetime
from uuid import uuid4


class MessageStructure:
    """統一的WebSocket消息格式化工具類"""

    @staticmethod
    def format_ai_response(trading_analysis) -> dict:
        """將AI分析結果格式化為標準化的前端消息格式"""

        # 基本消息結構
        message = {
            "id": str(uuid4()),
            "sender": "agent",
            "timestamp": datetime.now().isoformat(),
            "message_type": "normal"
        }

        # 從分析結果中提取重要信息，構建結構化的文本
        summary = {
            "recommendation": getattr(trading_analysis, 'recommendation', 'Analysis complete'),
            "source_token": getattr(getattr(trading_analysis, 'source_token', None), 'symbol', 'UNKNOWN'),
            "transaction_type": "UNKNOWN"
        }

        # 確定交易類型 (單一交易或投資組合)
        if hasattr(trading_analysis, 'target_token'):
            if hasattr(trading_analysis.target_token, 'symbol') and trading_analysis.target_token.symbol:
                summary["target_token"] = trading_analysis.target_token.symbol
                summary["transaction_type"] = "SINGLE_SWAP"
            else:
                summary["transaction_type"] = "PORTFOLIO"

        # 安全分析
        if hasattr(trading_analysis, 'security_analysis'):
            summary["security_analysis"] = trading_analysis.security_analysis

        if hasattr(trading_analysis, 'contract_risk'):
            summary["risk_level"] = trading_analysis.contract_risk

        # 投資組合分配（如果適用）
        if summary["transaction_type"] == "PORTFOLIO":
            summary["portfolio"] = []

            # 嘗試從thinking_steps提取投資組合信息
            if hasattr(trading_analysis, 'thinking_steps'):
                for step in trading_analysis.thinking_steps:
                    if hasattr(step, 'answer') and isinstance(step.answer, dict) and 'tokens' in step.answer:
                        for token in step.answer['tokens']:
                            summary["portfolio"].append({
                                "symbol": token.get('symbol', 'Unknown'),
                                "allocation": token.get('allocation', 20),
                                "security_score": token.get('security_score', 'N/A')
                            })
                        break

        # 生成格式化的文本輸出
        text_parts = []

        # 主要建議
        text_parts.append(summary["recommendation"])

        # 交易詳情
        if summary["transaction_type"] == "SINGLE_SWAP":
            text_parts.append(f"\nTrade: {summary['source_token']} → {summary['target_token']}")
        else:
            text_parts.append(f"\nTrade: {summary['source_token']} → Portfolio")

            # 添加投資組合詳情
            if "portfolio" in summary and summary["portfolio"]:
                portfolio_text = "\nPortfolio Distribution:"

                for token in summary["portfolio"]:
                    portfolio_text += f"\n- {token['symbol']}: {token['allocation']}% (Security Evaluation: {token['security_score']})"

                text_parts.append(portfolio_text)

        # 安全分析
        if "security_analysis" in summary:
            text_parts.append(f"\nSecurity Analyze: {summary['security_analysis']}")

        if "risk_level" in summary:
            text_parts.append(f"Risk Level: {summary['risk_level']}")

        # 設置結構化的文本和摘要
        message["text"] = "\n".join(text_parts)
        message["summary"] = summary

        # 設置操作按鈕（如果適用）
        if hasattr(trading_analysis, 'safe_to_execute'):
            safe_to_execute = trading_analysis.safe_to_execute

            if safe_to_execute:
                message["action"] = {
                    "type": "confirm",
                    "text": "確認交易",
                    "data": summary
                }
            else:
                message["action"] = {
                    "type": "info",
                    "text": "See more",
                    "data": summary
                }

        return message

    @staticmethod
    def format_thinking_step(step, phase=None) -> dict:
        """將AI的思考步驟格式化為前端消息"""

        # 如果step是ThinkingStep對象
        if hasattr(step, 'phase') and hasattr(step, 'question') and hasattr(step, 'answer'):
            phase = step.phase
            question = step.question
            answer = step.answer
        else:
            # 否則假設它是字典
            phase = phase or step.get('phase', 'thinking')
            question = step.get('question', 'Analyzing...')
            answer = step.get('answer', '')

        # 以前端友好的格式化文本
        text = f"階段: {phase}\n問題: {question}\n"

        # 格式化答案 (可能是字符串或字典)
        if isinstance(answer, dict):
            text += "答案:\n"
            for key, value in answer.items():
                text += f"- {key}: {value}\n"
        else:
            text += f"答案: {answer}"

        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "message_type": "thinking",
            "phase": phase
        }

    @staticmethod
    def format_tool_call(tool_name, params=None) -> dict:
        """格式化工具调用消息"""
        # 提取参数
        params = params or {}
        text_content = params.pop("text_content", None)
        params_str = ", ".join([f"{k}={v}" for k, v in params.items() if v and k != "text_content"])

        # 使用 text_content 作为主要显示文本，如果没有则使用工具调用描述
        display_text = text_content or f"Using Tool: {tool_name}" + (f" ({params_str})" if params_str else "")

        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": display_text,
            "timestamp": datetime.now().isoformat(),
            "message_type": "tool_call",
            "tool": {
                "name": tool_name,
                "params": params
            }
        }

    @staticmethod
    def format_error(error_text) -> dict:
        """格式化錯誤消息"""
        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": error_text,
            "timestamp": datetime.now().isoformat(),
            "message_type": "error"
        }

    @staticmethod
    def format_status(status_text) -> dict:
        """格式化狀態更新消息"""
        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": status_text,
            "timestamp": datetime.now().isoformat(),
            "message_type": "status"
        }

    @staticmethod
    def format_transaction(text, status="pending", action=None) -> dict:
        """格式化交易相關消息"""
        message = {
            "id": str(uuid4()),
            "sender": "system",
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "message_type": "transaction",
            "status": status
        }

        if action:
            message["action"] = action

        return message