"""Minimal chat UI for the status investigation agent.

Run:
  pip install streamlit
  streamlit run demo_ui.py
"""
import html
import os

import streamlit as st

from agent import run_agent
from bonus.tools import BonusTools
from providers import CONFIG, Provider
from status_tools import StatusTools

PROVIDER_KEYS = {name: env for name, (env, _) in CONFIG.items()}
DEFAULT_MODELS = {
    'openrouter': 'openai/gpt-4o-mini',
    'openai': 'gpt-4o-mini',
    'groq': 'llama-3.3-70b-versatile',
    'gemini': 'gemini-2.0-flash',
    'anthropic': 'claude-3-5-haiku-latest',
}

st.set_page_config(
    page_title='Status Agent',
    page_icon='◎',
    layout='centered',
    initial_sidebar_state='collapsed',
)

st.markdown(
    '''
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&display=swap');

      /* Do NOT override span / icon fonts — that breaks Material Symbols (visibility, expand, …) */
      .stApp, .stMarkdown, p, label, input, textarea, button {
        font-family: 'DM Sans', sans-serif;
      }
      span[data-testid="stIconMaterial"],
      span[class*="material"],
      .material-icons,
      .material-symbols-rounded,
      .material-symbols-outlined {
        font-family: "Material Symbols Rounded", "Material Symbols Outlined",
                     "Material Icons" !important;
        font-style: normal !important;
        font-weight: normal !important;
        line-height: 1 !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        white-space: nowrap !important;
      }

      [data-testid="stHeader"] { background: transparent; }
      .block-container { padding-top: 2.2rem; max-width: 720px; }

      .hero-title {
        font-size: 1.85rem; font-weight: 600; letter-spacing: -0.02em;
        margin: 0 0 0.35rem 0;
        color: var(--text-color) !important;
      }
      .hero-sub {
        font-size: 0.98rem; margin: 0 0 1.4rem 0; line-height: 1.5;
        color: var(--text-color) !important; opacity: 0.72;
      }
      .answer-box {
        background: var(--secondary-background-color) !important;
        border: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
        border-radius: 14px; padding: 1.1rem 1.2rem;
        color: var(--text-color) !important; line-height: 1.55;
      }
      .meta {
        color: var(--text-color) !important; opacity: 0.65;
        font-size: 0.85rem; margin-top: 0.75rem;
      }
      .stButton > button {
        background: #2a9d8f !important; color: #ffffff !important;
        border: none !important; border-radius: 999px !important;
        padding: 0.45rem 1.15rem !important; font-weight: 500 !important;
      }
      .stButton > button:hover {
        background: #21867a !important; color: #ffffff !important;
      }
      div[data-testid="stTextInput"] input,
      div[data-baseweb="textarea"] textarea,
      div[data-baseweb="select"] > div {
        border-radius: 12px !important;
      }
      div[data-baseweb="textarea"] textarea {
        line-height: 1.5 !important;
        padding-top: 0.75rem !important;
      }
    </style>
    ''',
    unsafe_allow_html=True,
)

st.markdown('<p class="hero-title">Status Agent</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Hỏi về trạng thái GitHub / Cloudflare (và thêm provider nếu bật bonus). '
    'Agent dùng tool trên snapshot hoặc API live, rồi trả lời kèm nguồn.</p>',
    unsafe_allow_html=True,
)

with st.expander('Cấu hình', expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        provider_name = st.selectbox(
            'Provider',
            ['openrouter', 'openai', 'groq', 'gemini', 'anthropic'],
            index=0,
        )
        mode = st.selectbox('Nguồn dữ liệu', ['snapshot', 'live'], index=0)
    with col2:
        default_model = os.getenv('MODEL') or DEFAULT_MODELS.get(provider_name, '')
        model = st.text_input('Model', value=default_model)
        max_steps = st.slider('Max steps', 2, 16, 8)
    bonus = st.toggle('Bonus tools (5 providers)', value=False)

    key_env = PROVIDER_KEYS[provider_name]
    existing = os.getenv(key_env) or ''
    api_key = st.text_input(
        f'API key ({key_env})',
        value='',
        type='password',
        placeholder='đã có trong env' if existing else 'dán key vào đây',
        help='Ưu tiên key nhập ở đây; nếu để trống sẽ dùng biến môi trường.',
    )
    if existing and not api_key:
        st.caption(f'Đang dùng {key_env} từ môi trường (đã set).')
    elif not existing and not api_key:
        st.warning(f'Chưa có {key_env}. Dán key ở trên hoặc set trong terminal rồi chạy lại Streamlit.')

question = st.text_area(
    'Câu hỏi',
    placeholder='Ví dụ: GitHub Actions hiện có sự cố không? Hãy kiểm tra incident gần đây.',
    height=100,
    label_visibility='collapsed',
)

ask = st.button('Hỏi agent', use_container_width=False)

if 'history' not in st.session_state:
    st.session_state.history = []

if ask:
    q = (question or '').strip()
    if not q:
        st.warning('Nhập một câu hỏi trước.')
    elif not model.strip():
        st.warning('Cần tên model.')
    else:
        key_env = PROVIDER_KEYS[provider_name]
        if api_key.strip():
            os.environ[key_env] = api_key.strip()
        with st.spinner('Đang gọi model và tools...'):
            try:
                provider = Provider(provider_name, model.strip())
                tools = BonusTools(mode) if bonus else StatusTools(mode)
                result = run_agent(q, provider, tools, max_steps=max_steps)
                st.session_state.history.insert(0, {'question': q, 'result': result})
            except Exception as exc:
                st.error(str(exc))

for item in st.session_state.history:
    st.markdown(f"**Bạn:** {item['question']}")
    result = item['result']
    answer = result.get('answer') or '(không có câu trả lời)'
    safe = html.escape(answer).replace('\n', '<br>')
    st.markdown(f'<div class="answer-box">{safe}</div>', unsafe_allow_html=True)
    status = result.get('status', '?')
    err = result.get('error')
    meta = f'status: <b>{html.escape(str(status))}</b>'
    if err:
        meta += f' · error: {html.escape(str(err))}'
    st.markdown(f'<p class="meta">{meta}</p>', unsafe_allow_html=True)
    with st.expander('Xem trace'):
        tool_events = [t for t in result.get('trace', []) if t.get('event') == 'tool']
        if tool_events:
            for t in tool_events:
                st.markdown(f"- `{t.get('name')}` · step {t.get('step')}")
                st.code(t.get('arguments') or '', language='json')
        st.json(result.get('trace', []))
    st.divider()
