import time
import os
from typing import Dict, Any, Optional, Generator
from openai import OpenAI
from src.core.llm_provider import LLMProvider

class OpenAIProvider(LLMProvider):
    def __init__(self, model_name: str = "gpt-4o", api_key: Optional[str] = None):
        super().__init__(model_name, api_key)
        
        # Kiểm tra xem có cấu hình Custom API Base / LLM Endpoint từ môi trường không
        api_base = os.getenv("LLM_ENDPOINT") or os.getenv("OPENAI_API_BASE")
        
        if api_base:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=api_base
            )
        # Tự động hỗ trợ OpenRouter nếu API key có định dạng sk-or-
        elif self.api_key and self.api_key.startswith("sk-or-"):
            # Nếu model_name là gpt-4o hoặc tương tự, ánh xạ sang định dạng OpenRouter cần thiết
            if self.model_name == "gpt-4o":
                self.model_name = "openai/gpt-4o"
            elif self.model_name == "gpt-3.5-turbo":
                self.model_name = "openai/gpt-3.5-turbo"
                
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        else:
            self.client = OpenAI(api_key=self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        start_time = time.time()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Sử dụng streaming để chủ động bắt Stop Sequence ở phía client
        # Đề phòng trường hợp API Gateway của bên thứ ba bỏ qua tham số stop
        try:
            stream_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
                max_tokens=8192,
                stop=["Observation:", "observation:", "Observation: "]
            )

            content_chunks = []
            reasoning_chunks = []
            stop_words = ["Observation:", "observation:", "\nObservation:", "\nobservation:", "Observation: ", "observation: "]
            aborted = False
            accumulated_content = ""

            for chunk in stream_response:
                delta = chunk.choices[0].delta
                
                # Trích xuất phần reasoning (nếu có, ví dụ DeepSeek)
                reasoning_delta = getattr(delta, "reasoning_content", "") or ""
                if reasoning_delta:
                    reasoning_chunks.append(reasoning_delta)
                    
                content_delta = getattr(delta, "content", "") or ""
                if content_delta:
                    accumulated_content += content_delta
                    
                    # 1. Kiểm tra xem đã hoàn thành Action block chưa (duyệt ngoặc cân bằng)
                    # Giúp ngắt dòng stream ngay khi mô hình đóng ngoặc tool call,
                    # bất kể mô hình có viết thêm 'Observation:', 'response:' hay không
                    import re
                    match = re.search(r"Action:\s*(\w+)\(", accumulated_content, re.IGNORECASE)
                    if match:
                        start_idx = match.end()
                        paren_count = 1
                        idx = start_idx
                        in_string = False
                        string_char = None
                        escaped = False
                        
                        while idx < len(accumulated_content):
                            char = accumulated_content[idx]
                            if escaped:
                                escaped = False
                                idx += 1
                                continue
                            if char == '\\':
                                escaped = True
                                idx += 1
                                continue
                            if char in ('"', "'"):
                                if not in_string:
                                    in_string = True
                                    string_char = char
                                elif string_char == char:
                                    in_string = False
                                    string_char = None
                            if not in_string:
                                if char == '(':
                                    paren_count += 1
                                elif char == ')':
                                    paren_count -= 1
                                    if paren_count == 0:
                                        accumulated_content = accumulated_content[:idx + 1]
                                        aborted = True
                                        break
                            idx += 1
                        if aborted:
                            break

                    # 2. Kiểm tra xem có stop word nào xuất hiện trong phần content tích lũy không (dự phòng)
                    if not aborted:
                        for stop_word in stop_words:
                            if stop_word in accumulated_content:
                                idx = accumulated_content.index(stop_word)
                                accumulated_content = accumulated_content[:idx]
                                aborted = True
                                break
                    if aborted:
                        break
                        
            content = accumulated_content.strip()
            reasoning = "".join(reasoning_chunks).strip()
            
            if not content and reasoning:
                content = reasoning
                
            # Ước tính token sử dụng dựa trên ký tự (1 token ~ 4 ký tự)
            prompt_tokens = int(len(prompt) / 4) + (int(len(system_prompt) / 4) if system_prompt else 0)
            completion_tokens = int(len(content) / 4) + int(len(reasoning) / 4)
            total_tokens = prompt_tokens + completion_tokens
            
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        except Exception as e:
            # Fallback về non-streaming nếu stream gặp sự cố tương thích
            print(f"⚠️ STREAMING FALLBACK DUE TO EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=8192,
                stop=["Observation:", "observation:", "Observation: "]
            )
            msg = response.choices[0].message
            content = getattr(msg, "content", "") or ""
            reasoning = getattr(msg, "reasoning_content", "") or ""
            
            if not content and reasoning:
                content = reasoning
                
            # Trích xuất cắt đuôi ở fallback
            stop_words = ["Observation:", "observation:", "\nObservation:", "\nobservation:"]
            for stop_word in stop_words:
                if stop_word in content:
                    content = content.split(stop_word)[0]
                    break
            
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens
            else:
                prompt_tokens = int(len(prompt) / 4) + (int(len(system_prompt) / 4) if system_prompt else 0)
                completion_tokens = int(len(content) / 4) + int(len(reasoning) / 4)
                total_tokens = prompt_tokens + completion_tokens
                
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }

        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        return {
            "content": content,
            "usage": usage,
            "latency_ms": latency_ms,
            "provider": "openai"
        }

    def generate_stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        start_time = time.time()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
                max_tokens=8192,
                stop=["Observation:", "observation:", "Observation: "]
            )

            content_chunks = []
            reasoning_chunks = []
            stop_words = ["Observation:", "observation:", "\nObservation:", "\nobservation:", "Observation: ", "observation: "]
            aborted = False
            accumulated_content = ""

            for chunk in stream_response:
                delta = chunk.choices[0].delta
                
                # Trích xuất phần reasoning (nếu có)
                reasoning_delta = getattr(delta, "reasoning_content", "") or ""
                if reasoning_delta:
                    reasoning_chunks.append(reasoning_delta)
                    yield {"type": "chunk", "content": "", "reasoning": reasoning_delta}
                    
                content_delta = getattr(delta, "content", "") or ""
                if content_delta:
                    accumulated_content += content_delta
                    
                    # 1. Kiểm tra xem đã hoàn thành Action block chưa (duyệt ngoặc cân bằng)
                    import re
                    match = re.search(r"Action:\s*(\w+)\(", accumulated_content, re.IGNORECASE)
                    if match:
                        start_idx = match.end()
                        paren_count = 1
                        idx = start_idx
                        in_string = False
                        string_char = None
                        escaped = False
                        
                        while idx < len(accumulated_content):
                            char = accumulated_content[idx]
                            if escaped:
                                escaped = False
                                idx += 1
                                continue
                            if char == '\\':
                                escaped = True
                                idx += 1
                                continue
                            if char in ('"', "'"):
                                if not in_string:
                                    in_string = True
                                    string_char = char
                                elif string_char == char:
                                    in_string = False
                                    string_char = None
                            if not in_string:
                                if char == '(':
                                    paren_count += 1
                                elif char == ')':
                                    paren_count -= 1
                                    if paren_count == 0:
                                        # Yield the part of content_delta that leads to final parenthesis
                                        truncated_accumulated = accumulated_content[:idx + 1]
                                        prev_len = len(accumulated_content) - len(content_delta)
                                        yield_chunk = truncated_accumulated[prev_len:]
                                        if yield_chunk:
                                            yield {"type": "chunk", "content": yield_chunk, "reasoning": ""}
                                        accumulated_content = truncated_accumulated
                                        aborted = True
                                        break
                            idx += 1
                        if aborted:
                            break

                    # 2. Kiểm tra xem có stop word nào xuất hiện trong phần content tích lũy không
                    if not aborted:
                        for stop_word in stop_words:
                            if stop_word in accumulated_content:
                                idx = accumulated_content.index(stop_word)
                                truncated_accumulated = accumulated_content[:idx]
                                prev_len = len(accumulated_content) - len(content_delta)
                                yield_chunk = truncated_accumulated[prev_len:]
                                if yield_chunk:
                                    yield {"type": "chunk", "content": yield_chunk, "reasoning": ""}
                                accumulated_content = truncated_accumulated
                                aborted = True
                                break
                    
                    if aborted:
                        break
                    
                    # Nếu chưa abort, yield content_delta bình thường
                    yield {"type": "chunk", "content": content_delta, "reasoning": ""}
                        
            content = accumulated_content.strip()
            reasoning = "".join(reasoning_chunks).strip()
            
            if not content and reasoning:
                content = reasoning
                
            prompt_tokens = int(len(prompt) / 4) + (int(len(system_prompt) / 4) if system_prompt else 0)
            completion_tokens = int(len(content) / 4) + int(len(reasoning) / 4)
            total_tokens = prompt_tokens + completion_tokens
            
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        except Exception as e:
            # Fallback về non-streaming
            print(f"⚠️ STREAMING FALLBACK DUE TO EXCEPTION IN generate_stream: {e}")
            import traceback
            traceback.print_exc()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=4096,
                stop=["Observation:", "observation:", "Observation: "]
            )
            msg = response.choices[0].message
            content = getattr(msg, "content", "") or ""
            reasoning = getattr(msg, "reasoning_content", "") or ""
            
            if not content and reasoning:
                content = reasoning
                
            stop_words = ["Observation:", "observation:", "\nObservation:", "\nobservation:"]
            for stop_word in stop_words:
                if stop_word in content:
                    content = content.split(stop_word)[0]
                    break
            
            yield {"type": "chunk", "content": content, "reasoning": reasoning}
            
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens
            else:
                prompt_tokens = int(len(prompt) / 4) + (int(len(system_prompt) / 4) if system_prompt else 0)
                completion_tokens = int(len(content) / 4) + int(len(reasoning) / 4)
                total_tokens = prompt_tokens + completion_tokens
                
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }

        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        yield {
            "type": "done",
            "content": content,
            "usage": usage,
            "latency_ms": latency_ms,
            "provider": "openai"
        }

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
            max_tokens=4096,
            stop=["Observation:", "observation:", "Observation: "]
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
