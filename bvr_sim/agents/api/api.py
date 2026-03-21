import os
import json
import time
import http.client
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from typing import Optional, List, Dict
from openai import OpenAI


load_dotenv()


class API(ABC):
    def __init__(self, api_key: Optional[str] = None, model: str = None, url: str = None, **kwargs):
        self.api_key = api_key
        self.model = model
        self.url = url
        for k, v in kwargs.items():
            setattr(self, k, v)

    @abstractmethod
    def __call__(
        self,
        input_messages: Optional[List[Dict]] = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        pass


class WWXQ_API(API):
    def __init__(self, api_key: Optional[str] = None, model: str = 'qwen3-8b', **kwargs):
        super().__init__(
            api_key=api_key or os.getenv("WWXQ_API_KEY"),
            model=model,
            url="cloud.infini-ai.com",
            **kwargs
        )

    def __call__(
        self,
        input_messages: Optional[List[Dict]] = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        # **kwargs  # legacy support for old api call with model_name
    ) -> str:
        if input_messages is None:
            raise ValueError("messages should not be None!")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": input_messages,
            # "temperature": temperature,
            "max_tokens": max_tokens,
        }

        MAX_RETRIES = 4
        attempts = 0
        RETRY_INTERVAL = 1

        while attempts < MAX_RETRIES:
            try:
                conn = http.client.HTTPSConnection(self.url)
                conn.request("POST", f"/maas/{self.model}/nvidia/chat/completions",
                            json.dumps(payload), headers)
                res = conn.getresponse()
                data = res.read()
                response_json = json.loads(data.decode("utf-8"))
                conn.close()
                return response_json["choices"][0]["message"]["content"]

            except KeyError as e:
                if attempts < MAX_RETRIES - 1:
                    print(f"KeyError: {e}. Retrying in {RETRY_INTERVAL} seconds...")
                    time.sleep(RETRY_INTERVAL)
                    attempts += 1
                    RETRY_INTERVAL = RETRY_INTERVAL * 2
                else:
                    raise Exception(f"Failed to get 'choices' after {MAX_RETRIES} attempts.") from e


class OpenAI_API(API):
    def __init__(self, api_key: Optional[str] = None, model: str = 'gpt-4o-mini', **kwargs):
        super().__init__(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            model=model,
            url='https://xiaoai.plus/v1',
            **kwargs
        )
        self.client = OpenAI(api_key=self.api_key, base_url=self.url)

    def __call__(
        self,
        input_messages: Optional[List[Dict]] = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        if input_messages is None:
            raise ValueError("messages should not be None!")

        MAX_RETRIES = 4
        attempts = 0
        RETRY_INTERVAL = 1

        while attempts < MAX_RETRIES:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=input_messages,
                    # temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content

            except Exception as e:
                if attempts < MAX_RETRIES - 1:
                    print(f"Error: {e}. Retrying in {RETRY_INTERVAL} seconds...")
                    time.sleep(RETRY_INTERVAL)
                    attempts += 1
                    RETRY_INTERVAL = RETRY_INTERVAL * 2
                else:
                    raise Exception(f"Failed after {MAX_RETRIES} attempts.") from e


class Volcano_API(API):
    """ See https://www.volcengine.com/docs/82379/1585128 """
    def __init__(self, api_key: Optional[str] = None, model: str = 'doubao-seed-1-6-250615', **kwargs):
        super().__init__(
            api_key=api_key or os.getenv("ARK_API_KEY"),
            model=model,
            url='https://ark.cn-beijing.volces.com/api/v3',
            **kwargs
        )
        self.client = OpenAI(
            base_url=self.url,
            api_key=self.api_key,
        )

    def __call__(
        self,
        input_messages: Optional[List[Dict]] = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        """
        model:  doubao-seed-1-6-vision-250815
                doubao-seed-1-6-250615
                doubao-seed-1-6-thinking-250615
                doubao-seed-1-6-thinking-250715
                doubao-seed-1-6-flash-250828
                doubao-seed-1-6-flash-250615
                doubao-seed-1-6-flash-250715
                kimi-k2-250905
                deepseek-v3-1-terminus
                deepseek-v3-1-250821
        """
        if input_messages is None:
            raise ValueError("messages should not be None!")

        MAX_RETRIES = 4
        attempts = 0
        RETRY_INTERVAL = 1

        while attempts < MAX_RETRIES:
            try:
                print(f"self.client.chat.completions.create called, model={self.model}")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=input_messages,
                    # temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content

            except Exception as e:
                if attempts < MAX_RETRIES - 1:
                    print(f"Error: {e}. Retrying in {RETRY_INTERVAL} seconds...")
                    time.sleep(RETRY_INTERVAL)
                    attempts += 1
                    RETRY_INTERVAL = RETRY_INTERVAL * 2
                else:
                    raise Exception(f"Failed after {MAX_RETRIES} attempts.") from e
