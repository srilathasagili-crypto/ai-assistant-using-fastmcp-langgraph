import uuid

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from graph.builder import build_graph
from graph.config import validate_config
from graph.logger import get_logger
from memory.chat_history import get_thread_config
from memory.user_profile import get_profile
from memory.reminders import get_due_unnotified
from tools.pdf_extract import extract_pdf_text
from ui.components import (
    apply_theme,
    render_tool_status,
    render_memory_status,
    render_reminder_banner,
)

logger = get_logger("app")

st.set_page_config(
    page_title="Intelligent AI Assistant",
    page_icon="🤖",
    layout="wide",
)

apply_theme()


@st.cache_resource
def get_graph():
    logger.info("Building graph...")
    return build_graph()


def init_session():
    if "user_id" not in st.session_state:
        st.session_state.user_id = None

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
        logger.info(
            f"Started new conversation thread: {st.session_state.thread_id}"
        )

    if "history" not in st.session_state:
        st.session_state.history = []

    if "pdf_uploaded_name" not in st.session_state:
        st.session_state.pdf_uploaded_name = None

    if "voice_enabled" not in st.session_state:
        st.session_state.voice_enabled = False


def render_history():
    for message in st.session_state.history:
        role = "user" if isinstance(message, HumanMessage) else "assistant"

        with st.chat_message(role):
            st.markdown(message.content)


def render_sidebar(status: dict):
    st.sidebar.title("⚙️ Assistant")

    name_input = st.sidebar.text_input(
        "Your name",
        value=st.session_state.user_id or "",
        help=(
            "Used as your memory key, so preferences and history "
            "are remembered next time you use this name."
        ),
    )

    if name_input.strip():
        st.session_state.user_id = (
            name_input.strip().lower().replace(" ", "_")
        )

    st.sidebar.divider()

    render_tool_status(status)

    st.sidebar.divider()

    if st.session_state.user_id:
        profile = get_profile(st.session_state.user_id)
        render_memory_status(profile)
    else:
        st.sidebar.info(
            "Enter your name above to enable long-term memory."
        )

    st.sidebar.divider()

    st.sidebar.markdown("### 📄 PDF Analysis")

    uploaded_file = st.sidebar.file_uploader(
        "Upload a PDF",
        type=["pdf"],
    )

    st.sidebar.divider()

    st.session_state.voice_enabled = st.sidebar.checkbox(
        "🎤 Voice mode",
        value=st.session_state.voice_enabled,
    )

    st.sidebar.divider()

    if st.sidebar.button("🗑️ Clear chat"):
        st.session_state.history = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.pdf_uploaded_name = None
        st.rerun()

    return uploaded_file


def handle_pdf_upload(uploaded_file, graph, config):
    """
    Extract text from a newly uploaded PDF and store it directly
    into the graph's checkpointed state.

    Deliberately uses update_state() instead of graph.invoke()
    so that uploading a PDF does not trigger an extra LLM call.
    """

    if uploaded_file is None:
        return

    if st.session_state.pdf_uploaded_name == uploaded_file.name:
        return

    with st.spinner("Reading PDF..."):
        text = extract_pdf_text(uploaded_file)

    if not text:
        st.sidebar.error(
            "Couldn't extract text from this PDF "
            "(it may be scanned/image-only)."
        )
        return

    graph.update_state(
        config,
        {
            "pdf_context": text,
            "user_id": st.session_state.user_id or "default_user",
        },
    )

    st.session_state.pdf_uploaded_name = uploaded_file.name

    st.sidebar.success(
        f"'{uploaded_file.name}' loaded — ask me to summarize it "
        "or answer questions about it."
    )


def handle_voice_input() -> str | None:
    try:
        from streamlit_mic_recorder import mic_recorder
    except ImportError:
        st.sidebar.warning(
            "Voice mode needs the 'streamlit-mic-recorder' package "
            "(see requirements.txt)."
        )
        return None

    audio = mic_recorder(
        start_prompt="🎙️ Speak",
        stop_prompt="⏹ Stop",
        key="recorder",
    )

    if not audio:
        return None

    try:
        from groq import Groq
        from graph.config import GROQ_API_KEY

        client = Groq(api_key=GROQ_API_KEY)

        tmp_path = "/tmp/voice_input.wav"

        with open(tmp_path, "wb") as f:
            f.write(audio["bytes"])

        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=f,
                model="whisper-large-v3",
            )

        return result.text

    except Exception as e:
        logger.exception("Voice transcription failed")
        st.warning(f"Couldn't transcribe audio: {e}")
        return None


def speak(text: str):
    try:
        from gtts import gTTS
        import io

        tts = gTTS(
            text=text,
            lang="en",
        )

        buf = io.BytesIO()

        tts.write_to_fp(buf)

        buf.seek(0)

        st.audio(
            buf,
            format="audio/mp3",
        )

    except Exception as e:
        logger.exception("Text-to-speech failed")
        st.caption(
            f"(voice output unavailable: {e})"
        )


def extract_reply_text(content) -> str:
    """
    Convert Gemini/LangChain content into a clean string.

    Gemini may return content as:

    [
        {
            "type": "text",
            "text": "Hello!",
            "extras": {...}
        }
    ]

    This function extracts only the actual text and removes
    metadata such as signatures.
    """

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text = item.get("text", "")

                    if text:
                        text_parts.append(str(text))

            elif isinstance(item, str):
                text_parts.append(item)

        return "\n".join(text_parts).strip()

    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text", ""))

        if "text" in content:
            return str(content["text"])

    return str(content)


def main():
    st.title("🤖 Intelligent AI Assistant")

    init_session()

    status = validate_config()

    graph = get_graph()

    config = get_thread_config(
        st.session_state.thread_id
    )

    uploaded_file = render_sidebar(status)

    handle_pdf_upload(
        uploaded_file,
        graph,
        config,
    )

    if st.session_state.user_id:
        render_reminder_banner(
            get_due_unnotified(
                st.session_state.user_id
            )
        )

    render_history()

    user_input = st.chat_input(
        "Ask me anything..."
    )

    if st.session_state.voice_enabled:
        voice_text = handle_voice_input()

        if voice_text:
            user_input = voice_text

    if not user_input:
        return

    user_message = HumanMessage(
        content=user_input
    )

    st.session_state.history.append(
        user_message
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            try:
                result = graph.invoke(
                    {
                        "messages": [user_message],
                        "user_id": (
                            st.session_state.user_id
                            or "default_user"
                        ),
                    },
                    config=config,
                )

                # Get the latest AI message
                latest_message = result["messages"][-1]

                # Extract clean text from Gemini response
                reply = extract_reply_text(
                    latest_message.content
                )

                if not reply:
                    reply = (
                        "I received an empty response "
                        "from the model."
                    )

            except Exception:
                logger.exception(
                    "Error while processing user input"
                )

                reply = (
                    "Sorry, something went wrong. "
                    "Please try again."
                )

        # Display clean assistant response
        st.markdown(reply)

        # Optional voice output
        if st.session_state.voice_enabled:
            speak(reply)

    # Save clean response to chat history
    st.session_state.history.append(
        AIMessage(content=reply)
    )


if __name__ == "__main__":
    main()
