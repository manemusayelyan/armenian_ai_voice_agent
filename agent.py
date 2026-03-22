import logging
import os
import re
from pathlib import Path
from typing import AsyncIterable

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.agents.llm.chat_context import ChatContext, ChatMessage
from livekit.plugins import groq, openai, silero

from bank_knowledge import (
    BRANCH_SECTION,
    build_knowledge_chunks,
    detect_requested_bank,
    detect_requested_fields,
    detect_requested_section,
    format_retrieved_context,
    load_bank_context,
    normalize_text,
    query_tokens,
    retrieve_relevant_chunks,
    tokenize,
)
from speech_formatting import format_for_armenian_tts

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("armenian-bank-agent")

PROJECT_ROOT = Path(__file__).parent
BANK_CONTEXT_PATH = PROJECT_ROOT / "bank_data" / "bank_context.txt"
STT_PROVIDER = os.getenv(
    "AGENT_STT_PROVIDER",
    "openai" if os.getenv("OPENAI_API_KEY") else "groq",
).lower()
DEFAULT_STT_MODEL = "gpt-4o-transcribe" if STT_PROVIDER == "openai" else "whisper-large-v3"
LLM_MODEL = os.getenv("AGENT_LLM_MODEL", "gpt-4.1-mini")
STT_MODEL = os.getenv("AGENT_STT_MODEL", DEFAULT_STT_MODEL)
TTS_MODEL = os.getenv("AGENT_TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("AGENT_TTS_VOICE", "nova")
SUPPORTED_BANKS = ("ԱԿԲԱ Բանկ", "Արմէկոնոմբանկ", "Ֆասթ Բանկ")
SUPPORTED_SECTIONS = ("վարկեր", "ավանդներ", "մասնաճյուղեր")
STT_PROMPT = os.getenv(
    "AGENT_STT_PROMPT",
    (
        "Armenian banking assistant vocabulary. "
        "Recognize Armenian bank names and terms accurately: "
        "ԱԿԲԱ Բանկ, Արմէկոնոմբանկ, Ֆասթ Բանկ, ACBA, AEB, Fast Bank, "
        "վարկ, ավանդ, մասնաճյուղ, հասցե, տոկոսադրույք, տարեկան եկամտաբերություն, "
        "ժամկետ, գումար, արժույթ, կանխավճար, վաղաժամկետ մարման տույժ, "
        "ուսման վարկ, հիփոթեք, սպառողական վարկ, անգրավ վարկ."
    ),
)

NUMBER_READING_GUIDE = """
Armenian reading guide for spoken answers:
- Read numbers as Armenian words, not digit by digit.
- Read `%` as `տոկոս`.
- Read decimal numbers naturally in Armenian, using `ամբողջ` when needed.
- Read ranges as `X-ից Y`.
- Read currency names in Armenian after the amount.

Few-shot examples:
- `13%` -> `տասներեք տոկոս`
- `8-10,5%` -> `ութից տաս ամբողջ հինգ տոկոս`
- `10% կանխավճար` -> `տաս տոկոս կանխավճար`
- `60․000․000 AMD` -> `վաթսուն միլիոն դրամ`
- `50,000 AMD` -> `հիսուն հազար դրամ`
- `240 ամիս` -> `երկու հարյուր քառասուն ամիս`
- `31-550 օր` -> `երեսուն մեկից հինգ հարյուր հիսուն օր`
- `AMD, USD, EUR, RUB` -> `դրամ, ամերիկյան դոլար, եվրո, ռուբլի`
""".strip()

SYSTEM_PROMPT = f"""
You are a voice assistant for Armenian banks.

Rules:
- Always answer only in Armenian.
- You may answer only about loans, deposits, and branch locations/addresses.
- You support only these banks: ACBA Bank, Armeconombank, and Fast Bank.
- Relevant bank context for each user turn will be injected in a developer message.
- Use only that injected context for factual answers.
- If the injected context does not contain the answer, say in Armenian that you do not have that information.
- Never guess or invent rates, amounts, addresses, working hours, or other facts.
- Keep the conversation on the current bank unless the user explicitly changes the bank.
- For direct fact questions, answer with the exact fact first.
- For follow-up questions, use the conversation context to stay on the same bank and product when it is clear.
- If the retrieved snippets point to more than one plausible product, ask one short clarification question in Armenian instead of mixing facts.
- If the bank is missing, ask which bank the user means before giving facts.
- If the bank is clear but the information type is still unclear, ask whether they need loans, deposits, or branch addresses.
- Never infer the number of products from the number of retrieved snippets or examples.
- State a product count only if the user explicitly asks for the count and the full available-options list is present in context.
- Prefer 1-3 short Armenian sentences and mention the bank/product name when useful.
- Keep answers concise and easy to speak aloud.
- For loan product answers, if the context includes them, mention these core facts first: տոկոսադրույք, առավելագույն գումար, ժամկետ, then one more key condition such as կանխավճար or վաղաժամկետ մարման տույժ.
- Do not replace a loan's առավելագույն գումար with նվազագույն գումար if the maximum amount is present in context.
- If the user asks a broad question like "վարկեր", summarize the available options from the retrieved context instead of saying you do not know.
- Use this pronunciation guide when generating Armenian answers that include numbers, amounts, or percents:
{NUMBER_READING_GUIDE}
""".strip()

GREETING = (
    "Բարև։ Ո՞ր բանկի մասին եք ուզում տեղեկություն ստանալ` "
    "ԱԿԲԱ Բանկ, Արմէկոնոմբանկ, թե Ֆասթ Բանկ, և ինչի մասին` "
    "վարկեր, ավանդներ, թե մասնաճյուղերի հասցեներ։"
)


def build_retrieval_query(turn_ctx: ChatContext, new_message: ChatMessage) -> str:
    current_text = (new_message.text_content or "").strip()
    return _build_retrieval_query_from_text(turn_ctx, current_text)


def _build_retrieval_query_from_text(turn_ctx: ChatContext, current_text: str) -> str:
    if not current_text:
        return ""

    query_parts = [current_text]
    if _query_has_enough_context(current_text):
        return current_text

    for message in reversed(turn_ctx.messages()):
        if message.role != "user":
            continue
        text = (message.text_content or "").strip()
        if not text or text == current_text:
            continue
        query_parts.append(text)
        combined_query = "\n".join(query_parts)
        if _query_has_enough_context(combined_query) or len(query_parts) >= 3:
            break

    return "\n".join(query_parts)


def _query_has_enough_context(text: str) -> bool:
    normalized = normalize_text(text)
    base_tokens = [token for token in tokenize(text) if token]
    expanded_tokens = [token for token in query_tokens(text) if token]

    requested_bank = detect_requested_bank(normalized)
    requested_section = detect_requested_section(expanded_tokens)
    requested_fields = detect_requested_fields(expanded_tokens, normalized)

    if requested_bank and requested_section:
        return True
    if requested_bank and len(base_tokens) >= 4:
        return True
    if requested_section and len(base_tokens) >= 4 and not requested_fields:
        return True
    return False


def _infer_active_bank(turn_ctx: ChatContext, current_text: str) -> str | None:
    current_bank = detect_requested_bank(normalize_text(current_text))
    if current_bank:
        return current_bank

    for message in reversed(turn_ctx.messages()):
        if message.role != "user":
            continue
        message_text = (message.text_content or "").strip()
        if not message_text:
            continue
        bank = detect_requested_bank(normalize_text(message_text))
        if bank:
            return bank

    return None


def _infer_active_section(turn_ctx: ChatContext, current_text: str) -> str | None:
    current_section = detect_requested_section(query_tokens(current_text))
    if current_section:
        return current_section

    for message in reversed(turn_ctx.messages()):
        if message.role != "user":
            continue
        message_text = (message.text_content or "").strip()
        if not message_text:
            continue
        section = detect_requested_section(query_tokens(message_text))
        if section:
            return section

    return None


def _is_multi_bank_query(text: str) -> bool:
    normalized = normalize_text(text)
    hints = (
        "որ բանկ",
        "որ բանկում",
        "ինչ բանկ",
        "ինչ բանկում",
        "բոլոր բանկ",
        "մի քանի բանկ",
        "համեմատ",
    )
    return any(hint in normalized for hint in hints)


def _is_affirmative(text: str) -> bool:
    normalized = normalize_text(text)
    tokens = set(tokenize(text))
    if tokens.intersection({"այո", "հա", "հաստատ", "իհարկե"}):
        return True
    return any(phrase in normalized for phrase in ("այո", "փոխիր", "անցիր", "լավ փոխենք"))


def _is_negative(text: str) -> bool:
    normalized = normalize_text(text)
    tokens = set(tokenize(text))
    if tokens.intersection({"ոչ", "չէ", "չեմ", "մնա"}):
        return True
    return any(phrase in normalized for phrase in ("ոչ", "չփոխ", "մնանք"))


def _is_options_query(text: str) -> bool:
    normalized = normalize_text(text)
    hints = (
        "ինչ վարկեր ունի",
        "ինչ ավանդներ ունի",
        "ինչ տեսակ",
        "ինչ տարբերակ",
        "ուրիշ ինչ",
        "այլ ինչ",
        "ինչ այլ",
        "բոլոր վարկ",
        "բոլոր ավանդ",
    )
    return any(hint in normalized for hint in hints)


def _needs_bank_clarification(user_text: str, active_bank: str | None) -> bool:
    if active_bank or _is_multi_bank_query(user_text):
        return False

    normalized = normalize_text(user_text)
    return any(
        token in normalized
        for token in ("վարկ", "ավանդ", "հասցե", "մասնաճյուղ", "բանկ")
    )


def _needs_section_clarification(
    user_text: str,
    active_bank: str | None,
    active_section: str | None,
) -> bool:
    if not active_bank or active_section or _is_multi_bank_query(user_text):
        return False
    return True


def _build_focus_instruction(active_bank: str | None, active_section: str | None) -> str:
    parts = []
    if active_bank:
        parts.append(
            f"Current conversation bank: {active_bank}. "
            f"Unless the user explicitly changes the bank, answer only about {active_bank}."
        )
    if active_section:
        parts.append(
            f"Current information type: {active_section}. "
            f"Stay in this information type unless the user clearly changes it."
        )
    return "\n".join(parts)


def _augment_query_with_focus(
    query: str,
    user_text: str,
    active_bank: str | None,
    active_section: str | None,
) -> str:
    query_parts = [query]
    normalized = normalize_text(user_text)

    if active_bank and not detect_requested_bank(normalized) and not _is_multi_bank_query(user_text):
        query_parts.insert(0, active_bank)

    if active_section and not detect_requested_section(query_tokens(user_text)):
        query_parts.insert(1 if len(query_parts) > 1 else 0, active_section)

    return "\n".join(part for part in query_parts if part)


def _filter_retrieved_to_focus(
    retrieved: list,
    active_bank: str | None,
    active_section: str | None,
    user_text: str,
) -> list:
    if _is_multi_bank_query(user_text):
        return retrieved

    filtered = retrieved
    if active_bank:
        bank_matches = [chunk for chunk in filtered if chunk.bank == active_bank]
        if bank_matches:
            filtered = bank_matches

    if active_section:
        section_matches = [chunk for chunk in filtered if chunk.section == active_section]
        if section_matches:
            filtered = section_matches

    return filtered


def _branch_location_tokens(
    user_text: str,
    active_bank: str | None,
    active_section: str | None,
) -> list[str]:
    if (
        detect_requested_section(query_tokens(user_text)) != BRANCH_SECTION
        and active_section != BRANCH_SECTION
    ):
        return []

    ignored_tokens = {
        "հասցե",
        "հասցեն",
        "որտեղ",
        "մասնաճյուղ",
        "մասնաճյուղեր",
        "բանկ",
        "բանկի",
        "ունի",
    }
    if active_bank:
        ignored_tokens.update(tokenize(active_bank))

    return [
        token
        for token in query_tokens(user_text)
        if token not in ignored_tokens and len(token) >= 3
    ]


def _filter_branch_chunks_by_location(retrieved: list, location_tokens: list[str]) -> list:
    if not location_tokens:
        return retrieved

    matches = [
        chunk
        for chunk in retrieved
        if any(
            token in chunk.normalized_title or token in chunk.normalized_text
            for token in location_tokens
        )
    ]
    return matches or retrieved


async def _spoken_text_stream(text: AsyncIterable[str]) -> AsyncIterable[str]:
    buffer = ""

    async for chunk in text:
        buffer += chunk
        segments, buffer = _extract_ready_tts_segments(buffer)
        for segment in segments:
            formatted = format_for_armenian_tts(segment)
            if formatted:
                yield formatted

    if buffer.strip():
        formatted = format_for_armenian_tts(buffer)
        if formatted:
            yield formatted


def _extract_ready_tts_segments(buffer: str) -> tuple[list[str], str]:
    segments = []
    boundary_pattern = re.compile(r"(.+?[\.!\?։\n]+)(?:\s+|$)", re.DOTALL)

    while True:
        match = boundary_pattern.match(buffer)
        if not match:
            break
        segment = match.group(1).strip()
        if segment:
            segments.append(segment)
        buffer = buffer[match.end():]

    if len(buffer) > 160 and " " in buffer:
        split_at = buffer.rfind(" ", 0, 160)
        if split_at > 0:
            segments.append(buffer[:split_at].strip())
            buffer = buffer[split_at + 1 :]

    return segments, buffer


def build_stt_engine():
    if STT_PROVIDER == "openai":
        return openai.STT(
            model=STT_MODEL,
            language="hy",
            prompt=STT_PROMPT,
        )

    return groq.STT(
        model=STT_MODEL,
        language="hy",
        prompt=STT_PROMPT,
    )


BANK_CONTEXT = load_bank_context(BANK_CONTEXT_PATH)
logger.info("Loaded bank context: %s (%d chars)", BANK_CONTEXT_PATH.name, len(BANK_CONTEXT))
KNOWLEDGE_CHUNKS = build_knowledge_chunks(BANK_CONTEXT)
logger.info("Built %d searchable chunks from bank_context.txt", len(KNOWLEDGE_CHUNKS))
logger.info(
    "Agent models configured: stt_provider=%s stt_model=%s llm=%s tts=%s voice=%s",
    STT_PROVIDER,
    STT_MODEL,
    LLM_MODEL,
    TTS_MODEL,
    TTS_VOICE,
)


class BankAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.active_bank: str | None = None
        self.active_section: str | None = None
        self.pending_switch_bank: str | None = None
        self.pending_switch_query: str | None = None

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        user_text = (new_message.text_content or "").strip()
        if not user_text:
            return

        effective_user_text = user_text
        switch_instruction = ""
        normalized_user = normalize_text(user_text)
        current_bank = detect_requested_bank(normalized_user)
        current_section = detect_requested_section(query_tokens(user_text))

        if self.pending_switch_bank:
            pending_bank = self.pending_switch_bank
            pending_query = self.pending_switch_query or pending_bank

            if _is_affirmative(user_text):
                self.active_bank = pending_bank
                self.active_section = None
                effective_user_text = pending_query
                normalized_user = normalize_text(effective_user_text)
                current_bank = pending_bank
                current_section = detect_requested_section(query_tokens(effective_user_text))
                switch_instruction = (
                    f"The user confirmed switching to {pending_bank}. "
                    f"Treat the active request as: {effective_user_text}"
                )
                self.pending_switch_bank = None
                self.pending_switch_query = None
            elif _is_negative(user_text):
                declined_bank = pending_bank
                self.pending_switch_bank = None
                self.pending_switch_query = None
                turn_ctx.add_message(
                    role="developer",
                    content=(
                        f"The user declined switching to {declined_bank}. "
                        f"Stay on {self.active_bank or 'the current bank'}. "
                        "Reply in one short Armenian sentence that you will stay on the current bank "
                        "and ask what information they need."
                    ),
                )
                return
            else:
                turn_ctx.add_message(
                    role="developer",
                    content=(
                        f"You asked whether to switch from {self.active_bank or 'the current bank'} "
                        f"to {pending_bank}. The user did not answer clearly. "
                        "Ask the same confirmation question again in one short Armenian sentence "
                        "and wait for a yes/no answer in Armenian."
                    ),
                )
                return

        if (
            current_bank
            and self.active_bank
            and current_bank != self.active_bank
            and not _is_multi_bank_query(user_text)
        ):
            self.pending_switch_bank = current_bank
            self.pending_switch_query = user_text
            turn_ctx.add_message(
                role="developer",
                content=(
                    f"The current bank is {self.active_bank}. "
                    f"The user mentioned {current_bank}. "
                    f"Ask one short Armenian confirmation question asking whether they are sure "
                    f"they want to switch from {self.active_bank} to {current_bank}. "
                    "Do not provide banking facts yet."
                ),
            )
            return

        active_bank = current_bank or self.active_bank or _infer_active_bank(turn_ctx, effective_user_text)
        active_section = (
            current_section
            or self.active_section
            or _infer_active_section(turn_ctx, effective_user_text)
        )

        if active_bank:
            self.active_bank = active_bank
        if active_section:
            self.active_section = active_section

        if _needs_bank_clarification(effective_user_text, active_bank):
            turn_ctx.add_message(
                role="developer",
                content=(
                    "The user has not chosen a bank yet. "
                    "Ask one short clarification question in Armenian asking which bank they mean: "
                    "ԱԿԲԱ Բանկ, Արմէկոնոմբանկ, թե Ֆասթ Բանկ. "
                    "Do not give banking facts yet."
                ),
            )
            return

        if _needs_section_clarification(effective_user_text, active_bank, active_section):
            turn_ctx.add_message(
                role="developer",
                content=(
                    f"The bank is {active_bank}. "
                    "Ask one short clarification question in Armenian asking whether they need "
                    "վարկեր, ավանդներ, թե մասնաճյուղերի հասցեներ. "
                    "Do not switch to any other bank."
                ),
            )
            return

        if _is_options_query(effective_user_text) and active_bank and active_section:
            retrieval_query = f"{active_bank}\n{active_section}"
        else:
            retrieval_query = _build_retrieval_query_from_text(turn_ctx, effective_user_text)
            retrieval_query = _augment_query_with_focus(
                query=retrieval_query,
                user_text=effective_user_text,
                active_bank=active_bank,
                active_section=active_section,
            )

        branch_request = (
            detect_requested_section(query_tokens(effective_user_text)) == BRANCH_SECTION
            or active_section == BRANCH_SECTION
        )
        retrieval_limit = 20 if branch_request else 6
        retrieved = retrieve_relevant_chunks(
            retrieval_query,
            KNOWLEDGE_CHUNKS,
            limit=retrieval_limit,
        )
        retrieved = _filter_retrieved_to_focus(
            retrieved=retrieved,
            active_bank=active_bank,
            active_section=active_section,
            user_text=effective_user_text,
        )
        if branch_request:
            retrieved = _filter_branch_chunks_by_location(
            retrieved,
                _branch_location_tokens(effective_user_text, active_bank, active_section),
            )

        injected_context = format_retrieved_context(retrieval_query, retrieved)
        focus_instruction = _build_focus_instruction(active_bank, active_section)
        developer_parts = [part for part in (switch_instruction, focus_instruction, injected_context) if part]
        developer_content = "\n\n".join(developer_parts)

        logger.info(
            "User turn=%r | effective_user_text=%r | active_bank=%r | active_section=%r | retrieval_query=%r | retrieved=%d | titles=%s",
            user_text,
            effective_user_text,
            active_bank,
            active_section,
            retrieval_query,
            len(retrieved),
            [chunk.title for chunk in retrieved],
        )
        logger.debug("Injected context:\n%s", developer_content)

        turn_ctx.add_message(
            role="developer",
            content=developer_content,
        )

    async def tts_node(self, text, model_settings):
        async for frame in Agent.default.tts_node(
            self,
            _spoken_text_stream(text),
            model_settings,
        ):
            yield frame


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD pre-loaded.")


async def entrypoint(ctx: JobContext) -> None:
    logger.info("New session - room: %s", ctx.room.name)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=build_stt_engine(),
        llm=openai.LLM(
            model=LLM_MODEL,
            temperature=0.0,
        ),
        tts=openai.TTS(
            model=TTS_MODEL,
            voice=TTS_VOICE,
        ),
    )

    await session.start(
        room=ctx.room,
        agent=BankAgent(),
        room_input_options=RoomInputOptions(),
    )

    await session.generate_reply(
        instructions=f"Greet the user with this exact Armenian message: {GREETING}"
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
