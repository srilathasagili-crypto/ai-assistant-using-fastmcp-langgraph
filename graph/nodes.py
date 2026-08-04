from langchain_core.messages import AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode

from graph.state import AssistantState
from graph.llm import get_llm
from graph.logger import get_logger
from memory.user_profile import format_profile_for_prompt

from tools.calculator import calculator
from tools.weather import get_weather
from tools.gmail import send_email
from tools.news import search_news, get_top_headlines
from tools.web_search import web_search
from tools.calendar_tool import add_calendar_event, list_today_events, delete_calendar_event
from tools.pdf_tools import ask_pdf_question, summarize_pdf, extract_pdf_key_info
from tools.reminders_tool import add_reminder, show_reminders, remove_reminder
from tools.memory_tool import remember_user_info, recall_user_info

logger = get_logger("graph.nodes")

TOOLS = [
    # Existing tools — unchanged.
    calculator,
    get_weather,
    send_email,
    # News
    search_news,
    get_top_headlines,
    # Web search
    web_search,
    # Calendar
    add_calendar_event,
    list_today_events,
    delete_calendar_event,
    # PDF analysis
    ask_pdf_question,
    summarize_pdf,
    extract_pdf_key_info,
    # Reminders
    add_reminder,
    show_reminders,
    remove_reminder,
    # Long-term memory
    remember_user_info,
    recall_user_info,
]

_llm = get_llm()
_llm_with_tools = _llm.bind_tools(TOOLS)

BASE_SYSTEM_PROMPT = (
    "You are a helpful, concise AI assistant. "
    "Use the calculator tool for any math. "
    "Use the weather tool for current weather questions. "
    "Use the send_email tool only when the user explicitly asks to send an email — "
    "if they mention attaching a file, pass its path as attachment_path. "
    "Use search_news for news about a specific topic, and get_top_headlines for general/today's headlines. "
    "Use web_search for general knowledge or current-events questions you're not confident about. "
    "Use the calendar tools to create, list, or delete Google Calendar events. "
    "Use the PDF tools (ask_pdf_question, summarize_pdf, extract_pdf_key_info) only when the user "
    "has uploaded a PDF and is asking about it. "
    "Use the reminder tools to create, list, or delete reminders for the user. "
    "Whenever the user states their name or a clear preference (favourite language, food, topic, etc.), "
    "call remember_user_info to save it. If asked what you remember about them, call recall_user_info. "
    "Never call a tool unless it's clearly needed. "
    "If a tool returns an error message, explain it to the user in plain language instead of retrying blindly."
)


def _build_system_message(user_id: str) -> SystemMessage:
    profile_facts = format_profile_for_prompt(user_id) if user_id else ""
    prompt = BASE_SYSTEM_PROMPT + (f"\n\nWhat you already know about this user: {profile_facts}" if profile_facts else "")
    return SystemMessage(content=prompt)


def chat_node(state: AssistantState) -> dict:
    messages = state["messages"]
    user_id = state.get("user_id", "default_user")

    system_message = _build_system_message(user_id)
    if not messages or messages[0].type != "system":
        messages = [system_message] + list(messages)
    else:
        # Refresh the system message each turn so newly-learned profile facts show up
        # without growing the message list.
        messages = [system_message] + list(messages[1:])

    try:
        response = _llm_with_tools.invoke(messages)
    except Exception as e:
        # Never let an LLM/API hiccup crash the app — surface a friendly message instead.
        logger.exception("LLM invocation failed")
        return {"messages": [AIMessage(content=f"Sorry, I hit an error talking to the model: {e}")]}

    if getattr(response, "tool_calls", None):
        logger.info(f"Tool calls requested: {[tc['name'] for tc in response.tool_calls]}")

    return {"messages": [response]}


# handle_tool_errors=True (the default) means a tool raising an exception is caught by
# LangGraph itself and turned into a ToolMessage with the error text, instead of crashing
# the graph — this is the last line of defense on top of each tool's own try/except.
tool_node = ToolNode(TOOLS, handle_tool_errors=True)
