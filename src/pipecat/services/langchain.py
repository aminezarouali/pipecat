import sys
from typing import Union

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import Runnable
from loguru import logger

from pipecat.frames.frames import (Frame, LLMFullResponseEndFrame,
                                   LLMFullResponseStartFrame, LLMMessagesFrame,
                                   LLMResponseEndFrame, LLMResponseStartFrame,
                                   TextFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class LangchainProcessor(FrameProcessor):
    def __init__(self, chain: Runnable, transcript_key: str = "input"):
        super().__init__()
        self._chain = chain
        self._transcript_key = transcript_key

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, LLMMessagesFrame):
            # Messages are accumulated by the `LLMUserResponseAggregator` in a list of messages.
            # The last one by the human is the one we want to send to the LLM.
            logger.debug(f"Got transcription frame {frame}")
            text: str = frame.messages[-1]["content"]

            await self._ainvoke(text.strip())
        else:
            await self.push_frame(frame)

    async def _invoke(self, text: str):
        response = await self._chain.ainvoke({self._transcript_key: text})
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(TextFrame(response))
        await self.push_frame(LLMFullResponseEndFrame())

    @staticmethod
    def __get_token_value(text: Union[str, AIMessageChunk]) -> str | None:
        match text:
            case str():
                return text
            case AIMessageChunk():
                return text.content
            case _:
                return None

    async def _ainvoke(self, text: str):
        logger.debug(f"Invoking chain with {text}")
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for token in self._chain.astream({self._transcript_key: text}):
                await self.push_frame(LLMResponseStartFrame())
                await self.push_frame(TextFrame(self.__get_token_value(token)))
                await self.push_frame(LLMResponseEndFrame())
        except GeneratorExit:
            logger.warning("Generator was closed prematurely")
            raise  # Re-raise to ensure proper generator closure
        except Exception as e:
            logger.error(f"An unknown error occurred: {e}")
            raise
        await self.push_frame(LLMFullResponseEndFrame())
